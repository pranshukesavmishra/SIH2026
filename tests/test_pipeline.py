"""End-to-end closed loop: short, but on the real system with no mocks."""
import numpy as np
import pytest

from fsoc_pat.config import SimConfig
from fsoc_pat.runner import run_scenario


def test_closed_loop_acquires_and_tracks_a_static_beacon():
    cfg = SimConfig.load("scenarios/static_easy.yaml")
    report, tracker = run_scenario(cfg, duration_s=15.0)
    assert report.acquisition_time_s is not None and report.acquisition_time_s < 5.0
    assert report.lock_retention_pct > 90.0
    assert report.decoy_locked_frames == 0
    assert report.tracking_error_urad["mean"] < 500.0


def test_closed_loop_follows_a_leo_pass():
    cfg = SimConfig.load("scenarios/leo_pass_nominal.yaml")
    report, _ = run_scenario(cfg, duration_s=20.0)
    assert report.acquisition_time_s is not None and report.acquisition_time_s < 8.0
    assert report.lock_retention_pct > 80.0
    assert report.beacon_in_fov_pct > 90.0        # the coarse-stage contract
    assert report.decoy_locked_pct < 1.0


def test_decoys_are_never_preferred_to_the_modulated_beacon():
    cfg = SimConfig.load("scenarios/decoy_field.yaml")
    report, _ = run_scenario(cfg, duration_s=20.0)
    assert report.decoy_locked_frames == 0


def test_report_quantities_are_internally_consistent():
    cfg = SimConfig.load("scenarios/static_easy.yaml")
    report, tracker = run_scenario(cfg, duration_s=10.0)
    assert report.frames == len(tracker.telemetry)
    occupancy = sum(report.state_occupancy_pct.values())
    assert occupancy == pytest.approx(100.0, abs=0.01)
    assert 0.0 <= report.lock_retention_pct <= 100.0
