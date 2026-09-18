"""The live path: the REAL engine on camera-style frames, and the Mk2 wire."""
import numpy as np
import pytest

from fsoc_pat.hil.engine import ArraySource, LiveEngine, live_config
from fsoc_pat.hil.mk2 import Mk2Gimbal


# ---------------------------------------------------------------------------
# synthetic "camera": dark room, one blinking beacon, one steady bright lamp
# ---------------------------------------------------------------------------
def blob(img, u, v, amp, sigma=1.8):
    h, w = img.shape
    y, x = np.mgrid[0:h, 0:w]
    img += amp * np.exp(-((x - u) ** 2 + (y - v) ** 2) / (2 * sigma ** 2))


# camera-only mode: the operator aims the camera at the beacon, so the
# target sits near boresight -- inside the state machine's lock tolerance.
def camera_frames(n=150, fps=30.0, beacon_hz=3.0, beacon_uv=(322, 243),
                  lamp_uv=(420, 180), seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for i in range(n):
        t = i / fps
        img = rng.normal(160.0, 40.0, (480, 640))     # 12-bit-scale dark room
        on = (t * beacon_hz) % 1.0 < 0.5
        if on:
            blob(img, *beacon_uv, 2600.0)
        blob(img, *lamp_uv, 3400.0)                    # brighter, but steady
        frames.append(np.clip(img, 0, 4095).astype(np.uint16))
    return frames


@pytest.fixture(scope="module")
def locked_engine():
    """Run once, assert plenty: the full engine is a couple of seconds of CPU."""
    src = ArraySource(camera_frames(), fps=30.0)
    cfg = live_config(fov_deg=50.0, blink_hz=3.0)
    eng = LiveEngine(src, cfg, gimbal=None, ai_weights=None)
    recs = list(eng.run())
    return recs


def test_live_engine_locks_the_blinking_beacon(locked_engine):
    recs = locked_engine
    assert len(recs) == 150
    tail = recs[-30:]
    locked = [r for r in tail if r["locked"]]
    assert len(locked) > 20, "engine never held lock on the beacon"
    # locked on the BLINKING source, not the brighter steady lamp
    for r in locked:
        if r["bpx"] is not None:
            assert abs(r["bpx"][0] - 322) < 12 and abs(r["bpx"][1] - 243) < 12


def test_live_engine_measures_the_frequency(locked_engine):
    hz = [r["ehz"] for r in locked_engine[-30:]
          if r["ehz"] is not None and r["ehzc"] > 0.2]
    assert hz, "no measured frequency reported"
    assert abs(np.median(hz) - 3.0) < 0.3


def test_live_telemetry_never_invents_ground_truth(locked_engine):
    for r in locked_engine:
        for banned in ("err_urad", "in_fov", "on_decoy"):
            assert banned not in r
        assert {"state", "n_det", "mod", "ehz", "proc_ms", "cmd"} <= set(r)


def test_camera_only_mode_reports_but_does_not_pretend_to_move(locked_engine):
    # no gimbal attached: reported pointing stays boresight, laser never on
    assert all(r["laser"] is False for r in locked_engine)


# ---------------------------------------------------------------------------
# Mk2 wire protocol
# ---------------------------------------------------------------------------
def test_mk2_dry_run_formats_the_v2_protocol():
    g = Mk2Gimbal(None, dry_run=True, min_interval_s=0.0)
    g.command(np.radians(2.0), np.radians(-1.0))
    line = g.sent[-1]
    assert line.startswith("P") and " T" in line and "." not in line
    pan = int(line[1:line.index(" ")])
    assert pan == int(round(np.radians(2.0) * g.steps_per_rad[0]))
    g.laser(True); g.vibration(True); g.fine(0.0, 0.0)
    assert g.sent[-3:] == ["L1", "V1", "p90 t90"]


def test_mk2_safety_envelope():
    g = Mk2Gimbal(None, dry_run=True, min_interval_s=0.0, max_step_per_cmd=100)
    g.command(np.radians(45.0), 0.0)              # huge move
    pan = int(g.sent[-1][1:g.sent[-1].index(" ")])
    assert pan == 100, "single command exceeded the step cap"
    g2 = Mk2Gimbal(None, dry_run=True, min_interval_s=10.0)
    assert g2.command(0.01, 0.0) is True
    assert g2.command(0.02, 0.0) is False, "rate limiter did not hold"


def test_mk2_fine_stage_respects_firmware_limits():
    g = Mk2Gimbal(None, dry_run=True)
    g.fine(10.0, -10.0)                            # absurd residual
    assert g.sent[-1] == "p160 t40"                # clamped to soft limits
