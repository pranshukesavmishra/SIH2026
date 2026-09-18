"""
The virtual pan-tilt camera: a gimbal that cannot move instantly, and a
detector that cannot see perfectly.

The three things here that a naive simulator omits, and that dominate real
tracking performance:

  * rate and acceleration limits — the mount physically cannot follow a
    step command, so a controller that assumes it will always overshoot;
  * command latency — pointing commands take effect tens of milliseconds
    after they are issued, which is what turns a high-gain loop unstable;
  * encoder noise — the controller does not know exactly where it is pointing,
    only where the encoders say it is.

``true_pointing`` and ``reported_pointing`` are kept separate throughout.
Scoring against the reported value would flatter the tracker; the metrics
always use the true one.
"""
from __future__ import annotations

from collections import deque
from typing import Optional, Tuple

import numpy as np

from . import geometry as geo
from .config import CameraConfig, GimbalConfig


class Gimbal:
    """Rate- and acceleration-limited pan-tilt mount with command latency."""

    def __init__(self, cfg: GimbalConfig, az0: float, el0: float, rng: np.random.Generator):
        self.cfg = cfg
        self.rng = rng
        self.az, self.el = float(az0), float(el0)
        self.rate_az, self.rate_el = 0.0, 0.0
        self._target = (self.az, self.el)
        self._queue: deque = deque()
        self._clock = 0.0
        self.max_rate = np.radians(cfg.max_rate_deg_s)
        self.max_accel = np.radians(cfg.max_accel_deg_s2)
        self.latency_s = cfg.command_latency_ms / 1000.0

    def command(self, az: float, el: float) -> None:
        """Queue an absolute pointing command; it takes effect after latency."""
        self._queue.append((self._clock + self.latency_s, float(az), float(el)))

    def step(self, dt: float) -> None:
        self._clock += dt
        while self._queue and self._queue[0][0] <= self._clock:
            _, az, el = self._queue.popleft()
            self._target = (az, el)

        target_az, target_el = self._target
        self.az, self.rate_az = self._slew(self.az, self.rate_az,
                                           self.az + geo.wrap_pi(target_az - self.az), dt)
        self.el, self.rate_el = self._slew(self.el, self.rate_el, target_el, dt)

        lo, hi = np.radians(self.cfg.el_limits_deg)
        if not (lo <= self.el <= hi):
            self.el = float(np.clip(self.el, lo, hi))
            self.rate_el = 0.0
        if self.cfg.az_limits_deg:
            lo_a, hi_a = np.radians(self.cfg.az_limits_deg)
            if not (lo_a <= self.az <= hi_a):
                self.az = float(np.clip(self.az, lo_a, hi_a))
                self.rate_az = 0.0
        self.az = float(geo.wrap_pi(self.az))

    def _slew(self, position, rate, target, dt):
        """
        One axis of a trapezoidal profile.

        The braking speed is the discrete-time solution of
        ``v dt + v^2 / 2a = |e|`` -- travel one full step at v, then brake at
        a, and arrive exactly:

            v = -a dt / 2 + sqrt((a dt / 2)^2 + 2 a |e|)

        The continuous-time form ``sqrt(2a|e|)`` commits to one step of travel
        it cannot brake away and overshoots by ~5 mrad on a large slew; a
        previous patch subtracted half a step of acceleration from it, which
        fixed the overshoot but created a ~145 urad deadband where the
        commanded velocity was zero and the mount parked short of every
        command it was given. The exact form has neither problem, and the
        additional ``|e| / dt`` cap lands the final sub-step exactly on the
        setpoint.
        """
        error = target - position
        half_step = 0.5 * self.max_accel * dt
        stopping = -half_step + np.sqrt(half_step ** 2
                                        + 2.0 * self.max_accel * abs(error))
        desired = np.sign(error) * min(self.max_rate, stopping, abs(error) / dt)
        dv = np.clip(desired - rate, -self.max_accel * dt, self.max_accel * dt)
        rate = rate + dv
        rate = float(np.clip(rate, -self.max_rate, self.max_rate))
        return position + rate * dt, rate

    def snapshot(self):
        """Cheap state capture, so a controller can roll the model forward."""
        return (self.az, self.el, self.rate_az, self.rate_el,
                self._target, list(self._queue), self._clock)

    def restore(self, state) -> None:
        (self.az, self.el, self.rate_az, self.rate_el,
         self._target, queue, self._clock) = state
        self._queue = deque(queue)

    @property
    def true_pointing(self) -> Tuple[float, float]:
        return self.az, self.el

    def reported_pointing(self) -> Tuple[float, float]:
        """What the encoders claim, which is what a controller actually gets."""
        noise = self.cfg.encoder_noise_urad * 1e-6
        return (self.az + self.rng.normal() * noise,
                self.el + self.rng.normal() * noise)


