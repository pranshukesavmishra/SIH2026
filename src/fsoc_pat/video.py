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

# The GUI's palette (gui/theme.py), as BGR for OpenCV, so exported frames and
# the live console are visibly the same instrument.
GROUND = (20, 14, 10)
PANEL = (30, 22, 16)
EDGE = (66, 52, 40)
INK = (242, 234, 226)
INK_MUTED = (166, 152, 138)
ACCENT = (232, 200, 83)
STATE_BGR = {"SEARCH": (255, 159, 90), "ACQUIRE": (77, 194, 255),
             "TRACK": (143, 214, 63), "COAST": (77, 157, 255),
             "REACQUIRE": (94, 107, 255)}
PANEL_W = 360


def render(frame, telemetry, tracker, error_trace) -> np.ndarray:
    img = frame.image
    h, w = img.shape
    view = np.clip(img.astype(np.float32) / max(img.max(), 1) * 255, 0, 255).astype(np.uint8)
    view = cv2.cvtColor(view, cv2.COLOR_GRAY2BGR)

    colour = STATE_BGR.get(telemetry.state.value, (200, 200, 200))

    # Corner brackets: the sensor's active area.
    arm = int(min(w, h) * 0.05)
    for cx, cy, sx, sy in ((0, 0, 1, 1), (w - 1, 0, -1, 1),
                           (0, h - 1, 1, -1), (w - 1, h - 1, -1, -1)):
        cv2.line(view, (cx, cy), (cx + sx * arm, cy), EDGE, 1, cv2.LINE_AA)
        cv2.line(view, (cx, cy), (cx, cy + sy * arm), EDGE, 1, cv2.LINE_AA)

    # Gap boresight cross, as in the GUI.
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        cv2.line(view, (w // 2 + dx * 5, h // 2 + dy * 5),
                 (w // 2 + dx * 16, h // 2 + dy * 16), (210, 210, 210), 1, cv2.LINE_AA)

    # During SEARCH, the acquisition spiral and the current dwell point.
    if telemetry.state.value == "SEARCH":
        f = tracker.focal_px
        pts = []
        for d_az, d_el in tracker.search.plan.points:
            px = w // 2 + int(geo.urad_to_px(d_az * 1e6, f))
            py = h // 2 - int(geo.urad_to_px(d_el * 1e6, f))
            pts.append((px, py))
        if len(pts) > 1:
            cv2.polylines(view, [np.array(pts)], False, (120, 90, 50), 1, cv2.LINE_AA)
        d_az, d_el = tracker.search.current_offset()
        px = w // 2 + int(geo.urad_to_px(d_az * 1e6, f))
        py = h // 2 - int(geo.urad_to_px(d_el * 1e6, f))
        cv2.circle(view, (px, py), 5, STATE_BGR["SEARCH"], 2, cv2.LINE_AA)

    for track in tracker.tracker.tracks:
        if track.last_detection is None or track.misses:
            continue
        d = track.last_detection
        cv2.drawMarker(view, (int(d.u), int(d.v)), ACCENT,
                       cv2.MARKER_DIAMOND, 11, 1)

    inset_src = None
    if telemetry.track_id is not None:
        track = next((t for t in tracker.tracker.tracks
                      if t.track_id == telemetry.track_id), None)
        if track is not None:
            az, el = track.angles
            cam_az, cam_el = frame.pointing_reported
            u, v, vis = geo.project(az, el, cam_az, cam_el, tracker.focal_px, w, h)
            if vis:
                # Double-arc reticle; dashed reads as circle at video scale,
                # so coast is distinguished by colour alone here.
                cv2.ellipse(view, (int(u), int(v)), (13, 13), 0, 20, 130, colour, 2, cv2.LINE_AA)
                cv2.ellipse(view, (int(u), int(v)), (13, 13), 0, 200, 310, colour, 2, cv2.LINE_AA)
                ra, re = track.imm.rates
                u2, v2, vis2 = geo.project(az + ra * 0.5, el + re * 0.5,
                                           cam_az, cam_el, tracker.focal_px, w, h)
                if vis2 and np.hypot(u2 - u, v2 - v) > 16:
                    cv2.arrowedLine(view, (int(u), int(v)), (int(u2), int(v2)),
                                    colour, 1, cv2.LINE_AA, tipLength=0.18)
                inset_src = (int(u), int(v))

    # 4x magnifier inset, lower-right, as in the GUI.
    if inset_src is not None:
        half = 24
        u0 = int(np.clip(inset_src[0] - half, 0, w - 2 * half))
        v0 = int(np.clip(inset_src[1] - half, 0, h - 2 * half))
        crop = view[v0:v0 + 2 * half, u0:u0 + 2 * half]
        size = int(min(w, h) * 0.3)
        mag = cv2.resize(crop, (size, size), interpolation=cv2.INTER_NEAREST)
        x0, y0 = w - size - 10, h - size - 10
        view[y0:y0 + size, x0:x0 + size] = mag
        cv2.rectangle(view, (x0, y0), (x0 + size, y0 + size), EDGE, 1)
        cv2.putText(view, "4x", (x0 + 6, y0 + 16), cv2.FONT_HERSHEY_SIMPLEX,
                    0.4, INK_MUTED, 1, cv2.LINE_AA)

    panel = np.full((h, PANEL_W, 3), PANEL, np.uint8)
    cv2.line(panel, (0, 0), (0, h), EDGE, 1)

    def put(text, y, c=INK, s=0.5):
        cv2.putText(panel, text, (16, y), cv2.FONT_HERSHEY_SIMPLEX, s, c, 1, cv2.LINE_AA)

    put("FSOC-PAT", 32, INK, 0.7)
    put("COARSE ALIGNMENT CONSOLE", 52, INK_MUTED, 0.38)
    cv2.line(panel, (16, 64), (PANEL_W - 16, 64), EDGE, 1)

    # State chip.
    label = telemetry.state.value
    (tw, _), _baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.rectangle(panel, (16, 78), (16 + tw + 20, 104), colour, -1)
    cv2.putText(panel, label, (26, 96), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                GROUND, 1, cv2.LINE_AA)
    cv2.putText(panel, f"t {telemetry.time_s:6.1f} s", (PANEL_W - 120, 96),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, INK_MUTED, 1, cv2.LINE_AA)

    # The headline number, large: pointing error.
    err = telemetry.pointing_error_rad
    big = "---" if err is None else f"{err * 1e6:.0f}"
    cv2.putText(panel, big, (16, 156), cv2.FONT_HERSHEY_SIMPLEX, 1.15, ACCENT, 2, cv2.LINE_AA)
    cv2.putText(panel, "urad pointing error", (16, 176), cv2.FONT_HERSHEY_SIMPLEX,
                0.4, INK_MUTED, 1, cv2.LINE_AA)

    rows = [("detections", f"{telemetry.n_detections}"),
            ("beacon SNR", "--" if telemetry.detection_snr is None
             else f"{telemetry.detection_snr:.1f}"),
            ("manoeuvre prob", f"{telemetry.mode_probabilities[1]:.2f}")]
    if telemetry.ai_score is not None:
        rows.append(("AI verifier", f"{telemetry.ai_score:.2f}"))
    rows.append(("processing", f"{telemetry.processing_ms:.1f} ms"))
    y = 208
    for name, value in rows:
        put(name, y, INK_MUTED, 0.42)
        cv2.putText(panel, value, (PANEL_W - 16 - 8 * len(value), y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, INK, 1, cv2.LINE_AA)
        y += 24

    # Error trace, log scale 10..30000 urad, filled under the curve.
    top, bottom, left, right = y + 24, h - 24, 16, PANEL_W - 16
    put("POINTING ERROR (LOG)", top - 10, INK_MUTED, 0.36)
    cv2.rectangle(panel, (left, top), (right, bottom), EDGE, 1)
    pts = []
    for i, e in enumerate(error_trace):
        if e is None:
            continue
        x = left + int((right - left) * i / max(len(error_trace) - 1, 1))
        frac = np.clip((np.log10(max(e * 1e6, 10.0)) - 1.0) / 3.5, 0.0, 1.0)
        pts.append((x, int(bottom - (bottom - top) * frac)))
    if len(pts) > 1:
        fill = np.array(pts + [(pts[-1][0], bottom), (pts[0][0], bottom)])
        overlay = panel.copy()
        cv2.fillPoly(overlay, [fill], (60, 46, 28))
        cv2.addWeighted(overlay, 0.6, panel, 0.4, 0, panel)
        cv2.polylines(panel, [np.array(pts)], False, ACCENT, 1, cv2.LINE_AA)

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
