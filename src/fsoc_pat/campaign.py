"""
Monte Carlo campaign: the statistical performance envelope.

A single demonstration run proves nothing on its own -- it might be the lucky
seed. A campaign runs the same scenario family under randomised seeds and
randomised conditions (beacon brightness, turbulence strength, vibration,
initial pointing error within the field of uncertainty) and reports
distributions: acquisition time percentiles, the probability of acquiring at
all, lock retention statistics, pointing error envelopes, and how often the
system locked the wrong object. These distributions are the claims the
technical report makes; the campaign is where they come from.

    python -m fsoc_pat.campaign scenarios/leo_pass_nominal.yaml -n 48 --out runs/mc

Each run's full report is kept, so any outlier can be reproduced exactly from
its logged seed.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
from dataclasses import asdict
from typing import Dict, List, Optional

import numpy as np

from .config import SimConfig
from .runner import run_scenario


def randomise(cfg: SimConfig, rng: np.random.Generator) -> Dict[str, float]:
    """
    Draw one campaign variant. Returns what was drawn, for the run log.

    The randomisation covers what a real deployment cannot control: how bright
    the beacon happens to be, how bad the seeing is, how hard the platform
    shakes, and how wrong the initial ephemeris is. It deliberately does NOT
    randomise design constants (frame rate, FOV, gains): the campaign
    characterises one system, not a family of systems.
    """
    draws = {
        "seed": int(rng.integers(0, 2 ** 31 - 1)),
        "beacon_scale": float(rng.uniform(0.4, 2.5)),
        "turb_scale": float(rng.uniform(0.5, 2.0)),
        "vib_scale": float(rng.uniform(0.5, 2.0)),
        "point_err_az_deg": float(rng.uniform(-1.2, 1.2)),
        "point_err_el_deg": float(rng.uniform(-0.9, 0.9)),
    }
    cfg.seed = draws["seed"]
    for beacon in cfg.beacons:
        beacon.amplitude_e_s *= draws["beacon_scale"]
    cfg.turbulence.tilt_rms_urad *= draws["turb_scale"]
    cfg.turbulence.scintillation_index *= draws["turb_scale"]
    for mode in cfg.vibration.modes:
        mode[1] *= draws["vib_scale"]
    cfg.initial_pointing_deg[0] += draws["point_err_az_deg"]
    cfg.initial_pointing_deg[1] += draws["point_err_el_deg"]
    return draws


def run_campaign(scenario_path: str, n_runs: int, duration_s: Optional[float],
                 out_dir: str, master_seed: int = 42, verbose: bool = True) -> Dict:
    rng = np.random.default_rng(master_seed)
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    runs: List[Dict] = []
    started = time.time()
    for i in range(n_runs):
        cfg = SimConfig.load(scenario_path)
        draws = randomise(cfg, rng)
        report, _ = run_scenario(cfg, duration_s=duration_s)
        entry = {"run": i, "draws": draws, "report": asdict(report)}
        runs.append(entry)
        if verbose:
            acq = report.acquisition_time_s
            print(f"  run {i:3d}: acq {'--' if acq is None else f'{acq:5.2f}s'}  "
                  f"lock {report.lock_retention_pct:5.1f}%  "
                  f"p95 {report.pointing_error_urad.get('p95', float('nan')):8.1f} urad  "
                  f"decoy {report.decoy_locked_frames}", flush=True)

    # ---- aggregate -------------------------------------------------------
    acq_times = [r["report"]["acquisition_time_s"] for r in runs]
    acquired = [t for t in acq_times if t is not None]
    locks = np.array([r["report"]["lock_retention_pct"] for r in runs])
    p95s = np.array([r["report"]["pointing_error_urad"].get("p95", np.nan) for r in runs])
    p95s = p95s[np.isfinite(p95s)]
    decoy_runs = sum(1 for r in runs if r["report"]["decoy_locked_frames"] > 0)

    summary = {
        "scenario": scenario_path, "n_runs": n_runs,
        "duration_s": duration_s, "master_seed": master_seed,
        "wall_time_s": time.time() - started,
        "acquisition_probability": len(acquired) / n_runs,
        "acquisition_time_s": {
            "p50": float(np.percentile(acquired, 50)) if acquired else None,
            "p95": float(np.percentile(acquired, 95)) if acquired else None,
            "max": float(np.max(acquired)) if acquired else None,
        },
        "lock_retention_pct": {"p5": float(np.percentile(locks, 5)),
                               "p50": float(np.percentile(locks, 50)),
                               "min": float(locks.min())},
        "pointing_error_p95_urad": {"p50": float(np.percentile(p95s, 50)),
                                    "p95": float(np.percentile(p95s, 95)),
                                    "max": float(p95s.max())} if len(p95s) else None,
        "runs_with_any_decoy_lock": decoy_runs,
    }
    (out / "campaign.json").write_text(json.dumps(
        {"summary": summary, "runs": runs}, indent=1))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario")
    parser.add_argument("-n", "--runs", type=int, default=48)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--out", default="runs/mc")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    summary = run_campaign(args.scenario, args.runs, args.duration,
                           args.out, master_seed=args.seed)
    print("\n=== campaign summary ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
