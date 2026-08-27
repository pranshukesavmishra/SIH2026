"""Trajectory generators must be physically right, not merely smooth."""
import numpy as np
import pytest

from fsoc_pat.beacon import Beacon, slant_range_km
from fsoc_pat.config import BeaconConfig, TrajectoryConfig

RNG = np.random.default_rng(0)


def _leo(**params):
    p = dict(t_rise_s=0.0, t_set_s=240.0, peak_el_deg=55.0, peak_az_deg=90.0, altitude_km=550.0)
    p.update(params)
    return Beacon(BeaconConfig(trajectory=TrajectoryConfig("leo_pass", p)), RNG)


def test_leo_pass_rises_culminates_and_sets():
    b = _leo()
    els = [np.degrees(b.state(t)[1]) for t in (0.0, 60.0, 120.0, 180.0, 240.0)]
    assert els[0] == pytest.approx(0.0, abs=0.5)
    assert els[2] == pytest.approx(55.0, abs=0.5)
    assert els[4] == pytest.approx(0.0, abs=0.5)
    assert els[1] == pytest.approx(els[3], abs=0.5)      # symmetric about culmination


def test_leo_range_is_minimum_at_culmination():
    b = _leo()
    ranges = [b.state(t)[2] for t in (0.0, 60.0, 120.0, 180.0, 240.0)]
    assert min(ranges) == ranges[2]
    # Culmination here is 55 deg, not the zenith, so the range floor is the
    # slant range at 55 deg -- roughly 660 km for a 550 km orbit.
    assert ranges[2] == pytest.approx(659.0, abs=2.0)
    assert ranges[0] > 2000.0                            # horizon: much further


def test_overhead_pass_closes_to_the_orbit_altitude():
    b = _leo(peak_el_deg=90.0)
    assert b.state(120.0)[2] == pytest.approx(550.0, abs=1.0)


def test_slant_range_matches_known_geometry():
    assert slant_range_km(np.pi / 2, 550.0) == pytest.approx(550.0, abs=1e-6)
    assert slant_range_km(0.0, 550.0) == pytest.approx(2707.0, abs=5.0)


def test_intensity_follows_inverse_square():
    b = _leo()
    near = b.intensity(0.0, 0.01, 400.0)
    far = b.intensity(0.0, 0.01, 800.0)
    assert near / far == pytest.approx(4.0, rel=1e-6)


def test_fast_blink_averages_to_duty_cycle():
    cfg = BeaconConfig(blink_hz=5000.0, blink_duty=0.3,
                       trajectory=TrajectoryConfig("static", {}))
    b = Beacon(cfg, RNG)
    assert b.intensity(0.0, 0.01, cfg.ref_range_km) == pytest.approx(cfg.amplitude_e_s * 0.3)


def test_slow_blink_resolves_into_visible_flicker():
    cfg = BeaconConfig(blink_hz=1.0, blink_duty=0.5, trajectory=TrajectoryConfig("static", {}))
    b = Beacon(cfg, RNG)
    on = b.intensity(0.1, 0.001, cfg.ref_range_km)
    off = b.intensity(0.7, 0.001, cfg.ref_range_km)
    assert on > 0.0 and off == 0.0


def test_unknown_trajectory_is_rejected_at_construction():
    with pytest.raises(ValueError, match="unknown trajectory"):
        Beacon(BeaconConfig(trajectory=TrajectoryConfig("teleport", {})), RNG)


def test_waypoint_interpolates_between_points():
    cfg = BeaconConfig(trajectory=TrajectoryConfig("waypoint", dict(
        points=[[0.0, 0.0, 10.0, 100.0], [10.0, 10.0, 20.0, 200.0]])))
    az, el, rng_km = Beacon(cfg, RNG).state(5.0)
    assert np.degrees(az) == pytest.approx(5.0)
    assert np.degrees(el) == pytest.approx(15.0)
    assert rng_km == pytest.approx(150.0)
