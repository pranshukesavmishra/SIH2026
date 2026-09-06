"""
From pointing error to communications performance.

The coarse stage's output is an angular error history. What a link engineer
needs to know is different: does the optical link close, at what data rate,
and for what fraction of the pass? This module makes that translation, so the
performance report can end with the number the whole exercise exists for.

The chain, each step standard FSO practice:

  * **Geometric loss.** A Gaussian beam of divergence theta_div delivers
    exp(-2 r^2 / theta_div^2) of its peak intensity at angular offset r --
    pointing error IS a power loss, this is the coupling.
  * **The fine stage.** Coarse alignment hands over to a fast steering mirror
    with a small angular range and a closed-loop bandwidth in the hundreds of
    hertz. Modelled honestly at frame resolution: the residual reaching the
    link is the coarse error minus what the FSM can absorb (its range) and
    follow (its bandwidth against the error's frame-to-frame change).
  * **Link margin.** Free-space path loss at the actual slant range, receiver
    aperture gain, and a required-power line; margin below zero is an outage.
  * **Availability** is then the fraction of tracked time with positive
    margin -- with and without the fine stage, because the difference IS the
    justification for the two-stage architecture.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


@dataclass
class LinkParams:
    """A modest LEO-to-ground optical downlink; every default is editable."""
    wavelength_nm: float = 1550.0
    tx_power_w: float = 2.0
    # A narrow communications beam is the entire point of FSO -- and the
    # entire reason pointing is hard. 250 urad at 500 km is a 125 m spot;
    # widening the beam buys pointing tolerance at the square of the cost in
    # delivered power, which is why the answer is a fine stage, not a wider
    # beam. (An earlier default of 1200 urad could not close the link even at
    # perfect pointing -- the margin math said so immediately, which is what
    # the module is for.)
    tx_divergence_urad: float = 250.0        # full 1/e^2 divergence of the comm beam
    rx_aperture_m: float = 0.15
    rx_sensitivity_dbm: float = -38.0        # for the target data rate
    optics_loss_db: float = 6.0              # both terminals, filters, splitters
    atmospheric_loss_db: float = 3.0         # clear-air zenith; scaled by air mass
    # fine steering stage
    fsm_range_urad: float = 3000.0
    fsm_bandwidth_hz: float = 300.0
    fsm_residual_urad: float = 15.0          # its own noise floor


@dataclass
class LinkReport:
    availability_coarse_only: float
    availability_with_fsm: float
    mean_margin_db: float
    p5_margin_db: float
    outage_count: int
    frames_evaluated: int

    def to_dict(self) -> Dict:
        return self.__dict__.copy()


def geometric_loss_db(error_urad: np.ndarray, divergence_urad: float) -> np.ndarray:
    r = error_urad / max(divergence_urad / 2.0, 1e-9)     # radius in beam half-widths
    return -10.0 * np.log10(np.maximum(np.exp(-2.0 * r * r), 1e-30))


def path_loss_db(range_km: np.ndarray, wavelength_nm: float,
                 rx_aperture_m: float, divergence_urad: float) -> np.ndarray:
    """
    Fraction of transmitted power collected by the aperture, as a loss.

    For a Gaussian beam the far-field spot radius is theta/2 * R; the aperture
    collects (2 a^2) / (w^2) of the power for a << w, which is the regime of
    every long link.
    """
    w = (divergence_urad * 1e-6 / 2.0) * (range_km * 1e3)   # spot 1/e^2 radius, m
    fraction = np.clip(2.0 * (rx_aperture_m / 2.0) ** 2 / np.maximum(w, 1e-9) ** 2,
                       1e-30, 1.0)
    return -10.0 * np.log10(fraction)


def fsm_residual_urad(coarse_error_urad: np.ndarray, params: LinkParams,
                      frame_rate_hz: float) -> np.ndarray:
    """
    What remains after the fine stage.

    Within range, the FSM removes the error down to its own floor; the part of
    the frame-to-frame *change* above its bandwidth leaks through; anything
    beyond its throw saturates it and passes untouched.
    """
    err = np.asarray(coarse_error_urad, dtype=float)
    saturated = np.maximum(err - params.fsm_range_urad, 0.0)
    # High-frequency leakage: a first-order servo at f_b rejects a change of
    # rate f by factor f/(f+f_b); apply to the per-frame innovation.
    change = np.abs(np.diff(err, prepend=err[:1]))
    nyq = frame_rate_hz / 2.0
    leak = change * (nyq / (nyq + params.fsm_bandwidth_hz))
    return np.sqrt(params.fsm_residual_urad ** 2 + leak ** 2) + saturated


def evaluate(pointing_error_urad: np.ndarray, range_km: np.ndarray,
             elevation_rad: np.ndarray, params: Optional[LinkParams] = None,
             frame_rate_hz: float = 30.0) -> LinkReport:
    """Evaluate the link over a tracked run. Arrays are per-frame, aligned."""
    params = params or LinkParams()
    err = np.asarray(pointing_error_urad, dtype=float)
    rng_km = np.asarray(range_km, dtype=float)
    el = np.asarray(elevation_rad, dtype=float)

    tx_dbm = 10.0 * np.log10(params.tx_power_w * 1e3)
    air_mass = 1.0 / np.maximum(np.sin(np.maximum(el, np.radians(5.0))), 0.087)
    fixed = (tx_dbm - params.optics_loss_db - params.atmospheric_loss_db * air_mass
             - path_loss_db(rng_km, params.wavelength_nm,
                            params.rx_aperture_m, params.tx_divergence_urad))

    margin_coarse = (fixed - geometric_loss_db(err, params.tx_divergence_urad)
                     - params.rx_sensitivity_dbm)
    resid = fsm_residual_urad(err, params, frame_rate_hz)
    margin_fsm = (fixed - geometric_loss_db(resid, params.tx_divergence_urad)
                  - params.rx_sensitivity_dbm)

    return LinkReport(
        availability_coarse_only=float((margin_coarse > 0).mean()),
        availability_with_fsm=float((margin_fsm > 0).mean()),
        mean_margin_db=float(margin_fsm.mean()),
        p5_margin_db=float(np.percentile(margin_fsm, 5)),
        outage_count=int(np.sum(np.diff((margin_fsm <= 0).astype(int)) == 1)),
        frames_evaluated=len(err))


def evaluate_run(tracker, simulator_cfg, params: Optional[LinkParams] = None
                 ) -> Optional[LinkReport]:
    """Convenience: evaluate straight from a finished tracker's telemetry."""
    frames = [t for t in tracker.telemetry
              if t.locked and t.pointing_error_rad is not None]
    if not frames:
        return None
    err = np.array([t.pointing_error_rad for t in frames]) * 1e6
    # Range/elevation are not in telemetry; reconstruct from the scenario's
    # primary beacon at the recorded times -- same generator, same numbers.
    from .beacon import Beacon
    import numpy as _np
    beacon_cfg = next(b for b in simulator_cfg.beacons if not b.is_decoy)
    beacon = Beacon(beacon_cfg, _np.random.default_rng(0))
    state = [beacon.state(t.time_s) for t in frames]
    rng_km = np.array([s[2] for s in state])
    el = np.array([s[1] for s in state])
    return evaluate(err, rng_km, el, params,
                    frame_rate_hz=simulator_cfg.camera.frame_rate_hz)
