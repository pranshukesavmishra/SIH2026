"""End-to-end behaviour of the simulation loop."""
import numpy as np
import pytest

from fsoc_pat.config import SimConfig
from fsoc_pat.simulator import Simulator


def _aimed(cfg, t=0.0):
    """A simulator already pointed at its primary beacon, for framing tests."""
    sim = Simulator(cfg)
    az, el, _ = sim.beacons[0].state(t)
    sim.camera.gimbal.az, sim.camera.gimbal.el = az, el
    sim.camera.gimbal._target = (az, el)
    sim.index = int(t * cfg.camera.frame_rate_hz) - 1
    return sim


def test_same_seed_reproduces_identical_frames():
    """Without this the Monte Carlo campaign and the regression tests mean nothing."""
    cfg = SimConfig(duration_s=1.0)
    a = [f.image for f in Simulator(cfg).run()]
    b = [f.image for f in Simulator(cfg).run()]
    assert all(np.array_equal(x, y) for x, y in zip(a, b))


def test_different_seeds_produce_different_frames():
    cfg_a = SimConfig(duration_s=0.5, seed=1)
    cfg_b = SimConfig(duration_s=0.5, seed=2)
    a = next(iter(Simulator(cfg_a).run()))
    b = next(iter(Simulator(cfg_b).run()))
    assert not np.array_equal(a.image, b.image)


def test_frame_count_and_timing():
    cfg = SimConfig(duration_s=2.0)
    frames = list(Simulator(cfg).run())
    assert len(frames) == 60
    assert frames[-1].time_s == pytest.approx(59 / 30.0)


def test_image_is_well_exposed_not_black_and_not_saturated():
    cfg = SimConfig.load("scenarios/leo_pass_nominal.yaml")
    frame = _aimed(cfg, t=60.0).step()
    full_scale = (1 << cfg.camera.bit_depth) - 1
    assert 0.01 * full_scale < frame.image.mean() < 0.5 * full_scale
    assert (frame.image >= full_scale).mean() < 0.001


def _culmination_time(cfg):
    """Midpoint of the pass, derived from the scenario rather than hard-coded."""
    p = cfg.beacons[0].trajectory.params
    return 0.5 * (p["t_rise_s"] + p["t_set_s"])


def test_beacon_snr_rises_monotonically_towards_culmination():
    """
    The difficulty gradient of the scenario, asserted rather than assumed.

    Brightness is set by inverse-square range, so SNR climbs as the target
    approaches. It is checked over the approach only: range is stationary at
    culmination, so the curve genuinely plateaus there and asserting a rise
    across the top would be asserting the wrong physics.

    Scintillation is disabled because it is a random multiplier of order unity;
    with it on, a single frame at each time samples the fluctuation rather than
    the trend. The trend is what this test is about.
    """
    cfg = SimConfig.load("scenarios/leo_pass_nominal.yaml")
    cfg.turbulence.enabled = False
    peak = _culmination_time(cfg)
    times = np.linspace(0.0, 0.8 * peak, 5)
    snrs = [_aimed(cfg, t=float(t)).step().primary.snr for t in times]
    assert all(b > a for a, b in zip(snrs, snrs[1:])), snrs
    assert snrs[-1] > 2.5 * snrs[0], snrs


def test_dropped_frames_are_blank_and_flagged():
    cfg = SimConfig(duration_s=20.0)
    cfg.noise.frame_drop_probability = 0.5
    dropped = [f for f in Simulator(cfg).run() if f.dropped]
    assert dropped, "expected some dropped frames at p=0.5"
    assert all(f.image.max() == 0 for f in dropped)


def test_disabling_disturbances_removes_pointing_jitter():
    cfg = SimConfig(duration_s=2.0)
    cfg.turbulence.enabled = False
    cfg.vibration.enabled = False
    pointing = np.array([f.pointing_true for f in Simulator(cfg).run()])
    assert pointing.std(axis=0).max() == pytest.approx(0.0, abs=1e-12)


def test_vibration_perturbs_the_optical_axis():
    cfg = SimConfig(duration_s=2.0)
    cfg.turbulence.enabled = False
    pointing = np.array([f.pointing_true for f in Simulator(cfg).run()])
    assert pointing.std(axis=0).max() > 1e-7


def test_decoys_are_labelled_and_enter_the_field():
    """A decoy that never crosses the field cannot test discrimination."""
    cfg = SimConfig.load("scenarios/decoy_field.yaml")
    peak = _culmination_time(cfg)
    seen = set()
    for t in np.arange(peak - 20.0, peak + 20.0, 0.5):
        for target in _aimed(cfg, t=float(t)).step().targets:
            if target.is_decoy and target.in_frame:
                seen.add(target.name)
    assert len(seen) >= 3, f"decoys never entered the field: {seen}"


def test_primary_returns_the_single_non_decoy_target():
    cfg = SimConfig.load("scenarios/decoy_field.yaml")
    frame = _aimed(cfg, t=_culmination_time(cfg)).step()
    assert frame.primary is not None and not frame.primary.is_decoy


def test_controller_commands_are_applied():
    cfg = SimConfig(duration_s=3.0)
    target = (np.radians(4.0), np.radians(14.0))

    class Fixed:
        def update(self, frame):
            return target

    frames = list(Simulator(cfg).run(Fixed()))
    final = frames[-1].pointing_true
    assert abs(final[0] - target[0]) < np.radians(0.5)
    assert abs(final[1] - target[1]) < np.radians(0.5)
