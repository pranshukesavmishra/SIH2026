"""
Everything that stops the beacon sitting still on the detector.

Two effects dominate coarse-alignment tracking and they fail differently:

  * Atmospheric turbulence moves the *apparent* position of every source in
    the field, with a correlation time set by the Greenwood frequency. It is
    partly common-mode, so a tracker can reject some of it by referencing the
    star field — but only partly, because anisoplanatism makes each direction
    wander independently at small scales.

  * Platform vibration moves the *camera*, as sharp resonances. It is not
    common-mode with anything and it is often above the frame rate, so it
    aliases. A controller tuned without it will look fine and then oscillate.

Keeping them as separate objects means either can be switched off to attribute
a tracking failure to one or the other.
"""
from __future__ import annotations

import numpy as np


class Turbulence:
    """Correlated tip/tilt jitter plus log-normal scintillation."""

    def __init__(self, cfg, rng: np.random.Generator):
        self.cfg = cfg
        self.rng = rng
        self._common = np.zeros(2)              # shared by the whole field
        self._per_target = {}                   # anisoplanatic residual

    def step(self, dt: float) -> None:
        if not self.cfg.enabled:
            return
        # First-order Gauss-Markov with the Greenwood frequency as its corner.
        alpha = float(np.exp(-2.0 * np.pi * self.cfg.greenwood_hz * dt))
        drive = np.sqrt(max(1.0 - alpha ** 2, 0.0))
        sigma = self.cfg.tilt_rms_urad * 1e-6
        self._common = alpha * self._common + drive * sigma * 0.8 * self.rng.normal(size=2)
        for key in list(self._per_target):
            self._per_target[key] = (alpha * self._per_target[key]
                                     + drive * sigma * 0.2 * self.rng.normal(size=2))

    def tilt(self, target_key: str) -> np.ndarray:
        """Angular offset (d_az, d_el) in radians to apply to one source."""
        if not self.cfg.enabled:
            return np.zeros(2)
        if target_key not in self._per_target:
            self._per_target[target_key] = np.zeros(2)
        return self._common + self._per_target[target_key]

    def scintillation(self) -> float:
        """Multiplicative intensity fluctuation with unit mean."""
        si = self.cfg.scintillation_index
        if not self.cfg.enabled or si <= 0.0:
            return 1.0
        sigma_ln = np.sqrt(np.log1p(si))
        return float(np.exp(sigma_ln * self.rng.normal() - 0.5 * sigma_ln ** 2))

    @property
    def blur_px(self) -> float:
        return self.cfg.seeing_blur_px if self.cfg.enabled else 0.0


class Vibration:
    """
    Platform vibration as driven, damped resonances.

    Each mode is integrated as a second-order oscillator forced by white
    noise, sub-stepped so that a 120 Hz mode is still integrated stably at a
    30 Hz frame rate. The camera only *samples* at the frame rate, so the
    high modes alias — deliberately, because that is what real hardware does.
    """

    def __init__(self, cfg, rng: np.random.Generator):
        self.cfg = cfg
        self.rng = rng
        modes = cfg.modes if cfg.enabled else []
        self._omega = np.array([2.0 * np.pi * m[0] for m in modes]) if modes else np.zeros(0)
        self._amp = np.array([m[1] * 1e-6 for m in modes]) if modes else np.zeros(0)
        self._zeta = np.array([m[2] for m in modes]) if modes else np.zeros(0)
        self._x = np.zeros((len(modes), 2))
        self._v = np.zeros((len(modes), 2))
        self._offset = np.zeros(2)

    def step(self, dt: float) -> None:
        if not self.cfg.enabled:
            return
        if len(self._omega):
            f_max = float(self._omega.max() / (2.0 * np.pi))
            n_sub = max(1, int(np.ceil(dt * f_max * 12.0)))
            h = dt / n_sub
            for _ in range(n_sub):
                # Steady-state RMS of a white-driven oscillator is
                # sqrt(q / (4 zeta omega^3)); invert it so `amp` is the RMS.
                q = 4.0 * self._zeta * self._omega ** 3 * self._amp ** 2
                force = (np.sqrt(q / h)[:, None] * self.rng.normal(size=self._x.shape))
                accel = (force
                         - 2.0 * (self._zeta * self._omega)[:, None] * self._v
                         - (self._omega ** 2)[:, None] * self._x)
                self._v += accel * h
                self._x += self._v * h
            self._offset = self._x.sum(axis=0)
        else:
            self._offset = np.zeros(2)
        if self.cfg.broadband_rms_urad > 0.0:
            self._offset = self._offset + self.cfg.broadband_rms_urad * 1e-6 * self.rng.normal(size=2)

    @property
    def offset(self) -> np.ndarray:
        """Camera pointing perturbation (d_az, d_el) in radians."""
        return self._offset if self.cfg.enabled else np.zeros(2)
