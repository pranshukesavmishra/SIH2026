"""
Export one full run's per-frame telemetry as JSON, for the web dashboard.

The browser cannot run the simulator, so the hosted demo replays a recording
instead of inventing numbers. Every value in that recording comes from the
same engine, scenario and seed as the desktop app, so the dashboard and the
performance report agree by construction.

    python tools/export_telemetry.py scenarios/iss_pass.yaml --out docs/media/telemetry_run.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fsoc_pat.config import SimConfig
from fsoc_pat.runner import run_scenario


def export(scenario: str, out_path: str, duration: float | None = None) -> dict:
    cfg = SimConfig.load(scenario)
    # Same entry point the GUI and the headless CLI use, so the recording is
    # the run, not a re-implementation of it.
    report, tracker = run_scenario(cfg, duration_s=duration)

    frames = []
    for t in tracker.telemetry:
        frames.append({
            "i": t.frame_index,
            "t": round(t.time_s, 3),
            "state": t.state.value,
            "locked": bool(t.locked),
            "detected": bool(t.detected),
            "n_det": int(t.n_detections),
            # micro-radians, the unit the deck and the GUI both use
            "err_urad": None if t.pointing_error_rad is None
                        else round(t.pointing_error_rad * 1e6, 1),
            "in_fov": bool(t.beacon_in_fov),
            "on_decoy": bool(t.on_decoy),
            "rate_frac": round(float(t.gimbal_rate_frac), 4),
            "mod": round(float(t.modulation_score), 4),
            "ai": None if t.ai_score is None else round(float(t.ai_score), 4),
            "p_manoeuvre": round(float(t.mode_probabilities[1]), 4),
            "snr_db": None if t.detection_snr is None
                      else round(float(t.detection_snr), 2),
            "proc_ms": round(float(t.processing_ms), 2),
        })

    payload = {
        "scenario": cfg.name,
        "source": Path(scenario).name,
        "seed": cfg.seed,
        # the constants the dashboard must display instead of guessing
        "constants": {
            "fov_deg": cfg.camera.fov_deg,
            "frame_rate_hz": cfg.camera.frame_rate_hz,
            "gimbal_max_rate_deg_s": cfg.gimbal.max_rate_deg_s,
            "command_latency_ms": cfg.gimbal.command_latency_ms,
            "beacon_blink_hz": next((b.blink_hz for b in cfg.beacons
                                     if not b.is_decoy), 0.0),
            "fov_half_width_urad": round(cfg.camera.fov_deg / 2 * 17453.3, 1),
        },
        "summary": {
            "acquisition_time_s": report.acquisition_time_s,
            "lock_retention_pct": round(report.lock_retention_pct, 2),
            "pointing_error_urad": {k: round(v, 1) for k, v
                                    in report.pointing_error_urad.items()},
            "beacon_in_fov_pct": round(report.beacon_in_fov_pct, 2),
            "decoy_locked_frames": int(report.decoy_locked_frames),
            "reacquisitions": int(report.reacquisitions),
            "processing_ms": {k: round(v, 2) for k, v
                              in report.processing_ms.items()},
            "frames": len(frames),
        },
        "frames": frames,
    }

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scenario", nargs="?", default="scenarios/iss_pass.yaml")
    ap.add_argument("--out", default="docs/media/telemetry_run.json")
    ap.add_argument("--duration", type=float, default=None)
    args = ap.parse_args(argv)

    payload = export(args.scenario, args.out, args.duration)
    s = payload["summary"]
    size_kb = Path(args.out).stat().st_size / 1024
    print(f"wrote {args.out}  ({size_kb:.0f} kB, {s['frames']} frames)")
    print(f"  acquisition   {s['acquisition_time_s']:.2f} s")
    print(f"  lock retention{s['lock_retention_pct']:6.1f} %")
    print(f"  pointing p50  {s['pointing_error_urad'].get('p50', float('nan')):.0f} urad")
    print(f"  beacon in FOV {s['beacon_in_fov_pct']:.1f} %")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
