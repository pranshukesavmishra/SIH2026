"""
Zero-cost physical beacon demo: a laptop webcam finds and identifies a
BLINKING phone flashlight across the room, using the same two principles
as the full simulator (bright-spot detection + blink-signature gating),
in a deliberately simplified standalone form.

    pip install opencv-python numpy
    python tools/webcam_beacon_demo.py            # default camera 0
    python tools/webcam_beacon_demo.py --blink 4  # expected blink rate (Hz)

Point any phone at the camera running a strobe/blink app at ~4 Hz.
Steady lights (bulbs, windows, a second NON-blinking phone) are rejected:
their 4 Hz score stays near zero — exactly how the real system rejects
stars and glints. Press q to quit.
"""
import argparse
import collections
import time

import cv2
import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--blink", type=float, default=4.0, help="expected blink Hz")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print("no camera found"); return 1

    N = 64                                   # analysis window (frames)
    history = collections.deque(maxlen=N)    # brightness at tracked spot
    times = collections.deque(maxlen=N)
    pos = None

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # top-hat: remove smooth background, keep small bright things
        tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT,
                                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
        blur = cv2.GaussianBlur(tophat, (9, 9), 0)
        _, maxval, _, maxloc = cv2.minMaxLoc(blur)

        # follow the current brightest candidate (sticky within 80 px)
        if pos is None or np.hypot(maxloc[0]-pos[0], maxloc[1]-pos[1]) < 80 or maxval > 60:
            pos = maxloc
        x, y = pos
        patch = gray[max(0, y-6):y+7, max(0, x-6):x+7]
        history.append(float(patch.mean()) if patch.size else 0.0)
        times.append(time.time())

        score = 0.0
        if len(history) == N and times[-1] > times[0]:
            fps = (N - 1) / (times[-1] - times[0])
            sig = np.array(history) - np.mean(history)
            # Goertzel-style: power at the expected blink frequency,
            # normalised by total power — same idea as the real gate
            k = args.blink / fps * N
            w = np.exp(-2j * np.pi * k * np.arange(N) / N)
            p_blink = abs(np.dot(sig, w)) ** 2
            p_total = float(np.dot(sig, sig)) + 1e-9
            score = min(1.0, 2.0 * p_blink / (p_total * N / 2))

        beacon = score > 0.35
        color = (80, 220, 120) if beacon else (60, 60, 230)
        label = f"BEACON CONFIRMED  blink score {score:.2f}" if beacon else \
                f"candidate — not blinking at {args.blink:g} Hz (score {score:.2f})"
        cv2.circle(frame, pos, 18, color, 2)
        cv2.putText(frame, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(frame, "ZeroDrift zero-cost beacon demo  --  q to quit",
                    (12, frame.shape[0]-12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.imshow("ZeroDrift webcam beacon demo", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release(); cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
