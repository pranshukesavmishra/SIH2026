"""
Commanding the mount.

Two facts dominate the design, and both push the same way:

**The loop is slow and the disturbances are fast.** Turbulence here has a
Greenwood frequency of 25 Hz and the platform resonates at 18, 47 and 120 Hz,
while the camera delivers 30 frames a second. Everything above 15 Hz is
aliased and simply cannot be observed, let alone corrected. A controller that
tries to chase that jitter amplifies it -- it acts on aliased noise, and the
mount's own inertia turns the commands into extra motion. The correct answer
is a *deliberately low* closed-loop bandwidth, a few hertz, tight enough to
follow real target motion and slow enough to average the jitter away. This is
why a real terminal puts a fine steering mirror downstream at kilohertz rates:
the coarse stage is not supposed to solve the fast problem.

**Commands arrive late.** Pointing commands take effect ~40 ms after they are
issued, which at a 3 Hz bandwidth is already 43 degrees of phase lag -- enough
to turn a well-damped loop into an oscillating one. A **Smith predictor**
handles this: an internal model of the mount is driven by the same commands,
run forward by the latency, and the controller closes its loop on the model's
*predicted* position instead of the stale measured one. The published result
for this technique on optical tip/tilt loops is a bandwidth improvement of
several times over plain PI control.

The error signal itself comes from the image, not the encoders. The offset of
the beacon from the image centre *is* the boresight error, measured optically,
and it is immune to encoder bias -- which is exactly why a tracking sensor
exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from . import geometry as geo
from .camera import Gimbal
from .config import GimbalConfig


class SmithPredictor:
    """
    An internal replica of the mount, used to see past the command latency.

    The replica is driven by every command the controller issues and then run
    forward by the dead time, so ``predict`` answers "where will the real mount
    actually be when this command lands?" rather than "where was it?".
    """

    def __init__(self, cfg: GimbalConfig, az0: float, el0: float):
        self.cfg = cfg
        self._model = Gimbal(cfg, az0, el0, np.random.default_rng(0))
        self.horizon_s = cfg.command_latency_ms / 1000.0

    def issue(self, az: float, el: float) -> None:
        self._model.command(az, el)

    def advance(self, dt: float) -> None:
        self._model.step(dt)

    def sync(self, az: float, el: float, blend: float = 0.05) -> None:
        """
        Nudge the replica towards the measured pointing.

        Pure open-loop prediction drifts as the model and the real mount
        diverge; a slow blend keeps them together without reintroducing the
        measurement lag the predictor exists to remove.
        """
        self._model.az = float(geo.wrap_pi(self._model.az
                                           + blend * geo.wrap_pi(az - self._model.az)))
        self._model.el = float(self._model.el + blend * (el - self._model.el))

    def predict(self, dt: float, sub_steps: int = 4) -> Tuple[float, float]:
        """
        Where the replica will be in ``dt`` seconds, without consuming it.

        Uses a snapshot/restore rather than a deep copy: this runs every frame,
        and copying the mount's command queue and generator each time showed up
        directly in the frame budget.
        """
        state = self._model.snapshot()
        step = dt / max(sub_steps, 1)
        for _ in range(max(sub_steps, 1)):
            self._model.step(step)
        az, el = self._model.az, self._model.el
        self._model.restore(state)
        return az, el

    @property
    def pointing(self) -> Tuple[float, float]:
        return self._model.az, self._model.el


@dataclass
class ControlTelemetry:
    """What the controller did this frame, for the metrics engine and the GUI."""
    command_az: float
    command_el: float
    error_az: float
    error_el: float
    lead_s: float
    used_optical_error: bool


class PointingController:
    """
    Bandwidth-limited proportional-integral controller with rate feed-forward
    and Smith-predictor dead-time compensation.

    ``bandwidth_hz`` is the single most important knob and the one most often
    set wrong. Raising it does not improve tracking here -- it makes the mount
    chase turbulence it cannot resolve. See the module docstring.
    """

    def __init__(self, gimbal_cfg: GimbalConfig, frame_rate_hz: float,
                 az0: float = 0.0, el0: float = 0.0,
                 bandwidth_hz: float = 3.0, kp: float = 0.75, ki: float = 0.35,
                 settle_margin_s: float = 0.02, integral_limit_urad: float = 2000.0):
        self.cfg = gimbal_cfg
        self.dt_nominal = 1.0 / frame_rate_hz
        self.bandwidth_hz = float(bandwidth_hz)
        self.kp, self.ki = float(kp), float(ki)
        self.settle_margin_s = float(settle_margin_s)
        self.integral_limit = integral_limit_urad * 1e-6

        self.smith = SmithPredictor(gimbal_cfg, az0, el0)
        self._integral = np.zeros(2)
        self._filtered_error = np.zeros(2)
        self._last_command = (az0, el0)

    def reset(self, az: float, el: float) -> None:
        self.smith = SmithPredictor(self.cfg, az, el)
        self._integral = np.zeros(2)
        self._filtered_error = np.zeros(2)
        self._last_command = (az, el)

    @property
    def lead_time(self) -> float:
        """How far ahead the target must be predicted for a command to land on it."""
        return self.cfg.command_latency_ms / 1000.0 + self.settle_margin_s

    def _low_pass(self, error: np.ndarray, dt: float) -> np.ndarray:
        alpha = 1.0 - np.exp(-2.0 * np.pi * self.bandwidth_hz * max(dt, 1e-6))
        self._filtered_error += alpha * (error - self._filtered_error)
        return self._filtered_error

    def update(self, reported: Tuple[float, float], dt: float,
               optical_error: Optional[Tuple[float, float]] = None,
               absolute_target: Optional[Tuple[float, float]] = None,
               target_rates: Tuple[float, float] = (0.0, 0.0)) -> ControlTelemetry:
        """
        Produce the next pointing command.

        ``optical_error`` is the beacon's angular offset from the boresight as
        measured in the image, and is preferred whenever it exists. Without a
        detection the controller falls back to ``absolute_target``, the
        filter's own estimate, which carries the encoder error the optical
        path avoids -- degraded, but enough to coast through a dropout.
        """
        self.smith.advance(dt)
        self.smith.sync(*reported)

        lead = self.lead_time
        predicted_az, predicted_el = self.smith.predict(lead)

        if optical_error is not None:
            measured = np.array(optical_error, dtype=float)
            used_optical = True
        elif absolute_target is not None:
            measured = np.array([geo.wrap_pi(absolute_target[0] - reported[0]),
                                 absolute_target[1] - reported[1]])
            used_optical = False
        else:
            return ControlTelemetry(*self._last_command, 0.0, 0.0, lead, False)

        # The Smith correction. `measured` is the error against where the mount
        # is *now*, but commands already issued will move it before the next one
        # lands. Subtracting that in-flight motion leaves only the error still
        # outstanding -- without this the integrator keeps accumulating an error
        # that is already being corrected, and the loop overshoots once per dead
        # time.
        in_flight = np.array([geo.wrap_pi(predicted_az - reported[0]),
                              predicted_el - reported[1]])
        error = measured - in_flight

        smoothed = self._low_pass(error, dt)
        self._integral = np.clip(self._integral + smoothed * dt,
                                 -self.integral_limit, self.integral_limit)

        # Feed-forward: where the target moves during the dead time. This term
        # does the bulk of the work during a fast pass -- feedback alone would
        # always trail by rate x lead, which at culmination is far larger than
        # the whole error budget.
        lead_az = target_rates[0] * lead
        lead_el = target_rates[1] * lead

        command_az = predicted_az + self.kp * smoothed[0] + self.ki * self._integral[0] + lead_az
        command_el = predicted_el + self.kp * smoothed[1] + self.ki * self._integral[1] + lead_el

        lo, hi = np.radians(self.cfg.el_limits_deg)
        command_az = float(geo.wrap_pi(command_az))
        command_el = float(np.clip(command_el, lo, hi))

        self.smith.issue(command_az, command_el)
        self._last_command = (command_az, command_el)
        return ControlTelemetry(command_az, command_el,
                                float(error[0]), float(error[1]), lead, used_optical)