class Detector:
    """Photon-to-digital-number conversion, with the noise sources that matter."""

    def __init__(self, cfg: CameraConfig, rng: np.random.Generator):
        self.cfg = cfg
        self.rng = rng
        self.max_dn = (1 << cfg.bit_depth) - 1
        n_hot = int(cfg.hot_pixel_fraction * cfg.width * cfg.height)
        self._hot = (rng.integers(0, cfg.height, n_hot), rng.integers(0, cfg.width, n_hot))
        self._hot_rate = rng.uniform(5.0, 60.0, n_hot) * cfg.dark_current_e_per_s

    def expose(self, rate_image: np.ndarray) -> np.ndarray:
        """
        Integrate an electrons/second image into a digital frame.

        Shot noise is Poisson on the accumulated signal, so bright regions are
        noisier in absolute terms and quieter in relative terms — the reason a
        faint beacon against bright cloud is much harder than the raw contrast
        ratio suggests.
        """
        cfg = self.cfg
        exposure_s = cfg.exposure_ms / 1000.0

        electrons = rate_image * exposure_s
        electrons = electrons + cfg.dark_current_e_per_s * exposure_s
        if len(self._hot_rate):
            electrons[self._hot] += self._hot_rate * exposure_s

        # Shot noise. Above ~25 electrons the Poisson distribution is
        # indistinguishable from a Gaussian of the same variance, and the
        # Gaussian is an order of magnitude cheaper to sample -- which is what
        # keeps the simulator running faster than real time on a laptop.
        electrons = np.clip(electrons, 0.0, None)
        faint = electrons < 25.0
        shot = electrons + np.sqrt(electrons) * self.rng.standard_normal(electrons.shape)
        if faint.any():
            shot[faint] = self.rng.poisson(electrons[faint])
        electrons = shot + self.rng.normal(0.0, cfg.read_noise_e, electrons.shape)
        electrons = np.clip(electrons, 0.0, cfg.full_well_e)

        dn = np.round(electrons / cfg.full_well_e * self.max_dn)
        return np.clip(dn, 0, self.max_dn).astype(np.uint16)


class VirtualCamera:
    """Gimbal plus detector, and the PSF width they share."""

    def __init__(self, cam_cfg: CameraConfig, gim_cfg: GimbalConfig,
                 az0: float, el0: float, rng: np.random.Generator):
        self.cfg = cam_cfg
        self.gimbal = Gimbal(gim_cfg, az0, el0, rng)
        self.detector = Detector(cam_cfg, rng)
        self.focal_px = geo.focal_px(cam_cfg.fov_deg, cam_cfg.width)
        self.dt = 1.0 / cam_cfg.frame_rate_hz

    def psf_sigma(self, seeing_blur_px: float = 0.0) -> float:
        """Optical PSF and atmospheric seeing add in quadrature."""
        return float(np.hypot(self.cfg.psf_sigma_px, seeing_blur_px))

    def blank_frame(self) -> np.ndarray:
        return np.zeros((self.cfg.height, self.cfg.width), dtype=np.float32)
