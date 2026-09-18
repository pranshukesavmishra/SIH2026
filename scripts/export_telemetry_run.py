"""
Export a full ISS-pass simulation run as a JSON telemetry recording.

Output: docs/media/telemetry_run.json

Structure:
  constants  {fov_deg, frame_rate_hz, gimbal_max_rate_deg_s,
              command_latency_ms, beacon_blink_hz, fov_half_width_urad}
  summary    {acquisition_time_s, lock_retention_pct,
              pointing_error_urad{mean,max,p50,p95,p99},
              beacon_in_fov_pct, decoy_locked_frames, reacquisitions,
              processing_ms{...}, frames}
  frames[]   {i, t, state, locked, detected, n_det, err_urad, in_fov,
              on_decoy, rate_frac, mod, ai, p_manoeuvre, snr_db, proc_ms}
"""
from __future__ import annotations

import json
import pathlib
import sys

# Add the src directory to the path so we can import fsoc_pat
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fsoc_pat.config import SimConfig
from fsoc_pat.runner import run_scenario

import numpy as np


def export(scenario_path: str, output_path: str, duration_s: float = 45.0):
    cfg = SimConfig.load(scenario_path)

    report, tracker = run_scenario(cfg, duration_s=duration_s)

    # Extract constants from config
    blink_hz = 0.0
    for b in cfg.beacons:
        if not b.is_decoy:
            blink_hz = b.blink_hz
            break

    constants = {
        "fov_deg": cfg.camera.fov_deg,
        "frame_rate_hz": cfg.camera.frame_rate_hz,
        "gimbal_max_rate_deg_s": cfg.gimbal.max_rate_deg_s,
        "command_latency_ms": cfg.gimbal.command_latency_ms,
        "beacon_blink_hz": blink_hz,
        "fov_half_width_urad": cfg.camera.fov_deg * 0.5 * (np.pi / 180.0) * 1e6,
    }

    # Build summary from the report
    telem = tracker.telemetry
    locked_frames = [t for t in telem if t.locked]
    total_frames = len(telem)

    # Pointing error stats (only locked frames with pointing_error_rad)
    locked_errors = [t.pointing_error_rad * 1e6 for t in locked_frames
                     if t.pointing_error_rad is not None]
    err_arr = np.array(locked_errors) if locked_errors else np.array([0.0])

    # Acquisition time
    acq_time = None
    if tracker.acquisition_frame is not None:
        acq_frame_t = telem[tracker.acquisition_frame] if tracker.acquisition_frame < len(telem) else None
        if acq_frame_t is not None:
            acq_time = acq_frame_t.time_s

    # Beacon in FOV fraction
    in_fov_count = sum(1 for t in telem if t.beacon_in_fov)

    # Decoy locked frames
    decoy_frames = sum(1 for t in telem if t.on_decoy)

    # Reacquisitions count
    from fsoc_pat.pipeline import LockState
    reacquisitions = 0
    prev_state = None
    for t in telem:
        if t.state == LockState.REACQUIRE and prev_state != LockState.REACQUIRE:
            reacquisitions += 1
        prev_state = t.state

    # Processing time stats
    proc_times = np.array([t.processing_ms for t in telem])

    summary = {
        "acquisition_time_s": round(acq_time, 3) if acq_time is not None else None,
        "lock_retention_pct": round(len(locked_frames) / max(1, total_frames) * 100, 1),
        "pointing_error_urad": {
            "mean": round(float(err_arr.mean()), 1),
            "max": round(float(err_arr.max()), 1),
            "p50": round(float(np.percentile(err_arr, 50)), 1),
            "p95": round(float(np.percentile(err_arr, 95)), 1),
            "p99": round(float(np.percentile(err_arr, 99)), 1),
        },
        "beacon_in_fov_pct": round(in_fov_count / max(1, total_frames) * 100, 1),
        "decoy_locked_frames": decoy_frames,
        "reacquisitions": reacquisitions,
        "processing_ms": {
            "mean": round(float(proc_times.mean()), 2),
            "max": round(float(proc_times.max()), 2),
            "p50": round(float(np.percentile(proc_times, 50)), 2),
            "p95": round(float(np.percentile(proc_times, 95)), 2),
            "p99": round(float(np.percentile(proc_times, 99)), 2),
        },
        "frames": total_frames,
    }

    # Build frames array
    frames = []
    for t in telem:
        err_urad = None
        if t.pointing_error_rad is not None:
            err_urad = round(t.pointing_error_rad * 1e6, 1)

        snr_db = None
        if t.detection_snr is not None:
            snr_db = round(float(t.detection_snr), 1)

        ai = None
        if t.ai_score is not None:
            ai = round(float(t.ai_score), 4)

        frames.append({
            "i": t.frame_index,
            "t": round(t.time_s, 4),
            "state": t.state.value,
            "locked": t.locked,
            "detected": t.detected,
            "n_det": t.n_detections,
            "err_urad": err_urad,
            "in_fov": t.beacon_in_fov,
            "on_decoy": t.on_decoy,
            "rate_frac": round(t.gimbal_rate_frac, 4),
            "mod": round(t.modulation_score, 4),
            "ai": ai,
            "p_manoeuvre": round(t.mode_probabilities[1], 4),
            "snr_db": snr_db,
            "proc_ms": round(t.processing_ms, 2),
        })

    result = {
        "constants": constants,
        "summary": summary,
        "frames": frames,
    }

    out = pathlib.Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=None, separators=(",", ":"))

    print(f"Exported {len(frames)} frames to {out}")
    print(f"  Acquisition time: {summary['acquisition_time_s']}s")
    print(f"  Lock retention: {summary['lock_retention_pct']}%")
    print(f"  Mean pointing error: {summary['pointing_error_urad']['mean']} µrad")
    print(f"  File size: {out.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    scenario = str(ROOT / "scenarios" / "iss_pass.yaml")
    output = str(ROOT / "docs" / "media" / "telemetry_run.json")
    export(scenario, output)
