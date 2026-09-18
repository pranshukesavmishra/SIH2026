"""
The rig's live console: real camera, real servos, real beacon.

    python -m fsoc_pat.hil.live

With no flags it auto-detects the Arduino's serial port and a working
camera and starts tracking -- this is the "plug it in and run it"
console, not a tool that needs a calibration ritual first.

What it shows, and what it refuses to show:

    SEARCHING   nothing bright and blinking in frame. The rig HOLDS
                STILL and the laser stays off. No spurious motion, no
                phantom track -- if there is no beacon, the honest
                output is "no beacon".
    CONFIRMING  a blinking candidate is building evidence.
    LOCKED      confirmed at the beacon's blink rate. Green. Laser on,
                and only now does the mount steer.

Steering and the laser are both gated behind LOCKED on purpose. An
earlier build let the acquisition logic drive the servos while it was
still hunting, which swung the mount around a dark room chasing sensor
noise and put a fragile servo at risk. Nothing commands the hardware
here until there is something real to point at.

Keys:  q = quit   c = re-centre   l = laser toggle

NOTE: this console uses the lightweight rig_detect stack, kept as the
low-dependency fallback. The FULL engine on live frames -- CFAR, IMM,
Smith predictor, AI verifier, adaptive blink estimation, browser
dashboard -- is `python -m fsoc_pat.hil.serve` (hil/engine.py); prefer
it whenever the laptop can spare the cycles.
"""
from __future__ import annotations

import argparse
import time

import numpy as np

from .rig_detect import (BlinkIdentifier, LockController, RigBeaconDetector,
                         to_gray8)
from .rig import SerialGimbal, UsbCamera, find_camera, find_serial_port

# Hardware safety envelope. Independent of what the detection logic wants,
# so no software fault can slam the servos: the tilt servo has already
# failed once on this rig from being driven into a bind.
SAFETY_MAX_STEP_DEG = 3.0
SAFETY_MIN_INTERVAL_S = 0.12


def _resolve_port(explicit):
    if explicit:
        return explicit
    found = find_serial_port()
    if found is None:
        raise SystemExit(
            "no serial port found -- is the rig plugged in? pass --port "
            "explicitly (macOS: `ls /dev/cu.*`) if auto-detect misses it.")
    print(f"auto-detected serial port: {found}")
    return found


