"""
The gimbal's limits are the reason tracking is hard; they must actually bind.

A simulator whose mount follows commands instantly makes every controller look
good, so these tests exist to prove it does not.
"""
import numpy as np
import pytest

from fsoc_pat.camera import Detector, Gimbal, VirtualCamera
from fsoc_pat.config import CameraConfig, GimbalConfig

RNG = np.random.default_rng(7)


def _gimbal(**kw):
    cfg = GimbalConfig(command_latency_ms=0.0, encoder_noise_urad=0.0, **kw)
    return Gimbal(cfg, 0.0, np.radians(20.0), np.random.default_rng(1))


def test_slew_never_exceeds_the_rate_limit():
    g = _gimbal(max_rate_deg_s=20.0, max_accel_deg_s2=1e6)
    g.command(np.radians(90.0), np.radians(20.0))
    dt, travelled = 1.0 / 30.0, []
    for _ in range(60):
        before = g.az
        g.step(dt)
        travelled.append(abs(g.az - before) / dt)
    assert max(travelled) <= np.radians(20.0) + 1e-9


def test_acceleration_limit_binds():
    g = _gimbal(max_rate_deg_s=1e6, max_accel_deg_s2=60.0)
    g.command(np.radians(90.0), np.radians(20.0))
    dt, rates = 1.0 / 30.0, [0.0]
    for _ in range(30):
        g.step(dt)
        rates.append(g.rate_az)
    jumps = np.abs(np.diff(rates)) / dt
    assert jumps.max() <= np.radians(60.0) * 1.0001


def test_command_latency_delays_the_response():
    cfg = GimbalConfig(command_latency_ms=100.0, encoder_noise_urad=0.0)
    g = Gimbal(cfg, 0.0, np.radians(20.0), RNG)
    g.command(np.radians(45.0), np.radians(20.0))
    for _ in range(2):                       # 66 ms elapsed, under the 100 ms latency
        g.step(1.0 / 30.0)
    assert g.az == pytest.approx(0.0, abs=1e-12)
    for _ in range(3):                       # now past it
        g.step(1.0 / 30.0)
    assert g.az > 0.0


def test_slew_settles_on_target_without_overshoot():
    g = _gimbal(max_rate_deg_s=20.0, max_accel_deg_s2=60.0)
    target = np.radians(5.0)
    g.command(target, np.radians(20.0))
    overshoot = 0.0
    for _ in range(200):
        g.step(1.0 / 30.0)
        overshoot = max(overshoot, g.az - target)
    assert g.az == pytest.approx(target, abs=np.radians(0.05))
    assert overshoot < np.radians(0.2)


def test_elevation_limits_are_enforced():
    cfg = GimbalConfig(command_latency_ms=0.0, el_limits_deg=[-5.0, 60.0])
    g = Gimbal(cfg, 0.0, np.radians(20.0), RNG)
    g.command(0.0, np.radians(89.0))
    for _ in range(300):
        g.step(1.0 / 30.0)
    assert np.degrees(g.el) <= 60.0 + 1e-6


def test_encoder_noise_is_present_but_unbiased():
    cfg = GimbalConfig(command_latency_ms=0.0, encoder_noise_urad=50.0)
    g = Gimbal(cfg, 0.0, 0.0, np.random.default_rng(3))
    errors = np.array([g.reported_pointing()[0] for _ in range(4000)])
    assert errors.std() == pytest.approx(50e-6, rel=0.15)
    assert abs(errors.mean()) < 5e-6


def test_detector_saturates_at_full_well():
    cfg = CameraConfig(read_noise_e=0.0, dark_current_e_per_s=0.0, hot_pixel_fraction=0.0)
    det = Detector(cfg, np.random.default_rng(5))
    frame = det.expose(np.full((8, 8), 1e9, dtype=np.float32))
    assert frame.max() == (1 << cfg.bit_depth) - 1


def test_dark_frame_sits_near_zero_but_is_not_empty():
    cfg = CameraConfig(hot_pixel_fraction=0.0)
    det = Detector(cfg, np.random.default_rng(5))
    frame = det.expose(np.zeros((64, 64), dtype=np.float32))
    assert frame.mean() < 5.0
    assert frame.std() > 0.0


def test_psf_widens_under_seeing():
    cam = VirtualCamera(CameraConfig(), GimbalConfig(), 0.0, 0.0, RNG)
    assert cam.psf_sigma(0.0) == pytest.approx(CameraConfig().psf_sigma_px)
    assert cam.psf_sigma(2.0) > cam.psf_sigma(0.0)
