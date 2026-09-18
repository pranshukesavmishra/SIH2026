"""
The rig detector must find what the mission detector cannot, and refuse
what brightness alone would tempt it into.

These tests encode the three failures actually observed on the bench:
a blazing flashlight producing zero detections, sensor grain producing
two dozen, and a steady lamp being indistinguishable from a beacon.
"""
import numpy as np
import pytest

from fsoc_pat.hil.rig_detect import (BlinkIdentifier, LockController,
                                     RigBeaconDetector)

RNG = np.random.default_rng(7)
W, H = 320, 240
FPS = 30.0


def _frame(noise_level: float = 8.0) -> np.ndarray:
    """A dark frame with realistic sensor grain."""
    return np.clip(RNG.normal(noise_level, 4.0, (H, W)), 0, 255).astype(np.uint8)


def _add_blob(frame: np.ndarray, u: int, v: int, radius: int = 12,
              peak: float = 255.0) -> np.ndarray:
    """A saturated extended source -- what a phone flashlight actually is."""
    yy, xx = np.ogrid[:frame.shape[0], :frame.shape[1]]
    d2 = (xx - u) ** 2 + (yy - v) ** 2
    blob = peak * np.exp(-d2 / (2.0 * radius ** 2))
    return np.clip(frame.astype(float) + blob, 0, 255).astype(np.uint8)


def _run(frames, blink_hz=4.0, **kw):
    det = RigBeaconDetector()
    ident = BlinkIdentifier(blink_hz=blink_hz, min_samples=20, **kw)
    lock = LockController(confirm_frames=5)
    states = []
    for i, frame in enumerate(frames):
        blobs = det.detect(frame)
        ident.update(blobs, frame, now=i / FPS)
        states.append(lock.update(ident.best()))
    return ident, lock, states


# ---- detection ---------------------------------------------------------
def test_finds_the_saturated_blob_the_point_detector_erases():
    """The bench failure: a bright flashlight yielding zero detections."""
    frame = _add_blob(_frame(), 160, 120, radius=14)
    blobs = RigBeaconDetector().detect(frame)
    assert blobs, "a saturated flashlight must be detected"
    assert abs(blobs[0].u - 160) < 6 and abs(blobs[0].v - 120) < 6


def test_dark_frame_yields_no_detections():
    """The other bench failure: 24 detections on empty sensor grain."""
    for _ in range(10):
        assert RigBeaconDetector().detect(_frame()) == []


def test_grain_never_clears_the_absolute_floor():
    """Even an unusually noisy dark frame must stay silent."""
    noisy = np.clip(RNG.normal(35.0, 18.0, (H, W)), 0, 255).astype(np.uint8)
    assert RigBeaconDetector().detect(noisy) == []


# ---- identification ----------------------------------------------------
def test_blinking_beacon_locks():
    frames = []
    for i in range(120):
        lit = (np.sin(2 * np.pi * 4.0 * i / FPS) > 0)
        f = _frame()
        frames.append(_add_blob(f, 200, 100) if lit else f)
    ident, lock, states = _run(frames)

    assert lock.state == LockController.LOCKED
    best = ident.best()
    assert best is not None and best.score > 0.3
    assert best.dominant_hz == pytest.approx(4.0, abs=1.0)
    assert abs(best.u - 200) < 15 and abs(best.v - 100) < 15


def test_steady_lamp_is_rejected_however_bright():
    """Brightness is not identity: an unmodulated source must never lock."""
    frames = [_add_blob(_frame(), 200, 100, radius=14) for _ in range(120)]
    ident, lock, states = _run(frames)

    assert lock.state == LockController.SEARCHING
    assert ident.best() is None
    assert LockController.LOCKED not in states


def test_wrong_blink_rate_is_rejected():
    """A 1 Hz flicker is not the 4 Hz beacon."""
    frames = []
    for i in range(150):
        lit = (np.sin(2 * np.pi * 1.0 * i / FPS) > 0)
        f = _frame()
        frames.append(_add_blob(f, 200, 100) if lit else f)
    _, lock, states = _run(frames, blink_hz=4.0)
    assert LockController.LOCKED not in states


def test_empty_scene_never_locks():
    _, lock, states = _run([_frame() for _ in range(120)])
    assert lock.state == LockController.SEARCHING
    assert set(states) == {LockController.SEARCHING}


def test_beacon_wins_against_a_steady_distractor():
    """A steady lamp in frame must not stop the blinking beacon locking."""
    frames = []
    for i in range(120):
        f = _add_blob(_frame(), 60, 60, radius=14)          # steady distractor
        if np.sin(2 * np.pi * 4.0 * i / FPS) > 0:
            f = _add_blob(f, 240, 160)                       # the beacon
        frames.append(f)
    ident, lock, _ = _run(frames)

    assert lock.state == LockController.LOCKED
    best = ident.best()
    assert abs(best.u - 240) < 20 and abs(best.v - 160) < 20


# ---- lock hysteresis ---------------------------------------------------
def test_lock_survives_a_brief_dropout():
    lock = LockController(confirm_frames=3, drop_frames=10)

    class T:
        track_id, score = 1, 0.9

    for _ in range(3):
        lock.update(T())
    assert lock.state == LockController.LOCKED
    for _ in range(8):
        lock.update(None)
    assert lock.state == LockController.LOCKED, "blink-off must not drop lock"
    for _ in range(5):
        lock.update(None)
    assert lock.state == LockController.SEARCHING


def test_single_good_frame_does_not_lock():
    lock = LockController(confirm_frames=5)

    class T:
        track_id, score = 1, 0.9

    assert lock.update(T()) == LockController.CONFIRMING
