"""
The simulation loop: steps every component forward and emits frames with
ground truth attached.

Ordering inside a step is deliberate. Disturbances advance first, then the
gimbal responds to whatever command was issued last frame, and only then is
the frame rendered. That one-frame gap between commanding and seeing is not
an artefact — it is the sensing latency any real tracker has to close around,
and removing it would make every controller look better than it is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

import numpy as np

from . import geometry as geo
from .beacon import Beacon
from .camera import VirtualCamera
from .config import SimConfig
from .disturbance import Turbulence, Vibration
from .optics import splat_gaussian
from .scene import Scene


@dataclass
class TargetTruth:
    """Where a target really was, for scoring. Never shown to the tracker."""
    name: str
    is_decoy: bool
    az: float                 # geometric direction
    el: float
    az_apparent: float        # including turbulent tip/tilt: where photons land
    el_apparent: float
    u: float                  # pixel position, apparent
    v: float
    in_frame: bool
    range_km: float
    signal_e: float           # integrated signal in the exposure
    snr: float


@dataclass
class Frame:
    index: int
    time_s: float
    image: np.ndarray                       # uint16, shape (H, W)
    pointing_true: Tuple[float, float]      # optical axis, including vibration
    pointing_reported: Tuple[float, float]  # what the encoders say
    dropped: bool
    targets: List[TargetTruth] = field(default_factory=list)
    glint: Optional[Tuple[float, float, float]] = None

    @property
    def primary(self) -> Optional[TargetTruth]:
        """The one non-decoy target, if there is exactly one."""
        real = [t for t in self.targets if not t.is_decoy]
        return real[0] if real else None


class Simulator:
    """
    One scenario, stepped frame by frame.

    ``simulator.step(command)`` takes the pointing command a controller wants
    to issue and returns the next frame. Passing ``None`` leaves the gimbal
    where it is, which is how an open-loop or search-mode run is driven.
    """

    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.master_rng = np.random.default_rng(cfg.seed)
        # Independent streams so that changing one subsystem does not reshuffle
        # the random draws of another; scenarios stay comparable across edits.
        seeds = self.master_rng.integers(0, 2 ** 31 - 1, 6)
        self.rng_scene = np.random.default_rng(seeds[0])
        self.rng_detector = np.random.default_rng(seeds[1])
        self.rng_turb = np.random.default_rng(seeds[2])
        self.rng_vib = np.random.default_rng(seeds[3])
        self.rng_beacon = np.random.default_rng(seeds[4])
        self.rng_events = np.random.default_rng(seeds[5])

        az0, el0 = np.radians(cfg.initial_pointing_deg)
        self.camera = VirtualCamera(cfg.camera, cfg.gimbal, az0, el0, self.rng_detector)
        self.scene = Scene(cfg.scene, cfg.camera, self.rng_scene)
        self.turbulence = Turbulence(cfg.turbulence, self.rng_turb)
        self.vibration = Vibration(cfg.vibration, self.rng_vib)
        self.beacons = [Beacon(b, self.rng_beacon) for b in cfg.beacons]

        self.dt = self.camera.dt
        self.index = -1
        self.time_s = 0.0

    # ---- properties ----------------------------------------------------
    @property
    def total_frames(self) -> int:
        return int(np.floor(self.cfg.duration_s * self.cfg.camera.frame_rate_hz))

    @property
    def focal_px(self) -> float:
        return self.camera.focal_px

    # ---- main loop -----------------------------------------------------
    def step(self, command: Optional[Tuple[float, float]] = None) -> Frame:
        if command is not None:
            self.camera.gimbal.command(command[0], command[1])

        self.index += 1
        self.time_s = self.index * self.dt

        self.turbulence.step(self.dt)
        self.vibration.step(self.dt)
        self.camera.gimbal.step(self.dt)

        vib = self.vibration.offset
        true_az = float(geo.wrap_pi(self.camera.gimbal.az + vib[0]))
        true_el = float(geo.clamp_elevation(self.camera.gimbal.el + vib[1]))

        dropped = (self.cfg.noise.enabled
                   and self.rng_events.random() < self.cfg.noise.frame_drop_probability)

        sigma = self.camera.psf_sigma(self.turbulence.blur_px)
        rate = self.camera.blank_frame()
        rate += self.scene.render_background(true_az, true_el)
        common_tilt = self.turbulence.tilt("__field__")
        self.scene.draw_point_sources(rate, true_az, true_el, sigma, tuple(common_tilt))

        targets = self._render_targets(rate, true_az, true_el, sigma)
        glint = self.scene.maybe_glint(rate, sigma, self.rng_events)

        image = self.camera.detector.expose(rate)
        if dropped:
            image = np.zeros_like(image)

        self._attach_snr(targets, rate, sigma)

        return Frame(index=self.index, time_s=self.time_s, image=image,
                     pointing_true=(true_az, true_el),
                     pointing_reported=self.camera.gimbal.reported_pointing(),
                     dropped=dropped, targets=targets, glint=glint)

    def run(self, controller=None) -> Iterator[Frame]:
        """
        Iterate the whole scenario.

        ``controller`` is any object with ``update(frame) -> (az, el) | None``.
        Passing ``None`` runs the scenario open loop, which is how the
        detection-only benchmarks are collected.
        """
        command = None
        for _ in range(self.total_frames):
            frame = self.step(command)
            command = controller.update(frame) if controller is not None else None
            yield frame

    # ---- internals -----------------------------------------------------
    def _render_targets(self, rate, cam_az, cam_el, sigma) -> List[TargetTruth]:
        cam = self.cfg.camera
        exposure_s = cam.exposure_ms / 1000.0
        out: List[TargetTruth] = []

        for beacon in self.beacons:
            az, el, range_km = beacon.state(self.time_s)
            tilt = self.turbulence.tilt(beacon.cfg.name)
            az_app, el_app = az + float(tilt[0]), el + float(tilt[1])

            signal_rate = (beacon.intensity(self.time_s, exposure_s, range_km)
                           * self.turbulence.scintillation())
            u, v, in_frame = geo.project(az_app, el_app, cam_az, cam_el,
                                         self.focal_px, cam.width, cam.height)
            if in_frame and signal_rate > 0.0:
                splat_gaussian(rate, u, v, signal_rate, sigma)

            out.append(TargetTruth(
                name=beacon.cfg.name, is_decoy=beacon.cfg.is_decoy,
                az=az, el=el, az_apparent=az_app, el_apparent=el_app,
                u=u, v=v, in_frame=in_frame, range_km=range_km,
                signal_e=signal_rate * exposure_s, snr=0.0))
        return out

    def _attach_snr(self, targets, rate, sigma) -> None:
        """
        Peak-pixel SNR of each target against the local background.

        Reported in the ground truth so that a detection miss can be judged
        against how detectable the target actually was, instead of being
        blamed on the detector by default.
        """
        cfg = self.cfg.camera
        exposure_s = cfg.exposure_ms / 1000.0
        peak_fraction = 1.0 / (2.0 * np.pi * sigma * sigma)
        for t in targets:
            if not t.in_frame:
                continue
            ui, vi = int(np.clip(t.u, 0, cfg.width - 1)), int(np.clip(t.v, 0, cfg.height - 1))
            total_e = rate[vi, ui] * exposure_s
            signal_e = t.signal_e * peak_fraction
            noise_e = np.sqrt(max(total_e, 1.0) + cfg.read_noise_e ** 2)
            t.snr = float(signal_e / noise_e)
