"""
The real engine on real frames: CoarseAlignmentTracker driven by a camera.

This is the piece that makes the transfer claim true by construction:
the SAME ``CoarseAlignmentTracker`` -- CFAR detector, blink-signature
identification with adaptive frequency estimation, IMM Kalman filter,
Smith-predictor control, AI verifier -- that produces every simulated
number, fed with live camera frames instead of rendered ones. Nothing in
the tracking path knows the difference; only the frame source and the
actuator change.

Frame sources, in order of how much hardware they need:

    ArraySource     numpy frames from memory -- what the tests use
    VideoSource     a recorded video file -- develop with zero hardware
    CameraSource    a live UVC camera (hil.rig.UsbCamera)

Honesty contract, non-negotiable: the real world has no ground truth.
``LiveFrame.primary`` is None, so every truth-referenced metric
(pointing error vs beacon, in-FOV, wrong-target) is simply absent from
live telemetry rather than invented. What IS emitted is measured:
detections, SNR, blink modulation, the measured blink frequency, the
filter's target-offset-from-boresight, state, and processing time.
"""
from __future__ import annotations

import time
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np

from .. import geometry as geo
from ..config import SimConfig
from ..pipeline import CoarseAlignmentTracker, LockState
from .rig import LiveFrame


# ---------------------------------------------------------------------------
# frame sources
# ---------------------------------------------------------------------------
class ArraySource:
    """Frames straight from memory, at a nominal rate. Used by the tests."""

    def __init__(self, frames: List[np.ndarray], fps: float = 30.0):
        self.frames = frames
        self.fps = float(fps)
        self._i = 0

    def read(self) -> Optional[Tuple[np.ndarray, float]]:
        if self._i >= len(self.frames):
            return None
        img = self.frames[self._i]
        t = self._i / self.fps
        self._i += 1
        return img, t

    def release(self) -> None:
        pass


class VideoSource:
    """A recorded video file: the zero-hardware development path."""

    def __init__(self, path: str):
        import cv2
        self._cv2 = cv2
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise SystemExit(f"cannot open video: {path}")
        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS)) or 30.0
        self._i = 0

    def read(self) -> Optional[Tuple[np.ndarray, float]]:
        ok, frame = self.cap.read()
        if not ok:
            return None
        gray = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2GRAY)
        t = self._i / self.fps
        self._i += 1
        return (gray.astype(np.uint16) << 4), t

    def release(self) -> None:
        self.cap.release()


class CameraSource:
    """A live camera, timestamped by the wall clock (real dt, not assumed)."""

    def __init__(self, index: int = 0, width: int = 640, height: int = 480,
                 exposure: Optional[float] = None, fps: float = 30.0):
        from .rig import UsbCamera
        self.cam = UsbCamera(index, width, height, exposure=exposure)
        self.fps = float(fps)
        self._t0: Optional[float] = None

    def read(self) -> Optional[Tuple[np.ndarray, float]]:
        img = self.cam.read()
        if img is None:
            return None
        now = time.monotonic()
        if self._t0 is None:
            self._t0 = now
        return img, now - self._t0

    def release(self) -> None:
        self.cam.release()


# ---------------------------------------------------------------------------
# configuration for real optics
# ---------------------------------------------------------------------------
def live_config(fov_deg: float = 50.0, width: int = 640, height: int = 480,
                fps: float = 30.0, blink_hz: float = 4.0,
                latency_ms: float = 120.0) -> SimConfig:
    """
    A SimConfig describing the REAL optics, not a simulated sky.

    Defaults describe a typical UVC webcam; `hardware/calibration.yaml`
    values override them once measured (measure, never assume). Turbulence
    and injected noise are off -- the real world supplies its own.
    """
    cfg = SimConfig()
    cfg.camera.fov_deg = float(fov_deg)
    cfg.camera.width = int(width)
    cfg.camera.height = int(height)
    cfg.camera.frame_rate_hz = float(fps)
    cfg.turbulence.enabled = False
    cfg.vibration.enabled = False
    cfg.gimbal.command_latency_ms = float(latency_ms)
    cfg.gimbal.encoder_noise_urad = 0.0     # steppers: no encoder echo at all
    cfg.initial_pointing_deg = [0.0, 0.0]
    cfg.acquisition_fou_deg = min(2.0, fov_deg / 4.0)
    cfg.beacons = cfg.beacons[:1]
    cfg.beacons[0].blink_hz = float(blink_hz)   # 0.0 = adaptive blind mode
    return cfg


