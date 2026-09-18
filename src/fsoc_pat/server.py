"""
FSOC-PAT Web & API Server
Serves the responsive Mission Control interface (PC and Mobile compatible)
and provides live simulation streaming and scenario management.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import threading
import time
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any, Dict, List, Optional

import numpy as np

from fsoc_pat.config import SimConfig
from fsoc_pat.metrics import build_report
from fsoc_pat.pipeline import CoarseAlignmentTracker
from fsoc_pat.simulator import Frame, Simulator

WEB_DIR = pathlib.Path(__file__).parent / "web"
SCENARIOS_DIR = pathlib.Path(__file__).parent.parent.parent / "scenarios"


class SimulationSession:
    """Manages an active simulation session."""
    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.sim = Simulator(cfg)
        self.tracker = CoarseAlignmentTracker(cfg)
        self.running = False
        self.paused = False
        self.step_idx = 0
        self.gen = self.sim.run(self.tracker)
        self.lock = threading.Lock()
        self.latest_frame: Optional[Frame] = None
        self.latest_telemetry: Optional[Any] = None

    def step(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            try:
                frame = next(self.gen)
                self.latest_frame = frame
                t = self.tracker.telemetry[-1] if self.tracker.telemetry else None
                self.latest_telemetry = t
                self.step_idx += 1

                # Construct payload
                result = {
                    "step": self.step_idx,
                    "time_s": float(frame.time_s),
                    "gimbal_pan_deg": float(np.degrees(frame.true_pointing[0])),
                    "gimbal_tilt_deg": float(np.degrees(frame.true_pointing[1])),
                    "target_pan_deg": float(np.degrees(frame.ground_truth.target_apparent[0])) if frame.ground_truth.target_apparent is not None else None,
                    "target_tilt_deg": float(np.degrees(frame.ground_truth.target_apparent[1])) if frame.ground_truth.target_apparent is not None else None,
                    "target_in_fov": bool(frame.ground_truth.target_in_fov),
                    "target_pixel": [float(p) for p in frame.ground_truth.target_pixel] if frame.ground_truth.target_pixel is not None else None,
                    "state": t.state.value if t else "SEARCH",
                    "locked": bool(t.locked) if t else False,
                    "detected": bool(t.detected) if t else False,
                    "pointing_error_urad": float(t.pointing_error_rad * 1e6) if t and t.pointing_error_rad is not None else None,
                    "error_rad": float(t.error_rad) if t and t.error_rad is not None else None,
                    "modulation_score": float(t.modulation_score) if t else 0.0,
                    "ai_score": float(t.ai_score) if t and t.ai_score is not None else None,
                    "mode_probabilities": [float(p) for p in t.mode_probabilities] if t else [0.5, 0.5],
                    "processing_ms": float(t.processing_ms) if t else 0.0,
                    "n_detections": int(t.n_detections) if t else 0,
                    "detections": [
                        {"x": float(d.pixel[0]), "y": float(d.pixel[1]), "flux": float(d.flux), "snr": float(d.snr)}
                        for d in self.tracker.detector.detections
                    ] if hasattr(self.tracker, "detector") and hasattr(self.tracker.detector, "detections") else [],
                    "stars": [
                        {"x": float(s[0]), "y": float(s[1]), "flux": float(s[2])}
                        for s in getattr(frame.ground_truth, "stars_pixel", [])[:40]
                    ] if hasattr(frame.ground_truth, "stars_pixel") else [],
                    "decoys": [
                        {"x": float(d[0]), "y": float(d[1]), "flux": float(d[2])}
                        for d in getattr(frame.ground_truth, "decoys_pixel", [])
                    ] if hasattr(frame.ground_truth, "decoys_pixel") else []
                }
                return result
            except StopIteration:
                return None


active_session: Optional[SimulationSession] = None
session_lock = threading.Lock()


class MissionControlHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, format, *args):
        # Reduce console clutter during rapid requests
        if args and str(args[0]).startswith(('200', '304')):
            return
        super().log_message(format, *args)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            self.send_json({"status": "online", "system": "ZeroDrift FSOC-PAT", "version": "1.0.0"})
            return

        if path == "/api/scenarios":
            scenarios = []
            if SCENARIOS_DIR.exists():
                for p in sorted(SCENARIOS_DIR.glob("*.yaml")):
                    try:
                        cfg = SimConfig.load(str(p))
                        scenarios.append({
                            "id": p.name,
                            "name": cfg.name,
                            "filename": p.name,
                            "description": cfg.description if hasattr(cfg, 'description') else p.stem.replace('_', ' ').title(),
                            "duration_s": cfg.duration_s,
                            "frame_rate_hz": cfg.camera.frame_rate_hz,
                            "fov_deg": cfg.camera.fov_deg,
                            "turbulence": cfg.turbulence.enabled,
                            "greenwood_hz": cfg.turbulence.greenwood_hz if cfg.turbulence.enabled else 0,
                            "vibration": cfg.vibration.enabled,
                            "decoys": len(cfg.decoys) if hasattr(cfg, 'decoys') else 0
                        })
                    except Exception as e:
                        scenarios.append({"id": p.name, "name": p.stem, "error": str(e)})
            self.send_json({"scenarios": scenarios})
            return

        if path == "/api/step":
            global active_session
            with session_lock:
                if active_session is None:
                    # Default scenario
                    default_path = SCENARIOS_DIR / "leo_pass_nominal.yaml"
                    if default_path.exists():
                        cfg = SimConfig.load(str(default_path))
                        active_session = SimulationSession(cfg)
                if active_session:
                    frame_data = active_session.step()
                    if frame_data:
                        self.send_json({"ok": True, "frame": frame_data})
                    else:
                        report = build_report(active_session.tracker.telemetry,
                                              active_session.cfg.name,
                                              active_session.cfg.camera.frame_rate_hz)
                        self.send_json({"ok": False, "finished": True, "report": report.__dict__})
                    return
            self.send_json({"ok": False, "error": "No active session"})
            return

        if path == "/api/report":
            with session_lock:
                if active_session and active_session.tracker.telemetry:
                    report = build_report(active_session.tracker.telemetry,
                                          active_session.cfg.name,
                                          active_session.cfg.camera.frame_rate_hz)
                    self.send_json({"ok": True, "report": report.__dict__})
                    return
            self.send_json({"ok": False, "error": "No report available"})
            return

        # Fall back to serving static files from WEB_DIR
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"

        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = {}

        if path == "/api/init":
            global active_session
            scenario_name = data.get("scenario", "leo_pass_nominal.yaml")
            scenario_path = SCENARIOS_DIR / scenario_name
            if not scenario_path.exists():
                scenario_path = SCENARIOS_DIR / "leo_pass_nominal.yaml"

            try:
                cfg = SimConfig.load(str(scenario_path))
                # Optional overrides from client
                if "duration_s" in data:
                    cfg.duration_s = float(data["duration_s"])
                if "turbulence_enabled" in data:
                    cfg.turbulence.enabled = bool(data["turbulence_enabled"])
                if "greenwood_hz" in data:
                    cfg.turbulence.greenwood_hz = float(data["greenwood_hz"])
                if "vibration_enabled" in data:
                    cfg.vibration.enabled = bool(data["vibration_enabled"])

                with session_lock:
                    active_session = SimulationSession(cfg)
                self.send_json({"ok": True, "scenario": scenario_path.name, "name": cfg.name, "duration_s": cfg.duration_s})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, status=500)
            return

        if path == "/api/run_full":
            scenario_name = data.get("scenario", "leo_pass_nominal.yaml")
            duration_s = data.get("duration_s", None)
            scenario_path = SCENARIOS_DIR / scenario_name
            if not scenario_path.exists():
                scenario_path = SCENARIOS_DIR / "leo_pass_nominal.yaml"

            try:
                cfg = SimConfig.load(str(scenario_path))
                if duration_s:
                    cfg.duration_s = float(duration_s)
                sim = Simulator(cfg)
                tracker = CoarseAlignmentTracker(cfg)

                telemetry_list = []
                t_start = time.perf_counter()
                for frame in sim.run(tracker):
                    t = tracker.telemetry[-1] if tracker.telemetry else None
                    if t:
                        telemetry_list.append({
                            "time_s": float(t.time_s),
                            "state": t.state.value,
                            "locked": bool(t.locked),
                            "pointing_error_urad": float(t.pointing_error_rad * 1e6) if t.pointing_error_rad is not None else None,
                            "modulation_score": float(t.modulation_score),
                            "ai_score": float(t.ai_score) if t.ai_score is not None else None,
                            "mode_probabilities": [float(p) for p in t.mode_probabilities],
                            "processing_ms": float(t.processing_ms)
                        })
                wall_time = time.perf_counter() - t_start
                report = build_report(tracker.telemetry, cfg.name, cfg.camera.frame_rate_hz, wall_time_s=wall_time)

                self.send_json({
                    "ok": True,
                    "scenario": cfg.name,
                    "frames_count": len(telemetry_list),
                    "telemetry": telemetry_list[::max(1, len(telemetry_list)//200)], # sample up to 200 points for charts
                    "report": {
                        "acquisition_time_s": report.acquisition_time_s,
                        "lock_retention_pct": report.lock_retention_pct,
                        "pointing_error_urad": report.pointing_error_urad,
                        "fsm_handover_pct": report.fsm_handover_pct,
                        "wrong_locks": report.wrong_target_locks,
                        "wall_time_s": wall_time
                    }
                })
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, status=500)
            return

        self.send_json({"error": "Endpoint not found"}, status=404)

    def send_json(self, obj: Any, status: int = 200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def run_server(port: int = 8080):
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    server_address = ("", port)
    httpd = HTTPServer(server_address, MissionControlHandler)
    print(f"===========================================================")
    print(f"🚀 ZeroDrift FSOC-PAT Mission Control Web Server Running!")
    print(f"🌐 URL: http://localhost:{port}")
    print(f"📱 PC & Mobile Compatible (Stitch Aetheris Orbital Design)")
    print(f"===========================================================")
    httpd.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run FSOC-PAT Web Interface Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind server (default: 8080)")
    args = parser.parse_args()
    run_server(args.port)
