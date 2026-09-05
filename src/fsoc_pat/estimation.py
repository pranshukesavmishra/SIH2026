"""
Estimating where the beacon is, and where it is going.

Detections are noisy, intermittent and occasionally wrong. A tracker cannot
command the mount straight from them: it needs a smoothed estimate of the
target's angular position *and rate*, because by the time a command takes
effect the target has moved. Rate is what makes the feed-forward term in the
controller possible, and feed-forward is what keeps the boresight error small
during the fast part of a pass.

Two motion models are run at once and blended:

  * A **smooth** model, with very little assumed jerk, fits the long slow
    approach from the horizon and keeps the estimate quiet when the target is
    barely manoeuvring.
  * A **manoeuvring** model, with four orders of magnitude more assumed jerk,
    fits culmination and the sharp turns of a UAV, where a smooth filter lags
    badly.

Both share a constant-acceleration structure and differ only in their process
noise, which is the standard way to build an IMM pair: the mode probabilities
then say how hard the target is maneuvering, rather than which kinematic
equation applies.

An Interacting Multiple Model (IMM) filter runs both and weights them by how
well each is predicting, so the tracker is quiet when the target is quiet and
responsive when it manoeuvres. Tuning a single filter to do both means
choosing which half of the pass to track badly.

Everything is in azimuth/elevation because that is what the mount takes. Near
the zenith this is genuinely ill-conditioned -- a target passing overhead
demands enormous azimuth rate, the classic keyhole problem of an az/el mount --
and that is a real limit of the hardware, not an artefact worth hiding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from . import geometry as geo

# State layout: [az, el, az_rate, el_rate, az_accel, el_accel]
STATE_DIM = 6
MEAS_DIM = 2


def _transition(dt: float) -> np.ndarray:
    """Constant-acceleration transition; the CV model just gets no accel noise."""
    f = np.eye(STATE_DIM)
    f[0, 2] = f[1, 3] = dt
    f[2, 4] = f[3, 5] = dt
    f[0, 4] = f[1, 5] = 0.5 * dt * dt
    return f


def _process_noise(dt: float, jerk_psd: float) -> np.ndarray:
    """
    Discrete white-noise-jerk process noise.

    ``jerk_psd`` is the assumed spectral density of angular jerk in rad^2/s^5.
    Raising it makes the filter trust its measurements more and its model less.
    """
    q = np.zeros((STATE_DIM, STATE_DIM))
    t2, t3, t4, t5 = dt ** 2, dt ** 3, dt ** 4, dt ** 5
    block = np.array([[t5 / 20.0, t4 / 8.0, t3 / 6.0],
                      [t4 / 8.0, t3 / 3.0, t2 / 2.0],
                      [t3 / 6.0, t2 / 2.0, dt]]) * jerk_psd
    for axis in (0, 1):                       # az and el share the structure
        idx = [axis, 2 + axis, 4 + axis]
        for i, ii in enumerate(idx):
            for j, jj in enumerate(idx):
                q[ii, jj] = block[i, j]
    return q


class KalmanFilter:
    """One motion model. Plain linear Kalman filter over the shared state."""

    def __init__(self, jerk_psd: float):
        self.jerk_psd = float(jerk_psd)
        self.x = np.zeros(STATE_DIM)
        self.P = np.eye(STATE_DIM)
        self.H = np.zeros((MEAS_DIM, STATE_DIM))
        self.H[0, 0] = self.H[1, 1] = 1.0

    def initialise(self, az: float, el: float, sigma: float,
                   rate_sigma_deg_s: float = 3.0) -> None:
        """
        Start a track from a single detection.

        ``rate_sigma_deg_s`` must comfortably exceed the fastest target the
        system is meant to catch: a new track has no velocity information, so
        this is the only thing that keeps its first prediction gate wide enough
        to admit the second detection. Set it too low and fast targets can
        never form a track at all -- every frame spawns a fresh one-hit track
        that dies unconfirmed.
        """
        rate_sigma = np.radians(rate_sigma_deg_s)
        self.x = np.zeros(STATE_DIM)
        self.x[0], self.x[1] = az, el
        self.P = np.diag([sigma ** 2, sigma ** 2,
                          rate_sigma ** 2, rate_sigma ** 2,
                          rate_sigma ** 2, rate_sigma ** 2])

    def predict(self, dt: float) -> None:
        f = _transition(dt)
        self.x = f @ self.x
        self.P = f @ self.P @ f.T + _process_noise(dt, self.jerk_psd)

    def innovation(self, z: np.ndarray) -> np.ndarray:
        """Measurement minus prediction, with azimuth wrapped across the seam."""
        y = z - self.H @ self.x
        y[0] = geo.wrap_pi(y[0])
        return y

    def update(self, z: np.ndarray, R: np.ndarray) -> float:
        """Apply a measurement; returns its likelihood under this model."""
        y = self.innovation(z)
        S = self.H @ self.P @ self.H.T + R
        try:
            S_inv = np.linalg.inv(S)
        except np.linalg.LinAlgError:                     # pragma: no cover
            return 1e-300
        K = self.P @ self.H.T @ S_inv
        self.x = self.x + K @ y
        self.x[0] = geo.wrap_pi(self.x[0])
        # Joseph form: stays positive-definite under the repeated updates and
        # occasional coasting this tracker does, where the short form drifts.
        I_KH = np.eye(STATE_DIM) - K @ self.H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T
        det = max(np.linalg.det(S), 1e-300)
        return float(np.exp(-0.5 * y @ S_inv @ y) / np.sqrt((2 * np.pi) ** MEAS_DIM * det))

    def gate_distance(self, z: np.ndarray, R: np.ndarray) -> float:
        """Squared Mahalanobis distance, for chi-square gating."""
        y = self.innovation(z)
        S = self.H @ self.P @ self.H.T + R
        try:
            return float(y @ np.linalg.inv(S) @ y)
        except np.linalg.LinAlgError:                     # pragma: no cover
            return np.inf


class IMMEstimator:
    """
    Interacting Multiple Model filter over a quiet and an agile motion model.

    The mode probabilities are worth showing in the GUI: watching the agile
    model take over as a pass approaches culmination is the clearest possible
    evidence that the filter is doing something a single model could not.
    """

    def __init__(self, quiet_jerk_psd: float = 1e-8, agile_jerk_psd: float = 1e-4,
                 switch_probability: float = 0.03):
        self.models = [KalmanFilter(quiet_jerk_psd), KalmanFilter(agile_jerk_psd)]
        self.mu = np.array([0.5, 0.5])
        p = switch_probability
        self.transition = np.array([[1 - p, p], [p, 1 - p]])
        self.initialised = False

    # ---- lifecycle -----------------------------------------------------
    def initialise(self, az: float, el: float, sigma: float,
                   rate_sigma_deg_s: float = 3.0) -> None:
        for m in self.models:
            m.initialise(az, el, sigma, rate_sigma_deg_s)
        self.mu = np.array([0.5, 0.5])
        self.initialised = True

    def _mix(self) -> None:
        """Blend the models' states in proportion to how likely each mode is."""
        c = self.transition.T @ self.mu
        c = np.maximum(c, 1e-12)
        mixing = (self.transition * self.mu[:, None]) / c[None, :]
        states = [m.x.copy() for m in self.models]
        covs = [m.P.copy() for m in self.models]
        for j, m in enumerate(self.models):
            x = sum(mixing[i, j] * states[i] for i in range(len(self.models)))
            P = np.zeros_like(covs[0])
            for i in range(len(self.models)):
                d = (states[i] - x).reshape(-1, 1)
                P += mixing[i, j] * (covs[i] + d @ d.T)
            m.x, m.P = x, P

    def predict(self, dt: float) -> None:
        self._mix()
        for m in self.models:
            m.predict(dt)

    def update(self, z: np.ndarray, R: np.ndarray) -> None:
        likelihoods = np.array([m.update(z, R) for m in self.models])
        posterior = np.maximum(likelihoods * (self.transition.T @ self.mu), 1e-300)
        self.mu = posterior / posterior.sum()

    def gate_distance(self, z: np.ndarray, R: np.ndarray) -> float:
        """Gate on the most confident model, so a manoeuvre is not gated out."""
        return min(m.gate_distance(z, R) for m in self.models)

    # ---- outputs -------------------------------------------------------
    @property
    def state(self) -> np.ndarray:
        return sum(self.mu[i] * m.x for i, m in enumerate(self.models))

    @property
    def covariance(self) -> np.ndarray:
        x = self.state
        P = np.zeros((STATE_DIM, STATE_DIM))
        for i, m in enumerate(self.models):
            d = (m.x - x).reshape(-1, 1)
            P += self.mu[i] * (m.P + d @ d.T)
        return P

    @property
    def angles(self) -> Tuple[float, float]:
        s = self.state
        return float(s[0]), float(s[1])

    @property
    def rates(self) -> Tuple[float, float]:
        s = self.state
        return float(s[2]), float(s[3])

    @property
    def position_sigma(self) -> float:
        """One-sigma angular position uncertainty, for gating and for display."""
        P = self.covariance
        return float(np.sqrt(max(P[0, 0] * np.cos(self.angles[1]) ** 2 + P[1, 1], 0.0)))

    def predict_ahead(self, dt: float) -> Tuple[float, float]:
        """Where the target will be in ``dt`` seconds, without consuming state."""
        f = _transition(dt)
        out = np.zeros(STATE_DIM)
        for i, m in enumerate(self.models):
            out += self.mu[i] * (f @ m.x)
        return float(geo.wrap_pi(out[0])), float(geo.clamp_elevation(out[1]))
