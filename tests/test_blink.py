"""The adaptive blink-frequency estimator: measured, not assumed."""
import numpy as np
import pytest

from fsoc_pat.tracking import (MultiTargetTracker, estimate_blink_frequency,
                               goertzel_power)

FPS = 30.0


def square_wave(hz, n=90, fps=FPS, phase=0.0, amplitude=1.0, duty=0.5,
                noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fps
    frac = (t * hz + phase) % 1.0
    x = amplitude * (frac < duty).astype(float)
    return x + rng.normal(0.0, noise, n)


@pytest.mark.parametrize("hz", [1.0, 2.5, 4.0, 6.5, 9.0, 12.0])
def test_recovers_frequency_across_the_band(hz):
    hz_est, conf = estimate_blink_frequency(square_wave(hz), FPS)
    assert hz_est is not None
    assert abs(hz_est - hz) < 0.15, f"{hz} Hz read as {hz_est}"
    assert conf > 0.3


@pytest.mark.parametrize("phase", [0.0, 0.25, 0.6, 0.9])
def test_phase_invariant(phase):
    hz_est, _ = estimate_blink_frequency(square_wave(4.0, phase=phase), FPS)
    assert abs(hz_est - 4.0) < 0.15


def test_survives_noise_and_dropouts():
    x = square_wave(4.0, n=90, noise=0.3, seed=3)
    x[::11] = 0.0                      # missed detections record zero flux
    hz_est, conf = estimate_blink_frequency(x, FPS)
    assert abs(hz_est - 4.0) < 0.3
    assert conf > 0.15


def test_steady_source_scores_no_confidence():
    rng = np.random.default_rng(1)
    steady = 5.0 + rng.normal(0.0, 0.05, 90)   # a star: bright, unmodulated
    hz_est, conf = estimate_blink_frequency(steady, FPS)
    assert conf < 0.12


def test_needs_history():
    hz_est, conf = estimate_blink_frequency([1.0, 0.0] * 8, FPS)
    assert hz_est is None and conf == 0.0


def test_estimate_agrees_with_goertzel_at_peak():
    x = square_wave(6.0)
    hz_est, _ = estimate_blink_frequency(x, FPS)
    at_peak = goertzel_power(x, hz_est / FPS)
    at_wrong = goertzel_power(x, 2.0 / FPS)
    assert at_peak > 4 * at_wrong


class _FakeDet:
    def __init__(self, u, v, flux, snr=20.0):
        self.u, self.v, self.flux, self.snr = u, v, flux, snr


def _run_tracker(blink_hz_config, beacon_hz, n_frames=75):
    """Feed the tracker one blinking source and one steady star by hand."""
    tracker = MultiTargetTracker(focal_px=3000.0, width=640, height=480,
                                 frame_rate_hz=FPS, beacon_blink_hz=blink_hz_config,
                                 pointing_jitter_urad=150.0)
    tracker.set_expectation(0.0, 0.0, np.radians(2.0))
    dt = 1.0 / FPS
    beacon_flux = square_wave(beacon_hz, n=n_frames, amplitude=800.0)
    for i in range(n_frames):
        dets = [_FakeDet(340.0, 240.0, 900.0)]            # steady star
        if beacon_flux[i] > 0:
            dets.append(_FakeDet(300.0, 240.0, beacon_flux[i]))
        tracker.update(dets, 0.0, 0.0, dt)
    return tracker


def test_blind_mode_locks_the_pulsed_source_not_the_star():
    """With NO agreed frequency the tracker still refuses the steady star."""
    tracker = _run_tracker(blink_hz_config=0.0, beacon_hz=3.3)
    primary = tracker.primary()
    assert primary is not None
    assert primary.est_blink_hz is not None
    assert abs(primary.est_blink_hz - 3.3) < 0.3
    assert primary.modulation_score >= tracker.modulation_threshold


def test_known_mode_estimator_reports_the_true_frequency():
    """Agreed 4 Hz: the hard gate works as before AND telemetry now carries
    the measured frequency."""
    tracker = _run_tracker(blink_hz_config=4.0, beacon_hz=4.0)
    primary = tracker.primary()
    assert primary is not None
    assert abs(primary.est_blink_hz - 4.0) < 0.2


def test_known_mode_gate_unchanged_for_wrong_frequency_imposter():
    """A 2.5 Hz imposter must keep failing the 4 Hz gate exactly as before."""
    tracker = _run_tracker(blink_hz_config=4.0, beacon_hz=2.5)
    primary = tracker.primary()
    if primary is not None:
        assert primary.modulation_score < tracker.modulation_threshold
