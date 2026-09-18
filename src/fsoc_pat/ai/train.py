"""
Train the track verifier and benchmark it against the classical discriminator.

    python -m fsoc_pat.ai.train --out models/

Writes the weights, a JSON of the evaluation, and prints the comparison table
the technical report quotes. The benchmark question is the operational one:
given a K-frame history of a source, is it the beacon? -- asked of the network
and of the Goertzel modulation power on identical inputs.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np

from ..tracking import goertzel_power
from .data import harvest
from .tinynet import TemporalPatchNet


def roc_auc(scores: np.ndarray, labels: np.ndarray) -> float:
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(len(scores))
    pos = labels == 1
    n_pos, n_neg = pos.sum(), (~pos).sum()
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[pos].sum() - n_pos * (n_pos - 1) / 2) / (n_pos * n_neg))


def goertzel_baseline(stacks: np.ndarray, blink_hz: float = 4.0,
                      fps: float = 30.0) -> np.ndarray:
    """The classical answer on the same inputs: modulation power of the
    central-aperture flux across the stack."""
    scores = []
    for stack in stacks:
        k, p, _ = stack.shape
        c = p // 2
        flux = stack[:, c - 1:c + 2, c - 1:c + 2].sum(axis=(1, 2))
        scores.append(goertzel_power(list(flux), blink_hz / fps))
    return np.asarray(scores)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="models")
    parser.add_argument("--runs", type=int, default=48)
    parser.add_argument("--epochs", type=int, default=400)
    args = parser.parse_args(argv)

    print("harvesting training data from the simulator…")
    x, y = harvest(n_runs=args.runs, base_seed=1000, verbose=True)
    x_test, y_test = harvest(n_runs=max(args.runs // 3, 8), base_seed=9000)
    print(f"train {len(y)} stacks ({int(y.sum())} beacon), "
          f"test {len(y_test)} ({int(y_test.sum())} beacon)")

    net = TemporalPatchNet(frames=x.shape[1], patch=x.shape[2], seed=7)
    history = net.train(x, y, epochs=args.epochs, verbose=True)

    p_train = net.predict(x)
    p_test = net.predict(x_test)
    g_test = goertzel_baseline(x_test)

    results = {
        "train_samples": int(len(y)), "test_samples": int(len(y_test)),
        "final_loss": history[-1],
        "train_auc": roc_auc(p_train, y),
        "test_auc_network": roc_auc(p_test, y_test),
        "test_auc_goertzel": roc_auc(g_test, y_test),
        "test_accuracy_network": float(((p_test > 0.5) == y_test).mean()),
        "test_accuracy_goertzel": float(((g_test > 0.22) == y_test).mean()),
        "parameters": int(sum(v.size for v in net.params.values())),
    }
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    net.save(str(out / "track_verifier.npz"))
    (out / "training_results.json").write_text(json.dumps(results, indent=2))

    print("\n=== beacon identification on held-out data (K-frame stacks) ===")
    print(f"  network   AUC {results['test_auc_network']:.3f}   "
          f"accuracy {results['test_accuracy_network']:.3f}   "
          f"({results['parameters']} parameters)")
    print(f"  goertzel  AUC {results['test_auc_goertzel']:.3f}   "
          f"accuracy {results['test_accuracy_goertzel']:.3f}   (0 parameters)")
    print(f"weights -> {out / 'track_verifier.npz'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
