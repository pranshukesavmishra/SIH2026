"""
Classical Goertzel vs the neural verifier, across the conditions that matter.

    python tools/benchmark_id.py --out runs/benchmark-id

The single headline number in the defence brief (AUC 0.957 vs 0.900 on
8-frame windows) answers one cell of a bigger question: WHERE does each
method win? This sweep walks window length x beacon brightness x blink
frequency and reports the AUC of both discriminators per cell, on identical
labelled stacks harvested from the simulator (the labelling oracle).

Ground rules, so the comparison stays honest:
  * The network always sees its native 8-frame window (that is the model
    that ships). For longer windows it scores the LAST 8 frames -- exactly
    what the serving verifier's deque would hold.
  * The Goertzel gets the full window at the TRUE blink frequency -- the
    classical method's home turf, frequency agreed in advance.
  * Both are published, including every cell the classical method wins.

Writes results.json plus a markdown table (docs/benchmark_identification.md
is generated from it).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from fsoc_pat.ai.data import harvest
from fsoc_pat.ai.tinynet import TemporalPatchNet
from fsoc_pat.ai.train import goertzel_baseline, roc_auc

WINDOWS = [8, 16, 32]
FREQS = [2.0, 4.0, 6.0, 10.0]
AMPS = {"dim": (5.0e5, 1.5e6), "nominal": (1.5e6, 1.2e7)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/benchmark-id")
    ap.add_argument("--runs", type=int, default=6, help="sim runs per cell")
    ap.add_argument("--seed", type=int, default=7000)
    ap.add_argument("--weights", default="models/track_verifier.npz")
    args = ap.parse_args(argv)

    net = TemporalPatchNet.load(args.weights)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cells = []
    t0 = time.time()
    for wi, frames in enumerate(WINDOWS):
        for fi, hz in enumerate(FREQS):
            for ai, (tier, amp) in enumerate(AMPS.items()):
                seed = args.seed + 1000 * wi + 100 * fi + 10 * ai
                x, y = harvest(n_runs=args.runs, frames=frames,
                               base_seed=seed, blink_hz=hz,
                               amplitude_range=amp)
                # network: its native window = the last K frames of the stack
                x_net = x[:, -net.K:] if frames > net.K else x
                p_net = net.predict(x_net)
                g = goertzel_baseline(x, blink_hz=hz)
                cell = {
                    "window_frames": frames, "blink_hz": hz, "amplitude": tier,
                    "samples": int(len(y)), "positives": int(y.sum()),
                    "auc_network": round(roc_auc(p_net, y), 4),
                    "auc_goertzel": round(roc_auc(g, y), 4),
                }
                cell["winner"] = ("network" if cell["auc_network"] > cell["auc_goertzel"] + 1e-9
                                  else "goertzel" if cell["auc_goertzel"] > cell["auc_network"] + 1e-9
                                  else "tie")
                cells.append(cell)
                print(f"K={frames:2d}  {hz:4.1f} Hz  {tier:8s}  "
                      f"net {cell['auc_network']:.3f}  vs  "
                      f"goertzel {cell['auc_goertzel']:.3f}  -> {cell['winner']}"
                      f"   ({len(y)} samples, {time.time()-t0:.0f}s)")

    results = {
        "runs_per_cell": args.runs, "seed": args.seed,
        "network_window_frames": net.K,
        "note": ("network always scores its native window (last K frames); "
                 "goertzel gets the full window at the true frequency"),
        "cells": cells,
        "wall_time_s": round(time.time() - t0, 1),
    }
    (out / "results.json").write_text(json.dumps(results, indent=2))

    # ---- markdown report -------------------------------------------------
    lines = [
        "# Beacon identification: classical vs learned, across conditions",
        "",
        "AUC of \"is this K-frame history the beacon?\" for the Goertzel",
        "modulation power (full window, true frequency known) and the shipped",
        "497-parameter neural verifier (its native 8-frame window — what it",
        "sees in service). Same labelled stacks, harvested from the simulator",
        f"against hidden ground truth. {args.runs} runs/cell, seed {args.seed}.",
        "",
        "| window | blink | beacon | network AUC | Goertzel AUC | stronger |",
        "|---|---|---|---|---|---|",
    ]
    for c in cells:
        lines.append(f"| {c['window_frames']} frames "
                     f"({c['window_frames']/30:.2f} s) | {c['blink_hz']:.0f} Hz "
                     f"| {c['amplitude']} | {c['auc_network']:.3f} "
                     f"| {c['auc_goertzel']:.3f} | {c['winner']} |")
    net_wins = sum(1 for c in cells if c["winner"] == "network")
    g_wins = sum(1 for c in cells if c["winner"] == "goertzel")
    lines += [
        "",
        f"**Score: network {net_wins} cells, Goertzel {g_wins} cells.**",
        "",
        "## Where the classical method wins — and why we say so",
        "",
        "Long windows are Goertzel territory: given enough cycles, a single",
        "matched frequency bin approaches the optimal detector for a periodic",
        "signal, and no 497-parameter network beats mathematics with time on",
        "its side. The network's edge is the opposite regime — short windows,",
        "where too few blink cycles have elapsed for a frequency bin to",
        "resolve, and spatial appearance carries the decision. That is why",
        "the tracker uses **both**: the network votes early, the Goertzel",
        "hard-gates the final identity, and neither replaces the other.",
        "",
        "A second finding the table makes plain: the verifier's vote is",
        "**frequency-specific**. Trained on 4 Hz beacons, it degrades —",
        "sometimes below chance — on 10 Hz targets it never saw. The",
        "classical gate has no training distribution to leave, which is",
        "exactly why the tracker keeps the Goertzel as the final authority",
        "on identity and weights the network's vote below it.",
        "",
        "Generated by `tools/benchmark_id.py`; raw numbers in",
        f"`{out.as_posix()}/results.json`.",
    ]
    md = pathlib.Path("docs/benchmark_identification.md")
    md.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {out / 'results.json'} and {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
