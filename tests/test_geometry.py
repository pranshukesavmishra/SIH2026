"""Projection must be exact, because every error metric is built on it."""
import numpy as np
import pytest

from fsoc_pat import geometry as geo

W, H, FOV = 640, 480, 6.0
F = geo.focal_px(FOV, W)
CAM = (np.radians(11.9), np.radians(31.2))


def test_boresight_lands_on_principal_point():
    u, v, visible = geo.project(CAM[0], CAM[1], *CAM, F, W, H)
    assert visible
    assert u == pytest.approx(W / 2.0, abs=1e-9)
    assert v == pytest.approx(H / 2.0, abs=1e-9)


def test_project_unproject_round_trip():
    az, el = np.radians(12.3), np.radians(31.7)
    u, v, _ = geo.project(az, el, *CAM, F, W, H)
    az2, el2 = geo.unproject(u, v, *CAM, F, W, H)
    assert float(geo.angular_separation(az, el, az2, el2)) < 1e-12


def test_pixel_radius_matches_true_angular_separation():
    """A projection with the wrong focal length still round-trips; this does not."""
    az, el = np.radians(12.3), np.radians(31.7)
    u, v, _ = geo.project(az, el, *CAM, F, W, H)
    radius_px = np.hypot(u - W / 2.0, v - H / 2.0)
    sep = geo.angular_separation(az, el, *CAM)
    assert radius_px == pytest.approx(geo.urad_to_px(sep * 1e6, F), rel=1e-9)


def test_elevation_offset_moves_straight_up():
    u, v, _ = geo.project(CAM[0], CAM[1] + np.radians(0.5), *CAM, F, W, H)
    assert u == pytest.approx(W / 2.0, abs=1e-6)
    assert v < H / 2.0


def test_azimuth_separation_shrinks_with_cosine_of_elevation():
    """Near the zenith a degree of azimuth is much less than a degree of arc."""
    el = np.radians(85.0)
    sep = geo.angular_separation(0.0, el, np.radians(1.0), el)
    assert float(np.degrees(sep)) == pytest.approx(np.cos(el) * 1.0, rel=1e-3)


def test_wrap_pi_is_continuous_across_the_seam():
    assert float(geo.wrap_pi(np.radians(359.0) - np.radians(1.0))) == pytest.approx(
        np.radians(-2.0), abs=1e-12)


def test_target_behind_camera_is_not_visible():
    _, _, visible = geo.project(CAM[0] + np.pi, CAM[1], *CAM, F, W, H)
    assert not visible