# ---------------------------------------------------------------------------
# the live engine
# ---------------------------------------------------------------------------
class LiveEngine:
    """
    One step per camera frame: read, track, (optionally) steer, report.

    ``gimbal=None`` is camera-only mode: the full detection/identification/
    filtering chain runs and the dashboard shows everything measurable, and
    the pointing commands the controller computes are reported but not
    applied -- with a static camera, pretending the mount moved would poison
    the tracker's angle bookkeeping. With a real Mk2 attached the camera
    rides the mount, so commands are applied and the loop closes.
    """

    def __init__(self, source, cfg: Optional[SimConfig] = None,
                 gimbal=None, cfar_k: float = 6.0,
                 ai_weights: Optional[str] = "auto",
                 steer_states=(LockState.TRACK, LockState.COAST)):
        self.source = source
        self.cfg = cfg or live_config(fps=getattr(source, "fps", 30.0))
        self.gimbal = gimbal
        self.tracker = CoarseAlignmentTracker(self.cfg, cfar_k=cfar_k,
                                              ai_weights=ai_weights)
        self.steer_states = tuple(steer_states)
        self.index = 0
        self.laser_on = False
        self.last_command: Tuple[float, float] = (0.0, 0.0)
        self._last_image: Optional[np.ndarray] = None
        self._last_reported: Tuple[float, float] = (0.0, 0.0)

    # ---- one frame -----------------------------------------------------
    def step(self) -> Optional[Dict]:
        got = self.source.read()
        if got is None:
            return None
        image, t = got
        self._last_image = image
        reported = (self.gimbal.reported_pointing() if self.gimbal is not None
                    else (0.0, 0.0))
        self._last_reported = reported
        frame = LiveFrame(index=self.index, time_s=float(t), image=image,
                          pointing_true=reported, pointing_reported=reported)
        started = time.perf_counter()
        cmd = self.tracker.update(frame)
        self.last_command = (float(cmd[0]), float(cmd[1]))

        state = self.tracker.state
        if self.gimbal is not None:
            if state in self.steer_states:
                self.gimbal.command(*self.last_command)
                if not self.laser_on:            # laser gated behind lock
                    self.gimbal.laser(True)
                    self.laser_on = True
            elif self.laser_on:
                self.gimbal.laser(False)
                self.laser_on = False

        self.index += 1
        return self._telemetry(frame)

    def run(self) -> Iterator[Dict]:
        while True:
            rec = self.step()
            if rec is None:
                return
            yield rec

    # ---- telemetry -----------------------------------------------------
    def _telemetry(self, frame: LiveFrame) -> Dict:
        """Same keys as the recorded-replay exporter, so the dashboard's
        draw path carries over; truth-referenced keys are absent, never
        fabricated."""
        t = self.tracker.telemetry[-1]
        primary = next((tr for tr in self.tracker.tracker.tracks
                        if tr.track_id == t.track_id), None)
        bpx = None
        if primary is not None:
            az, el = primary.angles
            u, v, vis = geo.project(az, el, *frame.pointing_reported,
                                    self.tracker.focal_px,
                                    self.tracker.width, self.tracker.height)
            if vis:
                bpx = [round(float(u), 1), round(float(v), 1)]
        # the filter's target offset from boresight: measured, no truth needed
        off = None if t.error_rad is None else round(t.error_rad * 1e6, 1)
        return {
            "i": t.frame_index, "t": round(t.time_s, 3),
            "state": t.state.value, "locked": bool(t.locked),
            "detected": bool(t.detected), "n_det": int(t.n_detections),
            "off_urad": off,
            "mod": round(float(t.modulation_score), 4),
            "ai": None if t.ai_score is None else round(float(t.ai_score), 4),
            "ehz": None if t.est_blink_hz is None
                   else round(float(t.est_blink_hz), 2),
            "ehzc": round(float(t.est_blink_conf), 3),
            "snr_db": None if t.detection_snr is None
                      else round(float(t.detection_snr), 2),
            "proc_ms": round(float(t.processing_ms), 2),
            "bpx": bpx,
            "cmd": [round(np.degrees(self.last_command[0]), 3),
                    round(np.degrees(self.last_command[1]), 3)],
            "laser": self.laser_on,
        }

    # ---- annotated preview --------------------------------------------
    def annotate_jpeg(self, image: np.ndarray, rec: Dict,
                      quality: int = 70) -> bytes:
        import cv2
        disp = cv2.cvtColor((image >> 4).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        cam_az, cam_el = self._last_reported
        for tr in self.tracker.tracker.tracks:
            az, el = tr.angles
            u, v, vis = geo.project(az, el, cam_az, cam_el, self.tracker.focal_px,
                                    self.tracker.width, self.tracker.height)
            if vis:
                cv2.circle(disp, (int(u), int(v)), 14, (60, 180, 180), 1)
        if rec.get("bpx"):
            u, v = int(rec["bpx"][0]), int(rec["bpx"][1])
            colour = (80, 220, 120) if rec["locked"] else (60, 170, 240)
            cv2.circle(disp, (u, v), 24, colour, 2)
            cv2.drawMarker(disp, (u, v), colour, cv2.MARKER_CROSS, 18, 1)
        cv2.putText(disp, rec["state"], (10, 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (90, 220, 255), 2)
        ok, buf = cv2.imencode(".jpg", disp,
                               [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else b""
