"""
Calibrate the verifier's confidence, so its vote means what it says.

    python -m fsoc_pat.ai.calibrate --out models/

A network trained to minimise cross-entropy separates classes well (AUC) yet
its raw sigmoid is routinely over-confident: "0.92" from an uncalibrated
model is not a 92% chance of being the beacon. Temperature scaling (Guo et
al., 2017) fixes exactly this: one scalar T divides the logit, fitted on
held-out data. It cannot change the ranking (monotonic), so AUC is untouched
-- it only makes the probabilities honest.

The payoff is the abstain band. Once probabilities are honest, "0.5-ish"
genuinely means "cannot tell", and the tracker treats it as *no vote* instead
of a weak vote: the verifier abstains rather than guesses, and the classical
evidence (persistence, consistency, prior, modulation) decides alone. The
band's edges are chosen from the validation set as the region where the
calibrated model is no better than a coin flip.

Writes models/calibration.json next to the weights; TrackVerifier picks it
up automatically when present, and behaves exactly as before when absent.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

from .data import harvest
from .tinynet import TemporalPatchNet
from .train import roc_auc


def nll(logits: np.ndarray, labels: np.ndarray, temperature: float) -> float:
    z = logits / temperature
    p = 1.0 / (1.0 + np.exp(-z))
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(labels * np.log(p) + (1 - labels) * np.log(1 - p)))


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    """Golden-section search on one scalar: no optimiser dependency needed."""
    lo, hi = 0.25, 12.0
    phi = (np.sqrt(5.0) - 1) / 2
    a, b = lo, hi
    c, d = b - phi * (b - a), a + phi * (b - a)
    for _ in range(60):
        if nll(logits, labels, c) < nll(logits, labels, d):
            b = d
        else:
            a = c
        c, d = b - phi * (b - a), a + phi * (b - a)
    return float((a + b) / 2)


def expected_calibration_error(p: np.ndarray, labels: np.ndarray,
                               bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for i in range(bins):
        mask = (p >= edges[i]) & (p < edges[i + 1] if i < bins - 1 else p <= 1.0)
        if not mask.any():
            continue
        ece += mask.mean() * abs(p[mask].mean() - labels[mask].mean())
    return float(ece)


def abstain_band(p: np.ndarray, labels: np.ndarray,
                 min_accuracy: float = 0.9) -> tuple:
    """
    The calibrated-probability region where the verifier should shut up.

    Sweep symmetric bands around 0.5; the band grows until predictions
    *outside* it are at least ``min_accuracy`` accurate on validation data.
    Inside the band the model has demonstrably nothing to add.
    """
    for half in np.arange(0.02, 0.45, 0.02):
        lo, hi = 0.5 - half, 0.5 + half
        outside = (p < lo) | (p > hi)
        if not outside.any():
            continue
        acc = float(((p[outside] > 0.5) == labels[outside]).mean())
        if acc >= min_accuracy:
            return float(lo), float(hi)
    return 0.35, 0.65


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="models")
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--seed", type=int, default=5000,
                    help="disjoint from the train (1000) and test (9000) pools")
    args = ap.parse_args(argv)

    out = pathlib.Path(args.out)
    net = TemporalPatchNet.load(str(out / "track_verifier.npz"))
    print("harvesting a calibration split from the simulator…")
    x, y = harvest(n_runs=args.runs, base_seed=args.seed, verbose=True)
    logits = net.forward(x)

    T = fit_temperature(logits, y)
    p_raw = 1.0 / (1.0 + np.exp(-logits))
    p_cal = 1.0 / (1.0 + np.exp(-logits / T))
    lo, hi = abstain_band(p_cal, y)
    inside = (p_cal >= lo) & (p_cal <= hi)

    report = {
        "temperature": round(T, 4),
        "abstain_lo": round(lo, 3),
        "abstain_hi": round(hi, 3),
        "val_samples": int(len(y)),
        "val_auc": round(roc_auc(p_cal, y), 4),
        "ece_before": round(expected_calibration_error(p_raw, y), 4),
        "ece_after": round(expected_calibration_error(p_cal, y), 4),
        "abstain_fraction": round(float(inside.mean()), 4),
        "accuracy_when_voting": round(
            float(((p_cal[~inside] > 0.5) == y[~inside]).mean()), 4)
        if (~inside).any() else None,
        "harvest_seed": args.seed,
    }
    (out / "calibration.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"calibration -> {out / 'calibration.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
