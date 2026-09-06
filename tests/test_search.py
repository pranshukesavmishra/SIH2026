"""The spiral must actually cover the Field of Uncertainty."""
import numpy as np
import pytest

from fsoc_pat.search import SpiralSearch


def test_radii_grow_monotonically():
    plan = SpiralSearch(fou_radius_deg=8.0, fov_deg=2.0).plan
    radii = [np.hypot(*p) for p in plan.points]
    assert all(b >= a - 1e-9 for a, b in zip(radii, radii[1:]))


def test_no_gap_wider_than_the_step():
    """Consecutive dwell points must overlap, or the beacon can hide between
    turns and the scan misses it forever."""
    search = SpiralSearch(fou_radius_deg=6.0, fov_deg=2.0)
    pts = np.array(search.plan.points)
    gaps = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    assert gaps.max() <= search.plan.step_rad * 1.5


def test_covers_the_whole_uncertainty_cone():
    search = SpiralSearch(fou_radius_deg=6.0, fov_deg=2.0)
    radii = [np.hypot(*p) for p in search.plan.points]
    assert max(radii) >= np.radians(6.0) - search.plan.step_rad


def test_small_uncertainty_needs_no_scan():
    plan = SpiralSearch(fou_radius_deg=0.5, fov_deg=6.0).plan
    assert plan.n_steps == 1


def test_azimuth_step_widens_near_the_zenith():
    """Without the cos(el) division the spiral collapses horizontally."""
    search = SpiralSearch(fou_radius_deg=2.0, fov_deg=2.0)
    search._index = 1                                  # a point with an az offset
    d_az, _ = search.current_offset()
    az_low, _ = search.command(0.0, np.radians(10.0))
    az_high, _ = search.command(0.0, np.radians(75.0))
    if abs(d_az) > 1e-9:
        assert abs(az_high) > abs(az_low)


def test_advance_dwells_then_cycles():
    search = SpiralSearch(fou_radius_deg=6.0, fov_deg=2.0, dwell_frames=3)
    n = search.plan.n_steps
    for _ in range(3 * n):
        search.advance()
    assert search.completed_cycles == 1
