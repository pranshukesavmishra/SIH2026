"""
The live loop: the simulation's algorithms, a real camera, real servos.

    python -m fsoc_pat.hil.live --port COM5 --camera 0

Builds a CoarseAlignmentTracker from a scenario config whose camera/gimbal
sections have been overwritten with the CALIBRATED numbers, then feeds it
LiveFrame objects instead of simulated ones. The tracker cannot tell the
difference -- which is the entire demonstration.
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import yaml

from ..config import SimConfig
from ..metrics import build_report
from ..pipeline import CoarseAlignmentTracker
from .rig import LiveFrame, SerialGimbal, UsbCamera


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--calibration", default="hardware/calibration.yaml")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--blink-hz", type=float, default=4.0)
    parser.add_argument("--fov-deg", type=float, default=None,
                        help="override; else derived from calibration")
    args = parser.parse_args(argv)

    with open(args.calibration, encoding="utf-8") as fh:
        calib = yaml.safe_load(fh)

    cfg = SimConfig()
    cfg.name = "live"
    px_per_rad = calib["px_per_rad_pan"]
    cfg.camera.fov_deg = args.fov_deg or float(np.degrees(cfg.camera.width / px_per_rad))
    cfg.gimbal.command_latency_ms = calib["command_latency_ms"]
    cfg.gimbal.max_rate_deg_s = 45.0
    cfg.beacons[0].blink_hz = args.blink_hz
    cfg.turbulence.enabled = False          # the real air provides its own
    cfg.vibration.enabled = False

    gimbal = SerialGimbal(args.port)
    camera = UsbCamera(args.camera, exposure=calib.get("exposure"))
    tracker = CoarseAlignmentTracker(cfg, fou_radius_deg=8.0,
                                     search_centre=(0.0, 0.0))

    print(f"live: FOV {cfg.camera.fov_deg:.1f} deg, "
          f"latency {cfg.gimbal.command_latency_ms:.0f} ms, "
          f"beacon {args.blink_hz} Hz -- tracking for {args.duration:.0f} s")
    gimbal.centre()
    time.sleep(1.5)

    index = 0
    t0 = time.perf_counter()
    try:
        while time.perf_counter() - t0 < args.duration:
            image = camera.read()
            if image is None:
                continue
            pointing = gimbal.reported_pointing()
            frame = LiveFrame(index=index, time_s=time.perf_counter() - t0,
                              image=image, pointing_true=pointing,
                              pointing_reported=pointing)
            az, el = tracker.update(frame)
            gimbal.command(az, el)
            index += 1
            if index % 30 == 0:
                t = tracker.telemetry[-1]
                print(f"  t={t.time_s:5.1f}s {t.state.value:9} "
                      f"det {t.n_detections}", flush=True)
    finally:
        gimbal.centre()
        camera.release()

    report = build_report(tracker.telemetry, "live", 30.0,
                          wall_time_s=time.perf_counter() - t0)
    print(report.to_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
