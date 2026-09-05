"""The link budget must punish pointing error and reward the fine stage."""
import numpy as np
import pytest

from fsoc_pat.linkbudget import (LinkParams, evaluate, fsm_residual_urad,
                                 geometric_loss_db)


def test_boresight_closes_and_gross_error_does_not():
    r = evaluate(np.zeros(100), np.full(100, 500.0), np.full(100, np.radians(60)))
    assert r.mean_margin_db > 0
    bad = evaluate(np.full(100, 5000.0), np.full(100, 500.0),
                   np.full(100, np.radians(60)))
    assert bad.availability_coarse_only == 0.0


def test_geometric_loss_is_monotonic_and_zero_at_boresight():
    errs = np.array([0.0, 50.0, 125.0, 250.0, 500.0])
    loss = geometric_loss_db(errs, 250.0)
    assert loss[0] == pytest.approx(0.0, abs=1e-9)
    assert all(b > a for a, b in zip(loss, loss[1:]))
    # at one half-divergence the Gaussian gives exp(-2) -> 8.7 dB
    assert loss[2] == pytest.approx(8.686, abs=0.01)


def test_fsm_absorbs_slow_error_but_not_saturation():
    p = LinkParams()
    slow = np.full(200, 1000.0)                       # within range, static
    resid = fsm_residual_urad(slow, p, 30.0)
    assert resid.max() < 3 * p.fsm_residual_urad
    huge = np.full(200, p.fsm_range_urad + 2000.0)    # beyond the throw
    resid = fsm_residual_urad(huge, p, 30.0)
    assert resid.min() > 1500.0


def test_fine_stage_availability_never_below_coarse():
    rng = np.random.default_rng(0)
    err = np.abs(rng.normal(0, 600, 500))
    r = evaluate(err, np.full(500, 600.0), np.full(500, np.radians(45)))
    assert r.availability_with_fsm >= r.availability_coarse_only


def test_longer_range_erodes_margin():
    near = evaluate(np.zeros(10), np.full(10, 500.0), np.full(10, np.radians(60)))
    far = evaluate(np.zeros(10), np.full(10, 1500.0), np.full(10, np.radians(60)))
    assert far.mean_margin_db < near.mean_margin_db
