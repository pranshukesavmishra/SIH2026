"""
The coarse alignment system, assembled.

This is the object the problem statement actually asks for: something that
"autonomously detects, identifies, and continuously tracks a designated moving
target within a virtual scene by controlling a virtual camera viewport". It
owns a detector, a multi-target tracker, a spiral search and a controller, and
sequences them through the acquisition states a real terminal uses.

    SEARCH ---- candidate found ----> ACQUIRE
       ^                                 |
       |                          error small and stable
       |                                 v
    REACQUIRE <--- coast expired ---   TRACK
       ^                                 |
       |                            detections stop
       |                                 v
       +-------- local scan fails ---  COAST

The distinction between COAST and REACQUIRE matters. A beacon that blinks, or
scintillates, or is briefly occluded, disappears for a few frames at a time --
throwing away a good track for that would make the system unusable. COAST
keeps commanding the filter's prediction, betting that the target is still
where the model says. Only when that bet has clearly failed does REACQUIRE
start a small local spiral, and only when *that* fails does the system admit
it is lost and start over.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np

from . import geometry as geo
from .config import SimConfig
from .control import PointingController
from .detection import Detection, PointDetector
from .search import SpiralSearch
from .simulator import Frame
from .tracking import MultiTargetTracker, Track


class LockState(str, Enum):
    SEARCH = "SEARCH"
    ACQUIRE = "ACQUIRE"
    TRACK = "TRACK"
    COAST = "COAST"
    REACQUIRE = "REACQUIRE"


@dataclass
class TrackerTelemetry:
    """One frame of everything the metrics engine and the GUI need."""
    frame_index: int
    time_s: float
    state: LockState
    n_detections: int
    locked: bool           # holding a confirmed track (TRACK or coasting through a gap)
    detected: bool = False  # a fresh detection was associated this frame
    track_id: Optional[int] = None
    error_rad: Optional[float] = None          # boresight error, if a track exists
    truth_error_rad: Optional[float] = None    # scored against ground truth
    on_decoy: bool = False
    modulation_score: float = 0.0
    mode_probabilities: Tuple[float, float] = (0.5, 0.5)
    command: Optional[Tuple[float, float]] = None
    detection_snr: Optional[float] = None
    processing_ms: float = 0.0


class CoarseAlignmentTracker:
    """
    Closed-loop coarse alignment.

    Construct it from the same :class:`SimConfig` the simulator uses, then pass
    each frame to :meth:`update` and command the mount with what it returns --
    which is exactly the contract :meth:`Simulator.run` expects.
    """

    def __init__(self, cfg: SimConfig, fou_radius_deg: Optional[float] = None,
                 search_centre: Optional[Tuple[float, float]] = None,
                 cfar_k: float = 5.0, bandwidth_hz: float = 3.0,
                 lock_threshold_px: float = 8.0, lock_frames: int = 5,
                 coast_frames: int = 15, reacquire_frames: int = 90):
        self.cfg = cfg
        cam = cfg.camera
        self.dt = 1.0 / cam.frame_rate_hz
        self.focal_px = geo.focal_px(cam.fov_deg, cam.width)
        self.width, self.height = cam.width, cam.height

        seeing = cfg.turbulence.seeing_blur_px if cfg.turbulence.enabled else 0.0
        psf_sigma = float(np.hypot(cam.psf_sigma_px, seeing))
        self.detector = PointDetector(psf_sigma=psf_sigma, cfar_k=cfar_k)

        blink = next((b.blink_hz for b in cfg.beacons if not b.is_decoy), 0.0)
        self.tracker = MultiTargetTracker(
            pointing_jitter_urad=self.disturbance_jitter_urad(cfg),
            focal_px=self.focal_px, width=cam.width, height=cam.height,
            frame_rate_hz=cam.frame_rate_hz,
            encoder_noise_urad=cfg.gimbal.encoder_noise_urad,
            beacon_blink_hz=blink)

        az0, el0 = np.radians(cfg.initial_pointing_deg)
        self.search_centre = search_centre if search_centre is not None else (az0, el0)
        if fou_radius_deg is None:
            fou_radius_deg = cfg.acquisition_fou_deg
        self.search = SpiralSearch(fou_radius_deg=fou_radius_deg, fov_deg=cam.fov_deg,
                                   aspect=cam.height / cam.width)
        self.controller = PointingController(cfg.gimbal, cam.frame_rate_hz,
                                             az0=az0, el0=el0, bandwidth_hz=bandwidth_hz)

        self.lock_threshold = float(geo.px_to_urad(lock_threshold_px, self.focal_px) * 1e-6)
        self.lock_frames = int(lock_frames)
        self.coast_frames = int(coast_frames)
        self.reacquire_frames = int(reacquire_frames)

        self.tracker.set_expectation(self.search_centre[0], self.search_centre[1],
                                     np.radians(fou_radius_deg))
        self.fou_radius_rad = float(np.radians(fou_radius_deg))
        # Once locked the prior is tightened to roughly a third of the field of
        # view and slid along with the track's own prediction, so it rejects
        # clutter drifting into frame without pulling against the real target.
        self.locked_prior_sigma = float(np.radians(cam.fov_deg) / 3.0)

        self.state = LockState.SEARCH
        self.telemetry: List[TrackerTelemetry] = []
        self._locked_id: Optional[int] = None
        self._frames_in_tolerance = 0
        self._frames_coasting = 0
        self._frames_reacquiring = 0
        self.acquisition_frame: Optional[int] = None

    @staticmethod
    def disturbance_jitter_urad(cfg: SimConfig) -> float:
        """
        Expected one-sigma pointing disturbance, in microradians.

        Taken from the scenario because the tracker is entitled to know the
        environment it was commissioned for -- a real terminal is specified
        against a vibration profile and a seeing budget. A system that had to
        discover this in the field would estimate it from its own innovation
        sequence instead; the structure here is the same, only the source of
        the number differs.
        """
        variance = 0.0
        if cfg.turbulence.enabled:
            variance += cfg.turbulence.tilt_rms_urad ** 2
        if cfg.vibration.enabled:
            variance += sum(mode[1] ** 2 for mode in cfg.vibration.modes)
            variance += cfg.vibration.broadband_rms_urad ** 2
        return float(np.sqrt(variance))

    # ---- helpers --------------------------------------------------------
    def _optical_error(self, detection: Detection, cam_az: float, cam_el: float):
        """
        Beacon offset from the boresight, as measured in the image.

        This is the error signal a tracking sensor exists to provide: it comes
        from where the light landed, so it does not inherit encoder bias.
        """
        az, el = geo.unproject(detection.u, detection.v, cam_az, cam_el,
                               self.focal_px, self.width, self.height)
        return float(geo.wrap_pi(az - cam_az)), float(el - cam_el)

    def _fresh(self, track: Optional[Track]) -> bool:
        return track is not None and track.misses == 0 and track.last_detection is not None

    # ---- main entry point ------------------------------------------------
    def update(self, frame: Frame) -> Tuple[float, float]:
        import time
        started = time.perf_counter()

        cam_az, cam_el = frame.pointing_reported
        detections = [] if frame.dropped else self.detector.detect(frame.image)
        self.tracker.update(detections, cam_az, cam_el, self.dt)

        primary = self.tracker.primary()
        if self._locked_id is not None:
            held = next((t for t in self.tracker.tracks if t.track_id == self._locked_id), None)
            # Stay with the locked track unless it is gone or another track has
            # become clearly better. Swapping on a marginal score difference is
            # how a tracker ends up oscillating between a beacon and a decoy.
            if held is not None and (primary is None
                                     or held.score(True) > primary.score(True) - 0.15):
                primary = held
            else:
                self._locked_id = None

        if primary is not None and self.state in (LockState.TRACK, LockState.COAST):
            self.tracker.set_expectation(*primary.imm.predict_ahead(self.dt),
                                         self.locked_prior_sigma)
        elif self.state is LockState.SEARCH:
            self.tracker.set_expectation(cam_az, cam_el, self.fou_radius_rad)

        command = self._run_state_machine(primary, cam_az, cam_el)
        self._record(frame, primary, detections, command,
                     (time.perf_counter() - started) * 1e3)
        return command

    def _run_state_machine(self, primary: Optional[Track],
                           cam_az: float, cam_el: float) -> Tuple[float, float]:
        if primary is None:
            return self._search_or_lose()

        optical = None
        if self._fresh(primary):
            optical = self._optical_error(primary.last_detection, cam_az, cam_el)
            self._frames_coasting = 0
        else:
            self._frames_coasting += 1

        if self._frames_coasting > self.coast_frames:
            return self._search_or_lose()

        error = (float(np.hypot(*optical)) if optical is not None
                 else float(geo.angular_separation(*primary.angles, cam_az, cam_el)))

        if error < self.lock_threshold:
            self._frames_in_tolerance += 1
        else:
            self._frames_in_tolerance = 0

        if self._frames_coasting > 0:
            self.state = LockState.COAST
        elif self._frames_in_tolerance >= self.lock_frames:
            if self.state is not LockState.TRACK:
                self.state = LockState.TRACK
                self._locked_id = primary.track_id
            self._locked_id = primary.track_id
        else:
            self.state = LockState.ACQUIRE

        self._frames_reacquiring = 0
        telemetry = self.controller.update(
            reported=(cam_az, cam_el), dt=self.dt,
            optical_error=optical,
            absolute_target=primary.angles if optical is None else None,
            target_rates=primary.imm.rates)
        return telemetry.command_az, telemetry.command_el

    def _search_or_lose(self) -> Tuple[float, float]:
        """No usable track: scan locally for a while, then start over."""
        self._frames_in_tolerance = 0
        self._locked_id = None

        if self.state in (LockState.TRACK, LockState.COAST, LockState.REACQUIRE) \
                and self._frames_reacquiring < self.reacquire_frames:
            self.state = LockState.REACQUIRE
            self._frames_reacquiring += 1
        else:
            if self.state is not LockState.SEARCH:
                self.search.reset()
            self.state = LockState.SEARCH
            self._frames_reacquiring = 0
            self._frames_coasting = 0

        self.search.advance()
        return self.search.command(*self.search_centre)

    def _record(self, frame: Frame, primary: Optional[Track],
                detections: List[Detection], command, elapsed_ms: float) -> None:
        truth = frame.primary
        truth_error = None
        on_decoy = False
        if primary is not None and truth is not None:
            est_az, est_el = primary.angles
            truth_error = float(geo.angular_separation(est_az, est_el, truth.az, truth.el))
            # Locked onto a decoy if some decoy is closer to the estimate than
            # the real beacon is. Scored honestly against ground truth, never
            # against the tracker's own opinion of itself.
            for other in frame.targets:
                if other.is_decoy:
                    d = float(geo.angular_separation(est_az, est_el, other.az, other.el))
                    if d < truth_error:
                        on_decoy = True

        # A pulsed beacon is dark for half of every cycle, and scintillation
        # blanks it at random. Coasting through those gaps on a confirmed track
        # is exactly what the filter is for, so it counts as holding lock --
        # scoring only TRACK frames would report a 4 Hz beacon as 50% lost
        # while the system was in fact tracking it perfectly throughout.
        locked = (primary is not None and primary.confirmed
                  and self.state in (LockState.TRACK, LockState.COAST))
        if self.state is LockState.TRACK and self.acquisition_frame is None:
            self.acquisition_frame = frame.index

        self.telemetry.append(TrackerTelemetry(
            frame_index=frame.index, time_s=frame.time_s, state=self.state,
            n_detections=len(detections), locked=locked,
            detected=self._fresh(primary),
            track_id=primary.track_id if primary else None,
            error_rad=None if primary is None else float(
                geo.angular_separation(*primary.angles, *frame.pointing_true)),
            truth_error_rad=truth_error, on_decoy=on_decoy,
            modulation_score=primary.modulation_score if primary else 0.0,
            mode_probabilities=tuple(primary.imm.mu) if primary else (0.5, 0.5),
            command=command,
            detection_snr=primary.last_detection.snr
            if primary and primary.last_detection else None,
            processing_ms=elapsed_ms))