def _resolve_camera(explicit):
    if explicit is not None:
        return explicit
    found = find_camera()
    if found is None:
        raise SystemExit(
            "no working camera found -- check camera permission for your "
            "terminal (System Settings -> Privacy & Security -> Camera), "
            "or pass --camera explicitly.")
    print(f"auto-detected camera index: {found}")
    return found


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", default=None, help="omit to auto-detect")
    p.add_argument("--camera", type=int, default=None, help="omit to auto-detect")
    p.add_argument("--duration", type=float, default=600.0)
    p.add_argument("--blink-hz", type=float, default=4.0,
                   help="the beacon's blink rate. Must match what the phone "
                        "is actually doing: a hand-tapped torch is nearer "
                        "1-2 Hz than 4.")
    p.add_argument("--exposure", type=float, default=None,
                   help="lock manual exposure (dim rooms: stops auto-exposure "
                        "hunting on every blink)")
    p.add_argument("--gain", type=float, default=0.02,
                   help="servo degrees per pixel of error while locked")
    p.add_argument("--flip-pan", action="store_true", help="invert pan steering")
    p.add_argument("--flip-tilt", action="store_true", help="invert tilt steering")
    p.add_argument("--no-steer", action="store_true",
                   help="detect and identify only; never command the servos")
    p.add_argument("--no-window", action="store_true", help="headless")
    p.add_argument("--abs-floor", type=int, default=110,
                   help="brightness below which nothing is ever a candidate")
    p.add_argument("--score-threshold", type=float, default=0.30)
    p.add_argument("--confirm-frames", type=int, default=5)
    args = p.parse_args(argv)

    gimbal = SerialGimbal(_resolve_port(args.port))
    camera = UsbCamera(_resolve_camera(args.camera), exposure=args.exposure)
    detector = RigBeaconDetector(abs_floor=args.abs_floor)
    identifier = BlinkIdentifier(blink_hz=args.blink_hz,
                                 score_threshold=args.score_threshold)
    lock = LockController(confirm_frames=args.confirm_frames)

    cv2 = None
    show_window = not args.no_window
    if show_window:
        try:
            import cv2 as _cv2
            cv2 = _cv2
        except ImportError:
            print("opencv display unavailable -- running headless")
            show_window = False

    print(f"live: beacon {args.blink_hz} Hz, gain {args.gain} deg/px, "
          f"steering {'OFF' if args.no_steer else 'on lock only'} "
          f"-- {args.duration:.0f}s (q to quit)")
    gimbal.centre()
    time.sleep(1.5)

    pan, tilt = 90.0, 90.0
    last_sent = 0.0
    laser_on = False
    index = 0
    fps = 0.0
    t0 = time.perf_counter()
    t_fps = t0

    try:
        while time.perf_counter() - t0 < args.duration:
            image = camera.read()
            if image is None:
                continue
            now = time.perf_counter()

            blobs = detector.detect(image)
            identifier.update(blobs, image, now=now)
            best = identifier.best()
            state = lock.update(best)
            locked = state == LockController.LOCKED

            # Command the hardware only on a confirmed lock.
            if locked and best is not None and not args.no_steer:
                gray = to_gray8(image)
                h, w = gray.shape[:2]
                ex, ey = best.u - w / 2.0, best.v - h / 2.0
                d_pan = args.gain * ex * (1 if args.flip_pan else -1)
                d_tilt = args.gain * ey * (-1 if args.flip_tilt else 1)
                if now - last_sent >= SAFETY_MIN_INTERVAL_S:
                    d_pan = float(np.clip(d_pan, -SAFETY_MAX_STEP_DEG, SAFETY_MAX_STEP_DEG))
                    d_tilt = float(np.clip(d_tilt, -SAFETY_MAX_STEP_DEG, SAFETY_MAX_STEP_DEG))
                    if abs(d_pan) > 0.3 or abs(d_tilt) > 0.3:
                        pan, tilt = pan + d_pan, tilt + d_tilt
                        gimbal.raw_command(pan, tilt)
                        last_sent = now

            if locked != laser_on:
                gimbal.laser(locked)
                laser_on = locked

            index += 1
            if index % 15 == 0:
                fps = 15.0 / max(now - t_fps, 1e-6)
                t_fps = now

            if show_window:
                disp = cv2.cvtColor(to_gray8(image), cv2.COLOR_GRAY2BGR)
                for b in blobs:
                    cv2.circle(disp, (int(b.u), int(b.v)), 14, (0, 200, 200), 1)
                if locked:
                    colour, label = (60, 240, 120), "LOCKED"
                elif state == LockController.CONFIRMING:
                    k, n = lock.progress
                    colour, label = (60, 200, 255), f"CONFIRMING {k}/{n}"
                else:
                    colour, label = (80, 80, 240), "SEARCHING"

                if best is not None:
                    cv2.circle(disp, (int(best.u), int(best.v)), 26, colour, 2)
                    cv2.drawMarker(disp, (int(best.u), int(best.v)), colour,
                                   cv2.MARKER_CROSS, 18, 1)

                score = best.score if best else 0.0
                hz = best.dominant_hz if best else 0.0
                cv2.putText(disp, label, (12, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.8, colour, 2)
                cv2.putText(disp,
                            f"blink {score:.2f} @ {hz:4.1f}Hz (want {args.blink_hz:.1f})"
                            f"   blobs {len(blobs)}",
                            (12, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, colour, 1)
                cv2.putText(disp,
                            f"laser {'ON' if laser_on else 'off'}   "
                            f"pan {pan:.0f} tilt {tilt:.0f}   {fps:4.1f} fps",
                            (12, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.55, colour, 1)
                cv2.imshow("ZeroDrift live console", disp)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('c'):
                    gimbal.centre()
                    pan, tilt = 90.0, 90.0
                elif key == ord('l'):
                    laser_on = not laser_on
                    gimbal.laser(laser_on)

            if index % 30 == 0:
                print(f"  t={now - t0:5.1f}s {state:12} "
                      f"blobs {len(blobs)} score "
                      f"{best.score if best else 0.0:.2f} "
                      f"@ {best.dominant_hz if best else 0.0:4.1f}Hz", flush=True)
    finally:
        gimbal.laser(False)
        gimbal.centre()
        camera.release()
        if show_window and cv2 is not None:
            cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
