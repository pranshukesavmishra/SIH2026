"""
Headless scenario runner: one function from scenario file to report, and a
command-line entry point.

    python -m fsoc_pat.runner scenarios/leo_pass_nominal.yaml --out runs/

This is the reproducibility backbone: the GUI, the tests, the Monte Carlo
campaign and the CI smoke run all call the same ``run_scenario`` so there is
exactly one definition of "run the system on a scenario".
"""
from __future__ import annotations

import argparse
import pathlib
import time
from typing import Callable, Optional, Tuple

from .config import SimConfig
from .metrics import PerformanceReport, build_report
from .pipeline import CoarseAlignmentTracker
from .simulator import Frame, Simulator


def run_scenario(cfg: SimConfig,
                 duration_s: Optional[float] = None,
                 on_frame: Optional[Callable[[Frame, CoarseAlignmentTracker], None]] = None,
                 ) -> Tuple[PerformanceReport, CoarseAlignmentTracker]:
    """
    Run the full closed loop on one scenario and summarise it.

    ``on_frame`` is a hook for the GUI and for video export; passing None runs
    headless at full speed.
    """
    if duration_s is not None:
        cfg.duration_s = duration_s
    sim = Simulator(cfg)
    tracker = CoarseAlignmentTracker(cfg)

    started = time.perf_counter()
    for frame in sim.run(tracker):
        if on_frame is not None:
            on_frame(frame, tracker)
    wall = time.perf_counter() - started

    report = build_report(tracker.telemetry, cfg.name,
                          cfg.camera.frame_rate_hz, wall_time_s=wall)
    return report, tracker


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run FSOC-PAT coarse alignment on a scenario, headless.")
    parser.add_argument("scenario", help="path to a scenario YAML file")
    parser.add_argument("--duration", type=float, default=None,
                        help="override the scenario's duration in seconds")
    parser.add_argument("--out", default=None,
                        help="directory to write <scenario>.report.{json,txt} into")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    cfg = SimConfig.load(args.scenario)
    report, _ = run_scenario(cfg, duration_s=args.duration)

    if not args.quiet:
        print(report.to_text())
    if args.out:
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        report.to_json(str(out / f"{cfg.name}.report.json"))
        (out / f"{cfg.name}.report.txt").write_text(report.to_text() + "\n", encoding="utf-8")
        if not args.quiet:
            print(f"\nreports written to {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
