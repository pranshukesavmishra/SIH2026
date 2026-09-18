"""ZeroDrift Mini-Rig Mk2 — ground-truth accuracy logger. DRAFT, not yet
run against real hardware — verify the laser-dot detection thresholds
against your actual camera/lighting before trusting the numbers.

Runs as a second process alongside rig_track.py / rig_track (Mk2),
watching a fixed printed target board through a second camera (a spare
phone as an IP webcam works fine) and measuring how far the laser dot
sits from the target's true center, converted to a real angular error.

Setup:
  1. Print a target with a clear center mark (crosshair or bullseye) and
     a reference object of KNOWN width next to it (e.g. a 50mm square).
  2. Mount the target at a MEASURED distance from the rig (in mm).
  3. Point this script's camera at the target, run it, and follow the
     on-screen calibration clicks.

Usage:
  python tools/rig/accuracy_logger.py --camera 1 --distance-mm 2000

Output: live overlay + a CSV log of every frame's measured error.
"""
import argparse
import csv
import math
import time

import cv2
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--camera", type=int, default=0, help="observer camera index")
    p.add_argument("--distance-mm", type=float, required=True,
                    help="measured distance from rig to target board, in mm")
    p.add_argument("--out", default="rig_accuracy_log.csv", help="CSV log path")
    p.add_argument("--min-brightness", type=int, default=220,
                    help="laser dot detection threshold (0-255); raise if it "
                         "false-triggers on ambient light, lower if it misses "
                         "a dim dot")
    return p.parse_args()


class Calibrator:
    """Two clicks to set the target center, two more for a known-length
    reference segment, to derive mm-per-pixel."""

    def __init__(self, window):
        self.window = window
        self.points = []
        cv2.setMouseCallback(window, self._on_click)

    def _on_click(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.points.append((x, y))

    def run(self, frame):
        prompts = [
            "Click the TARGET CENTER",
            "Click one end of a KNOWN-LENGTH reference object",
            "Click the other end of that reference object",
        ]
        self.points = []
        while len(self.points) < 3:
            disp = frame.copy()
            idx = min(len(self.points), 2)
            cv2.putText(disp, prompts[idx], (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            for pt in self.points:
                cv2.circle(disp, pt, 5, (0, 255, 0), -1)
            cv2.imshow(self.window, disp)
            if cv2.waitKey(20) & 0xFF == ord("q"):
                raise SystemExit
        target_center = self.points[0]
        ref_a, ref_b = self.points[1], self.points[2]
        ref_px = math.hypot(ref_b[0] - ref_a[0], ref_b[1] - ref_a[1])
        return target_center, ref_px


def find_laser_dot(frame, min_brightness):
    """Brightest-blob detection biased toward red — swap for your actual
    laser's color/wavelength if it's not a standard red 650nm module."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, bright_mask = cv2.threshold(gray, min_brightness, 255, cv2.THRESH_BINARY)
    red_mask = cv2.inRange(hsv, (0, 80, 150), (10, 255, 255)) | \
               cv2.inRange(hsv, (170, 80, 150), (180, 255, 255))
    mask = cv2.bitwise_and(bright_mask, red_mask) if cv2.countNonZero(red_mask) else bright_mask
    mask = cv2.bitwise_or(mask, bright_mask)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < 2:
        return None
    m = cv2.moments(c)
    if m["m00"] == 0:
        return None
    return (m["m10"] / m["m00"], m["m01"] / m["m00"])


def main():
    args = parse_args()
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera {args.camera}")

    window = "ZeroDrift Mk2 — accuracy logger"
    cv2.namedWindow(window)
    ok, frame = cap.read()
    if not ok:
        raise SystemExit("Could not read a frame to calibrate against")

    ref_mm = float(input("Enter the reference object's real length in mm: "))
    calib = Calibrator(window)
    target_center, ref_px = calib.run(frame)
    mm_per_px = ref_mm / ref_px
    print(f"Calibrated: {mm_per_px:.4f} mm/px at {args.distance_mm:.0f} mm distance")

    log_file = open(args.out, "w", newline="")
    writer = csv.writer(log_file)
    writer.writerow(["t_s", "dx_px", "dy_px", "error_mm", "error_urad", "laser_visible"])
    t0 = time.time()

    errors_urad = []
    print("Logging — press q to stop.")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        dot = find_laser_dot(frame, args.min_brightness)
        t = time.time() - t0

        disp = frame.copy()
        cv2.drawMarker(disp, (int(target_center[0]), int(target_center[1])),
                        (0, 255, 0), cv2.MARKER_CROSS, 20, 2)

        if dot is not None:
            dx_px = dot[0] - target_center[0]
            dy_px = dot[1] - target_center[1]
            error_mm = math.hypot(dx_px, dy_px) * mm_per_px
            error_urad = (error_mm / args.distance_mm) * 1e6
            errors_urad.append(error_urad)
            writer.writerow([f"{t:.3f}", f"{dx_px:.1f}", f"{dy_px:.1f}",
                              f"{error_mm:.2f}", f"{error_urad:.1f}", 1])
            cv2.circle(disp, (int(dot[0]), int(dot[1])), 6, (0, 0, 255), 2)
            cv2.line(disp, (int(target_center[0]), int(target_center[1])),
                      (int(dot[0]), int(dot[1])), (0, 255, 255), 1)
            cv2.putText(disp, f"error: {error_urad:.0f} urad ({error_mm:.1f} mm)",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        else:
            writer.writerow([f"{t:.3f}", "", "", "", "", 0])
            cv2.putText(disp, "laser dot not detected", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        cv2.imshow(window, disp)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    log_file.close()
    cap.release()
    cv2.destroyAllWindows()

    if errors_urad:
        arr = np.array(errors_urad)
        print(f"\n{len(arr)} samples logged to {args.out}")
        print(f"median error: {np.median(arr):.0f} urad")
        print(f"p95 error:    {np.percentile(arr, 95):.0f} urad")
        print(f"max error:    {arr.max():.0f} urad")
    else:
        print("\nNo laser dot detected in any frame — check --min-brightness "
              "and lighting before trusting a future run.")


if __name__ == "__main__":
    main()
