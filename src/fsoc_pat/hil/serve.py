"""
Live rig server: real camera -> real engine -> the ZD-1 dashboard.

    python -m fsoc_pat.hil.serve                    # auto camera, no rig
    python -m fsoc_pat.hil.serve --port-serial auto # + Mk2 over serial
    python -m fsoc_pat.hil.serve --video clip.mp4   # no hardware at all

Then open  http://localhost:8765/rig.html  (served from docs/, offline).

One process: the engine loop runs in a background thread at camera rate;
HTTP hands out three things --

    /live/meta       constants: fov, fps, blink mode, sources, mode
    /live/stream     Server-Sent Events, one JSON telemetry record/frame
    /live/video      MJPEG of the camera view with detection overlays
    /<anything>      static files from docs/ (the dashboard itself)

CORS is wide open so the Netlify copy of the console could also point at a
local server, but the offline path -- everything from this one process --
is the demo-day default: no wifi, no cloud, no excuses.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DOCS = pathlib.Path(__file__).resolve().parents[3] / "docs"

MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
        ".json": "application/json", ".png": "image/png",
        ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".mp4": "video/mp4"}


class LiveState:
    """Latest telemetry + jpeg, shared between engine thread and HTTP."""

    def __init__(self):
        self.lock = threading.Lock()
        self.rec = None
        self.jpeg = b""
        self.seq = 0
        self.meta = {}
        self.running = True

    def publish(self, rec, jpeg):
        with self.lock:
            self.rec, self.jpeg = rec, jpeg
            self.seq += 1

    def snapshot(self):
        with self.lock:
            return self.seq, self.rec, self.jpeg


STATE = LiveState()


def engine_loop(engine, source, throttle_fps: float):
    period = 1.0 / throttle_fps if throttle_fps > 0 else 0.0
    while STATE.running:
        t0 = time.monotonic()
        rec = engine.step()
        if rec is None:                          # video file ended: loop it
            if hasattr(engine.source, "cap") and hasattr(engine.source, "_i"):
                try:
                    engine.source.cap.set(1, 0)  # CAP_PROP_POS_FRAMES
                    engine.source._i = 0
                    continue
                except Exception:
                    pass
            STATE.running = False
            return
        jpeg = engine.annotate_jpeg(engine._last_image, rec) \
            if engine._last_image is not None else b""
        STATE.publish(rec, jpeg)
        if period:
            dt = time.monotonic() - t0
            if dt < period:
                time.sleep(period - dt)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):                    # quiet
        pass

    def _head(self, code=200, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/live/meta":
            self._head()
            self.wfile.write(json.dumps(STATE.meta).encode())
        elif path == "/live/stream":
            self._head(ctype="text/event-stream")
            last = -1
            try:
                while STATE.running:
                    seq, rec, _ = STATE.snapshot()
                    if rec is not None and seq != last:
                        last = seq
                        self.wfile.write(b"data: " + json.dumps(rec).encode()
                                         + b"\n\n")
                        self.wfile.flush()
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                return
        elif path == "/live/video":
            self._head(ctype="multipart/x-mixed-replace; boundary=zdframe")
            last = -1
            try:
                while STATE.running:
                    seq, _, jpeg = STATE.snapshot()
                    if jpeg and seq != last:
                        last = seq
                        self.wfile.write(b"--zdframe\r\nContent-Type: "
                                         b"image/jpeg\r\nContent-Length: "
                                         + str(len(jpeg)).encode()
                                         + b"\r\n\r\n" + jpeg + b"\r\n")
                        self.wfile.flush()
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                return
        else:                                     # static from docs/
            if path in ("/", ""):
                path = "/rig.html"
            f = (DOCS / path.lstrip("/")).resolve()
            if not str(f).startswith(str(DOCS)) or not f.is_file():
                self._head(404, "text/plain")
                self.wfile.write(b"not found")
                return
            self._head(ctype=MIME.get(f.suffix, "application/octet-stream"))
            self.wfile.write(f.read_bytes())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--http-port", type=int, default=8765)
    ap.add_argument("--camera", type=int, default=None,
                    help="camera index; default: auto-detect")
    ap.add_argument("--video", default=None,
                    help="drive from a recorded video instead of a camera")
    ap.add_argument("--port-serial", default=None,
                    help="Mk2 serial port, or 'auto'; omit = camera-only")
    ap.add_argument("--fov-deg", type=float, default=50.0)
    ap.add_argument("--blink-hz", type=float, default=4.0,
                    help="expected beacon frequency; 0 = adaptive blind mode")
    ap.add_argument("--exposure", type=float, default=None)
    ap.add_argument("--cfar-k", type=float, default=6.0)
    ap.add_argument("--dry-run", action="store_true",
                    help="attach the Mk2 driver but capture instead of send")
    args = ap.parse_args(argv)

    from .engine import CameraSource, LiveEngine, VideoSource, live_config

    if args.video:
        source = VideoSource(args.video)
        src_name = f"video:{pathlib.Path(args.video).name}"
        w = int(source.cap.get(3)) or 640
        h = int(source.cap.get(4)) or 480
    else:
        idx = args.camera
        if idx is None:
            from .rig import find_camera
            idx = find_camera()
            if idx is None:
                raise SystemExit("no camera found -- pass --camera or --video")
        source = CameraSource(idx, exposure=args.exposure)
        src_name = f"camera:{idx}"
        w, h = 640, 480

    gimbal = None
    if args.port_serial or args.dry_run:
        from .mk2 import Mk2Gimbal
        port = args.port_serial
        if port == "auto":
            from .rig import find_serial_port
            port = find_serial_port()
        gimbal = Mk2Gimbal(port if not args.dry_run else None,
                           dry_run=args.dry_run)

    cfg = live_config(fov_deg=args.fov_deg, width=w, height=h,
                      fps=getattr(source, "fps", 30.0),
                      blink_hz=args.blink_hz)
    engine = LiveEngine(source, cfg, gimbal=gimbal, cfar_k=args.cfar_k)
    STATE.meta = {
        "mode": "live", "source": src_name,
        "rig": ("mk2-dry" if args.dry_run else
                "mk2" if gimbal is not None else "camera-only"),
        "fov_deg": cfg.camera.fov_deg, "fps": cfg.camera.frame_rate_hz,
        "blink_hz": cfg.beacons[0].blink_hz,
        "adaptive": cfg.beacons[0].blink_hz == 0.0,
        "sensor_px": [cfg.camera.width, cfg.camera.height],
    }

    threading.Thread(target=engine_loop, args=(engine, source, 30.0),
                     daemon=True).start()
    httpd = ThreadingHTTPServer(("0.0.0.0", args.http_port), Handler)
    print(f"ZD-1 LIVE  ->  http://localhost:{args.http_port}/rig.html")
    print(f"  source {src_name} · rig {STATE.meta['rig']} · "
          f"blink {'adaptive' if STATE.meta['adaptive'] else str(args.blink_hz)+' Hz'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        STATE.running = False
        if gimbal is not None:
            gimbal.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
