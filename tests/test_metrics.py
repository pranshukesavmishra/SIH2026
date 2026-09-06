"""The report must be an honest, pure function of the telemetry."""
import numpy as np
import pytest

from fsoc_pat.metrics import build_report
from fsoc_pat.pipeline import LockState, TrackerTelemetry


def _frame(i, state, locked, detected=True, err=100e-6, perr=500e-6,
           decoy=False, fov=True, ms=8.0, ndet=5):
    return TrackerTelemetry(
        frame_index=i, time_s=i / 30.0, state=state, n_detections=ndet,
        locked=locked, detected=detected, truth_error_rad=err if locked else None,
        pointing_error_rad=perr if locked else None, on_decoy=decoy,
        beacon_in_fov=fov, processing_ms=ms)


def test_empty_telemetry_yields_empty_report():
    r = build_report([], "x", 30.0)
    assert r.frames == 0 and r.acquisition_time_s is None


def test_mandatory_quantities_are_computed():
    tm = ([_frame(i, LockState.SEARCH, False, detected=False) for i in range(30)]
          + [_frame(30 + i, LockState.TRACK, True) for i in range(60)])
    r = build_report(tm, "t", 30.0, wall_time_s=3.0)
    assert r.frames == 90
    assert r.simulation_duration_s == pytest.approx(3.0)
    assert r.achieved_fps == pytest.approx(30.0)
    assert r.acquisition_time_s == pytest.approx(1.0)
    assert r.lock_retention_pct == pytest.approx(100 * 60 / 90)
    assert r.tracking_error_urad["mean"] == pytest.approx(100.0)
    assert r.pointing_error_urad["mean"] == pytest.approx(500.0)
    assert r.processing_ms["mean"] == pytest.approx(8.0)


def test_acquisition_time_is_first_track_frame_not_first_lock():
    """COAST counts as locked, but acquisition means reaching TRACK."""
    tm = ([_frame(0, LockState.SEARCH, False)]
          + [_frame(1, LockState.COAST, True)]
          + [_frame(2, LockState.TRACK, True)])
    assert build_report(tm, "t", 30.0).acquisition_time_s == pytest.approx(2 / 30.0)


def test_reacquisition_events_are_paired_correctly():
    tm = ([_frame(i, LockState.TRACK, True) for i in range(10)]
          + [_frame(10 + i, LockState.SEARCH, False) for i in range(15)]      # lost 0.5 s
          + [_frame(25 + i, LockState.TRACK, True) for i in range(10)]
          + [_frame(35 + i, LockState.SEARCH, False) for i in range(5)])      # never back
    r = build_report(tm, "t", 30.0)
    assert r.reacquisitions == 2
    assert r.reacquisition_mean_s == pytest.approx(0.5)
    assert r.never_recovered is True


def test_decoy_time_is_not_laundered_into_the_mean():
    tm = ([_frame(i, LockState.TRACK, True, decoy=False) for i in range(50)]
          + [_frame(50 + i, LockState.TRACK, True, decoy=True) for i in range(50)])
    r = build_report(tm, "t", 30.0)
    assert r.decoy_locked_frames == 50
    assert r.decoy_locked_pct == pytest.approx(50.0)


def test_percentiles_expose_transients_that_the_mean_hides():
    tm = [_frame(i, LockState.TRACK, True, perr=(10000e-6 if i < 5 else 100e-6))
          for i in range(100)]
    r = build_report(tm, "t", 30.0)
    assert r.pointing_error_urad["p50"] == pytest.approx(100.0)
    assert r.pointing_error_urad["max"] == pytest.approx(10000.0)
    assert r.pointing_error_urad["mean"] > 2 * r.pointing_error_urad["p50"]


def test_report_serialises_and_renders(tmp_path):
    tm = [_frame(i, LockState.TRACK, True) for i in range(30)]
    r = build_report(tm, "t", 30.0)
    r.to_json(str(tmp_path / "r.json"))
    text = r.to_text()
    assert "Acquisition time" in text and "Lock retention" in text
    import json
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["scenario_name"] == "t"
