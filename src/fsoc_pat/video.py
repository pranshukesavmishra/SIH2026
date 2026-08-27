"""
Demo video export: a scenario run rendered to an annotated MP4.

    python -m fsoc_pat.video scenarios/iss_pass.yaml --duration 45 --out demo.mp4

Layout per frame: the camera view with the same overlays as the GUI, and a
side panel with the live numbers (state, time, pointing error, SNR, mode
probabilities) plus a scrolling error trace. Rendered with OpenCV only, so it
runs headless and inside the packaged binary.
"""
from __future__ import annotations

import argparse
from collections import deque

import cv2
import numpy as np

from . import geometry as geo
from .config import SimConfig
from .pipeline import CoarseAlignmentTracker
from .simulator import Simulator

STATE_BGR = {"SEARCH": (255, 160, 80), "ACQUIRE": (60, 200, 255),
             "TRACK": (120, 220, 70), "COAST": (50, 140, 255),
             "REACQUIRE": (90, 90, 255)}
PANEL_W = 360


def render(frame, telemetry, tracker, error_trace) -> np.ndarray:
    img = frame.image
    h, w = img.shape
    view = np.clip(img.astype(np.float32) / max(img.max(), 1) * 255, 0, 255).astype(np.uint8)
    view = cv2.cvtColor(view, cv2.COLOR_GRAY2BGR)

    colour = STATE_BGR.get(telemetry.state.value, (200, 200, 200))
    cv2.drawMarker(view, (w // 2, h // 2), (210, 210, 210), cv2.MARKER_CROSS, 24, 1)
    for track in tracker.tracker.tracks:
        if track.last_detection is None or track.misses:
            continue
        d = track.last_detection
        cv2.drawMarker(view, (int(d.u), int(d.v)), (255, 170, 150),
                       cv2.MARKER_DIAMOND, 12, 1)
    if telemetry.track_id is not None:
        track = next((t for t in tracker.tracker.tracks
                      if t.track_id == telemetry.track_id), None)
        if track is not None:
            az, el = track.angles
            cam_az, cam_el = frame.pointing_reported
            u, v, vis = geo.project(az, el, cam_az, cam_el, tracker.focal_px, w, h)
            if vis:
                cv2.circle(view, (int(u), int(v)), 12, colour, 2)

    panel = np.full((h, PANEL_W, 3), 22, np.uint8)
    def put(text, y, c=(200, 205, 210), s=0.55):
        cv2.putText(panel, text, (14, y), cv2.FONT_HERSHEY_SIMPLEX, s, c, 1, cv2.LINE_AA)
    put("FSOC-PAT  coarse alignment", 30, (240, 240, 240), 0.62)
    put(f"t = {telemetry.time_s:6.1f} s", 62)
    cv2.rectangle(panel, (14, 76), (150, 100), colour, -1)
    cv2.putText(panel, telemetry.state.value, (20, 94), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (15, 15, 15), 1, cv2.LINE_AA)
    err = telemetry.pointing_error_rad
    put(f"pointing error  {'--' if err is None else f'{err*1e6:8.0f} urad'}", 130)
    put(f"detections      {telemetry.n_detections}", 156)
    snr = telemetry.detection_snr
    put(f"beacon SNR      {'--' if snr is None else f'{snr:6.1f}'}", 182)
    put(f"manoeuvre prob  {telemetry.mode_probabilities[1]:.2f}", 208)
    if telemetry.ai_score is not None:
        put(f"AI verifier     {telemetry.ai_score:.2f}", 234)
    put(f"processing      {telemetry.processing_ms:5.1f} ms", 260)

    # error trace, log scale 10..30000 urad
    top, bottom, left, right = 300, h - 30, 14, PANEL_W - 14
    cv2.rectangle(panel, (left, top), (right, bottom), (60, 64, 70), 1)
    pts = []
    for i, e in enumerate(error_trace):
        if e is None:
            continue
        x = left + int((right - left) * i / max(len(error_trace) - 1, 1))
        frac = np.clip((np.log10(max(e * 1e6, 10.0)) - 1.0) / 3.5, 0.0, 1.0)
        pts.append((x, int(bottom - (bottom - top) * frac)))
    if len(pts) > 1:
        cv2.polylines(panel, [np.array(pts)], False, (255, 200, 120), 1, cv2.LINE_AA)
    put("pointing error (log)", top - 8, (150, 155, 160), 0.45)

    return np.hstack([view, panel])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario")
    parser.add_argument("--duration", type=float, default=45.0)
    parser.add_argument("--out", default="demo.mp4")
    parser.add_argument("--scale", type=int, default=1)
    args = parser.parse_args(argv)

    cfg = SimConfig.load(args.scenario)
    cfg.duration_s = args.duration
    sim = Simulator(cfg)
    tracker = CoarseAlignmentTracker(cfg)

    size = (cfg.camera.width * args.scale + PANEL_W, cfg.camera.height * args.scale)
    writer = cv2.VideoWriter(args.out, cv2.VideoWriter_fourcc(*"mp4v"),
                             cfg.camera.frame_rate_hz, size)
    trace = deque(maxlen=240)
    for frame in sim.run(tracker):
        telemetry = tracker.telemetry[-1]
        trace.append(telemetry.pointing_error_rad)
        canvas = render(frame, telemetry, tracker, trace)
        if args.scale != 1:
            canvas = cv2.resize(canvas, size, interpolation=cv2.INTER_NEAREST)
        writer.write(canvas)
    writer.release()
    print(f"wrote {args.out} ({sim.total_frames} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
