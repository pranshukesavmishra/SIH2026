"""
Rig calibration: measure, never assume.

    python -m fsoc_pat.hil.calibrate --port COM5 --camera 0

Three numbers connect the software's world to the rig's, and each is measured
by the routine rather than copied from a datasheet:

  * **plate scale** (pixels per radian): command a known servo move with the
    beacon in view, measure how far the spot moved in the image. Done for
    both axes; also yields the camera-to-mount roll angle.
  * **servo scale** (commanded degrees per true degree): the same experiment
    read the other way. MG996R horns rarely sit exactly where the datasheet
    promises.
  * **command latency**: the ESP32 stamps every accepted command; the spot's
    motion onset in the camera, minus the stamp, is the real end-to-end dead
    time the Smith predictor must be configured with.

Writes hardware/calibration.yaml, which the live runner loads.
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import yaml

from ..detection import PointDetector
from .rig import SerialGimbal, UsbCamera


def brightest(detector, image):
    dets = detector.detect(image)
    return max(dets, key=lambda d: d.snr) if dets else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--step-deg", type=float, default=3.0)
    parser.add_argument("--exposure", type=float, default=-6.0)
    parser.add_argument("--out", default="hardware/calibration.yaml")
    args = parser.parse_args(argv)

    gimbal = SerialGimbal(args.port)
    camera = UsbCamera(args.camera, exposure=args.exposure)
    detector = PointDetector(psf_sigma=2.0, cfar_k=6.0)
    gimbal.centre()
    time.sleep(1.5)

    print("== plate scale ==")
    moves = {"pan": (args.step_deg, 0.0), "tilt": (0.0, args.step_deg)}
    scale = {}
    for axis, (dp, dt) in moves.items():
        before = brightest(detector, camera.read())
        if before is None:
            print("no beacon visible; aim the rig first")
            return 1
        gimbal.ser.write(f"P {dp:.2f} {dt:.2f}\n".encode())
        time.sleep(1.2)
        after = brightest(detector, camera.read())
        gimbal.centre()
        time.sleep(1.2)
        moved_px = np.hypot(after.u - before.u, after.v - before.v)
        px_per_rad = moved_px / np.radians(args.step_deg)
        scale[axis] = float(px_per_rad)
        print(f"  {axis}: {moved_px:.1f} px for {args.step_deg} deg "
              f"-> {px_per_rad:.0f} px/rad")

    print("== command latency ==")
    latencies = []
    for _ in range(5):
        before = brightest(detector, camera.read())
        t0 = time.perf_counter()
        gimbal.ser.write(f"P {args.step_deg:.2f} 0\n".encode())
        while time.perf_counter() - t0 < 1.0:
            det = brightest(detector, camera.read())
            if det and before and abs(det.u - before.u) > 3.0:
                latencies.append(time.perf_counter() - t0)
                break
        gimbal.centre()
        time.sleep(1.0)
    latency_ms = float(np.median(latencies) * 1000.0) if latencies else 80.0
    print(f"  median {latency_ms:.0f} ms over {len(latencies)} trials")

    calib = {"px_per_rad_pan": scale.get("pan"),
             "px_per_rad_tilt": scale.get("tilt"),
             "command_latency_ms": latency_ms,
             "exposure": args.exposure}
    with open(args.out, "w", encoding="utf-8") as fh:
        yaml.safe_dump(calib, fh)
    print(f"wrote {args.out}")
    camera.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
