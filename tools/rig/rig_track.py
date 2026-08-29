"""
ZeroDrift mini-rig: physically point a laser at a blinking phone flashlight.

The webcam finds the beacon by its ~4 Hz blink (same identity principle as
the full simulator), and two SG90 servos steer the laser toward it with a
simple proportional loop — a real, physical coarse-alignment demo.

    pip install opencv-python numpy pyserial
    python tools/rig/rig_track.py --port /dev/ttyUSB0        # Linux/Mac
    python tools/rig/rig_track.py --port COM5                # Windows

Keys:  arrows = manual trim   c = centre   l = laser toggle   q = quit
Safety: 5 mW class laser — never point at eyes; tape a paper target
behind the phone; keep the soft limits in the firmware.
"""
import argparse
import collections
import time

import cv2
import numpy as np
import serial


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="Arduino serial port")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--blink", type=float, default=4.0)
    ap.add_argument("--gain", type=float, default=0.02,
                    help="servo degrees per pixel of error (start small)")
    args = ap.parse_args()

    ard = serial.Serial(args.port, 115200, timeout=0.01)
    time.sleep(2.0)                      # Nano resets on connect
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print("no camera"); return 1

    N = 64
    hist = collections.deque(maxlen=N)
    times = collections.deque(maxlen=N)
    pan_deg, tilt_deg = 90.0, 90.0
    laser = False
    pos = None

    def send():
        ard.write(f"P{int(pan_deg)} T{int(tilt_deg)}\n".encode())

    send()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        H, W = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT,
                                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
        blur = cv2.GaussianBlur(tophat, (9, 9), 0)
        _, mx, _, loc = cv2.minMaxLoc(blur)
        if pos is None or np.hypot(loc[0]-pos[0], loc[1]-pos[1]) < 80 or mx > 60:
            pos = loc

        patch = gray[max(0, pos[1]-6):pos[1]+7, max(0, pos[0]-6):pos[0]+7]
        hist.append(float(patch.mean()) if patch.size else 0.0)
        times.append(time.time())

        score = 0.0
        if len(hist) == N and times[-1] > times[0]:
            fps = (N-1) / (times[-1]-times[0])
            sig = np.array(hist) - np.mean(hist)
            k = args.blink / fps * N
            w = np.exp(-2j*np.pi*k*np.arange(N)/N)
            score = min(1.0, 2.0*abs(np.dot(sig, w))**2 /
                        ((float(np.dot(sig, sig))+1e-9)*N/2))
        beacon = score > 0.35

        if beacon:
            # proportional steering: move servos to shrink the pixel error.
            # If it runs AWAY from the target, flip the sign of one gain.
            ex, ey = pos[0]-W/2, pos[1]-H/2
            pan_deg = float(np.clip(pan_deg - args.gain*ex, 20, 160))
            tilt_deg = float(np.clip(tilt_deg + args.gain*ey, 40, 140))
            send()
            if not laser:
                laser = True; ard.write(b"L1")
        elif laser:
            laser = False; ard.write(b"L0")

        col = (80, 220, 120) if beacon else (60, 60, 230)
        cv2.circle(frame, pos, 18, col, 2)
        cv2.putText(frame,
                    f"{'LOCKED' if beacon else 'searching'}  blink {score:.2f}  "
                    f"pan {pan_deg:.0f}  tilt {tilt_deg:.0f}",
                    (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
        cv2.imshow("ZeroDrift mini-rig", frame)

        k = cv2.waitKey(1) & 0xFF
        if k == ord('q'):
            break
        elif k == ord('c'):
            pan_deg = tilt_deg = 90.0; send()
        elif k == ord('l'):
            laser = not laser; ard.write(b"L1" if laser else b"L0")
        elif k == 81: pan_deg = max(20, pan_deg-2); send()    # left
        elif k == 83: pan_deg = min(160, pan_deg+2); send()   # right
        elif k == 82: tilt_deg = max(40, tilt_deg-2); send()  # up
        elif k == 84: tilt_deg = min(140, tilt_deg+2); send() # down

    ard.write(b"L0"); cap.release(); cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
