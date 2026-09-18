"""
Regression guards for the control loop.

The numbers asserted here were measured on the sterile ramp testbed after the
two-path Smith restructure; a change that quietly reintroduces the
rate-times-latency lag (the bug this file exists because of) fails loudly.
"""
import numpy as np
import pytest

from fsoc_pat import geometry as geo
from fsoc_pat.camera import Gimbal
from fsoc_pat.config import GimbalConfig
from fsoc_pat.control import PointingController


def _ramp(rate_deg_s, seconds=16.0, latency_ms=40.0):
    fps, dt = 30.0, 1.0 / 30.0
    cfg = GimbalConfig(command_latency_ms=latency_ms, encoder_noise_urad=0.0)
    gimbal = Gimbal(cfg, 0.0, 0.3, np.random.default_rng(0))
    ctl = PointingController(cfg, fps, az0=0.0, el0=0.3)
    rate = np.radians(rate_deg_s)
    errors = []
    for i in range(int(seconds * fps)):
        t = i * dt
        err = (geo.wrap_pi(rate * t - gimbal.az), 0.3 - gimbal.el)
        tel = ctl.update(reported=(gimbal.az, gimbal.el), dt=dt,
                         optical_error=err, target_rates=(rate, 0.0))
        gimbal.command(tel.command_az, tel.command_el)
        gimbal.step(dt)
        if t > seconds * 0.6:
            errors.append(geo.wrap_pi(rate * (t + dt) - gimbal.az))
    return np.array(errors) * 1e6                       # urad


def test_ramp_lag_stays_at_the_noise_floor():
    """A step-input Smith structure lags by rate x latency = 524 urad here."""
    lag = _ramp(0.75)
    assert abs(lag.mean()) < 20.0
    assert np.abs(lag).max() < 40.0


def test_fast_ramp_within_the_integral_clamp_regime():
    # The integral path stands in for the follower lag rate^2/(2a) ~ 1.3 mrad
    # at this rate; convergence to that standing value takes ~10 s, so the
    # window is long and the bound reflects the converged behaviour.
    lag = _ramp(3.0, seconds=24.0)
    assert abs(lag.mean()) < 60.0


def test_long_latency_is_still_compensated():
    lag = _ramp(0.75, latency_ms=100.0, seconds=24.0)
    assert abs(lag.mean()) < 40.0


def test_step_settles_without_hunting():
    fps, dt = 30.0, 1.0 / 30.0
    cfg = GimbalConfig(command_latency_ms=40.0, encoder_noise_urad=0.0)
    gimbal = Gimbal(cfg, 0.0, 0.3, np.random.default_rng(0))
    ctl = PointingController(cfg, fps, az0=0.0, el0=0.3)
    target = np.radians(0.3)
    errors = []
    for i in range(int(7.0 * fps)):
        err = (geo.wrap_pi(target - gimbal.az), 0.3 - gimbal.el)
        tel = ctl.update(reported=(gimbal.az, gimbal.el), dt=dt,
                         optical_error=err, target_rates=(0.0, 0.0))
        gimbal.command(tel.command_az, tel.command_el)
        gimbal.step(dt)
        errors.append(abs(err[0]))
    # The mount's discrete-time braking law parks ~42 urad short of any
    # commanded point (measured on the gimbal alone); the integral path
    # removes that bias at its own deliberate pace. So the assertion is
    # two-part: promptly inside the mount's own parking scale, and fully
    # converged once the integrator has had time to work.
    early = np.array(errors[int(2.0 * fps):int(3.0 * fps)]) * 1e6
    late = np.array(errors[int(5.0 * fps):]) * 1e6
    assert early.max() < 200.0
    assert late.max() < 60.0


def test_coasting_returns_last_command_without_input():
    cfg = GimbalConfig()
    ctl = PointingController(cfg, 30.0, az0=0.1, el0=0.2)
    tel = ctl.update(reported=(0.1, 0.2), dt=1 / 30.0)
    assert tel.command_az == pytest.approx(0.1)
    assert tel.command_el == pytest.approx(0.2)
