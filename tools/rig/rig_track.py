"""
ZeroDrift mini-rig: steer a laser onto a beacon identified by its blink.

Detection core, rebuilt around one idea: *ask every pixel how much of its
variance sits at the beacon frequency, and take the winner.* The old approach
-- find the brightest spot, then test whether it blinks -- fails whenever
something bright and non-blinking (a finger, a mouth, a lamp) outshines the
beacon, because the wrong thing gets picked before the blink test ever runs.

Three things make this work in a real room:

* **Manual exposure.** With auto-exposure on, the camera reacts to the
  beacon's own blink: LED on -> whole frame darkens, LED off -> whole frame
  brightens. Every pixel then oscillates at the beacon frequency and
  *everything* looks like a beacon. This is the single worst failure mode.
* **Common-mode rejection.** Each frame is divided by its own mean, so any
  residual global gain swing cancels and only genuinely local modulation
  survives -- the same reason the simulator treats turbulence tip/tilt as
  partly common-mode and differences it away.
* **A frequency band, not a single bin.** Phone strobe apps are rarely at
  exactly 4.00 Hz, so a band is searched and the detected rate reported.

    python rig_track.py                    # auto-detects the Arduino
    python rig_track.py --diagnose 12      # headless: measure and write a report
    python rig_track.py --no-rig           # camera only, no hardware needed

Keys:  arrows = manual trim   c = centre   l = laser toggle   q = quit
Safety: 5 mW class laser -- never point at eyes; keep the firmware's limits.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
import time
import traceback

import cv2
import numpy as np


# --------------------------------------------------------------- hardware

def find_arduino_port():
    """Best guess at the Nano's port, so the packaged .exe needs no arguments."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return None
    ports = list(list_ports.comports())
    likely = [p for p in ports if any(k in (p.description or "") for k in
              ("Arduino", "CH340", "FTDI", "USB Serial", "USB-SERIAL"))]
    rest = [p for p in ports if "Bluetooth" not in (p.description or "")]
    picks = likely or rest
    return picks[0].device if picks else None


class Rig:
    """The Nano: two servos and a laser, behind a small command surface."""

    def __init__(self, port, baud=115200):
        import serial
        self.ser = serial.Serial(port, baud, timeout=0.01)
        time.sleep(2.0)                    # the Nano reboots when the port opens
        self.pan = self.tilt = 90.0
        self.laser = False
        self._send()

    def _send(self):
        self.ser.write(f"P{int(self.pan)} T{int(self.tilt)}\n".encode())

    def aim(self, pan, tilt):
        self.pan = float(np.clip(pan, 20, 160))
        self.tilt = float(np.clip(tilt, 40, 140))
        self._send()

    def set_laser(self, on):
        if on != self.laser:
            self.laser = on
            self.ser.write(b"L1" if on else b"L0")

    def close(self):
        try:
            self.set_laser(False)
            self.aim(90, 90)
            self.ser.close()
        except Exception:
            pass


def open_camera(index, width, height, exposure):
    """Open the camera, preferring a backend that lets us pin the exposure.

    Returns (cap, backend_name, exposure_locked).
    """
    for name, backend in (("DSHOW", cv2.CAP_DSHOW),
                          ("MSMF", cv2.CAP_MSMF),
                          ("default", cv2.CAP_ANY)):
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            locked = False
            if exposure is not None:
                # "manual" is 0.25 on V4L2-style backends and 0 on DSHOW;
                # set both, then confirm by reading the property back.
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)
                locked = cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
                cap.set(cv2.CAP_PROP_AUTO_WB, 0)
            ok, _ = cap.read()
            if ok:
                return cap, name, bool(locked)
        cap.release()
    return None, None, False


# --------------------------------------------------------------- detection

class BlinkFinder:
    """Per-pixel modulation analysis over a rolling window of frames.

    Every pixel gets asked the same question -- what fraction of your
    variance is at the beacon frequency? -- and the beacon is simply the
    argmax. A bright finger scores ~0 no matter how bright it is; a dim LED
    blinking on cue scores near 1.
    """

    def __init__(self, n, size, band, min_swing, min_depth=0.25):
        self.n = n
        self.size = size               # (w, h) working resolution
        self.band = np.asarray(band, dtype=np.float64)
        self.min_swing = min_swing
        self.min_depth = min_depth
        self.frames = collections.deque(maxlen=n)
        self.times = collections.deque(maxlen=n)
        self.means = collections.deque(maxlen=n)

    def push(self, gray):
        small = cv2.resize(gray, self.size, interpolation=cv2.INTER_AREA)
        self.frames.append(small.astype(np.float32))
        self.times.append(time.time())
        self.means.append(float(small.mean()) + 1e-6)

    @property
    def ready(self):
        return len(self.frames) == self.n and self.times[-1] > self.times[0]

    @property
    def fps(self):
        if len(self.times) < 2 or self.times[-1] <= self.times[0]:
            return 0.0
        return (len(self.times) - 1) / (self.times[-1] - self.times[0])

    def analyse(self):
        """(score_map, freq, fps, exposure_hunting) -- map is None if not ready."""
        if not self.ready:
            return None, 0.0, self.fps, 0.0
        fps = self.fps
        if fps < 2.5 * float(self.band.max()):        # below Nyquist + margin
            return None, 0.0, fps, 0.0

        raw = np.stack(self.frames)                          # (N, h, w), 0..255
        m = np.asarray(self.means, dtype=np.float32)
        x = raw / m[:, None, None]            # first-order common-mode rejection
        pix_mean = x.mean(axis=0)
        x -= pix_mean

        # Whatever global swing survives that division (clipped highlights make
        # the cancellation imperfect) is measured once and regressed out of
        # every pixel. Without this, a saturated non-blinking highlight still
        # pulses in step with the camera's gain and looks like a beacon.
        g = x.mean(axis=(1, 2))
        gg = float(g @ g)
        if gg > 1e-9:
            x -= g[:, None, None] * (np.tensordot(g, x, axes=(0, 0)) / gg)

        power = np.einsum("ijk,ijk->jk", x, x) + 1e-9
        idx = np.arange(self.n)

        maps = []
        for f in self.band:
            w = np.exp(-2j*np.pi*(f/fps)*idx).astype(np.complex64)
            coef = np.tensordot(w, x, axes=(0, 0))
            frac = np.minimum(1.0, (2.0*np.abs(coef)**2 / self.n) / power)
            # A real beacon goes dark: it swings a large fraction of its own
            # brightness. A bright surface merely riding the camera's gain
            # wobbles by a few percent. That difference is the discriminator
            # that brightness alone could never provide.
            depth = (2.0*np.abs(coef) / self.n) / (pix_mean + 1e-6)
            frac[depth < self.min_depth] = 0.0
            maps.append(frac)
        maps = np.stack(maps)

        # A pixel that barely changes can show a high *fraction* on pure
        # noise, so require a real swing before believing it.
        swing = np.sqrt(power / self.n)
        maps[:, swing < self.min_swing] = 0.0

        flat = int(maps.argmax())
        fi = flat // (maps.shape[1] * maps.shape[2])
        return maps.max(axis=0), float(self.band[fi]), fps, self._hunting(fps)

    @staticmethod
    def noise_floor(score_map):
        """What this frame's *background* is scoring, as a CFAR reference.

        Searching tens of thousands of pixels across several frequencies means
        the best pure-noise pixel scores surprisingly high, so a fixed
        threshold either drowns in false locks or misses real beacons when the
        light changes. Comparing the peak against the population it came from
        is the same constant-false-alarm-rate idea the simulator's detector
        uses, and it re-calibrates itself every frame.
        """
        return float(np.percentile(score_map, 99.0))

    def _hunting(self, fps):
        """How much the *whole frame's* brightness modulates in-band.

        High means auto-exposure is chasing the beacon, which makes every
        pixel look like it is blinking. This is diagnosis, not a fix.
        """
        m = np.asarray(self.means, dtype=np.float64)
        m -= m.mean()
        denom = float(m @ m) + 1e-9
        best = 0.0
        for f in self.band:
            w = np.exp(-2j*np.pi*(f/fps)*np.arange(len(m)))
            best = max(best, 2.0*abs(m @ w)**2 / (denom * len(m)))
        return min(1.0, best)


def local_peak(gray, pos, roi, kernel):
    """Brightest local feature near `pos`, for cheap frame-to-frame tracking."""
    h, w = gray.shape
    x, y = int(pos[0]), int(pos[1])
    x0, x1 = max(0, x-roi), min(w, x+roi+1)
    y0, y1 = max(0, y-roi), min(h, y+roi+1)
    patch = gray[y0:y1, x0:x1]
    if patch.size == 0:
        return None
    hat = cv2.morphologyEx(patch, cv2.MORPH_TOPHAT, kernel)
    _, _, _, loc = cv2.minMaxLoc(cv2.GaussianBlur(hat, (5, 5), 0))
    return (x0 + loc[0], y0 + loc[1])


# ------------------------------------------------------------------ display

def draw_hud(frame, state, score, freq, fps, rig, laser, backend, warn):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 62), (25, 25, 25), -1)
    cv2.rectangle(overlay, (0, h-30), (w, h), (25, 25, 25), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    cv2.putText(frame, "ZERODRIFT  |  SIH26169 coarse-alignment demo",
                (14, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (170, 170, 170), 1, cv2.LINE_AA)

    col = (80, 220, 120) if state == "LOCKED" else (70, 110, 230)
    cv2.putText(frame, state, (14, 47), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2, cv2.LINE_AA)
    cv2.putText(frame,
                f"blink {score:.2f}   {freq:.2f} Hz   {fps:.0f} fps   "
                f"{backend}   rig {'on' if rig else 'OFF'}   "
                f"laser {'ON' if laser else 'off'}",
                (150, 47), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (225, 225, 225), 1, cv2.LINE_AA)

    dot = (0, 0, 255) if laser else (80, 80, 80)
    cv2.circle(frame, (w-22, 20), 8, dot, -1)
    cv2.circle(frame, (w-22, 20), 8, (200, 200, 200), 1)

    cx, cy = w//2, h//2
    cv2.line(frame, (cx-12, cy), (cx+12, cy), (110, 110, 110), 1)
    cv2.line(frame, (cx, cy-12), (cx, cy+12), (110, 110, 110), 1)

    if warn:
        cv2.putText(frame, warn, (14, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (60, 200, 245), 2, cv2.LINE_AA)

    cv2.putText(frame, "q quit   c centre   l laser   arrow keys trim",
                (14, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 160, 160), 1, cv2.LINE_AA)


def show_message(text, seconds=7):
    """The only way to report a problem when there is no console (packaged .exe)."""
    img = np.zeros((260, 720, 3), dtype=np.uint8)
    for i, line in enumerate(text.split("\n")):
        cv2.putText(img, line, (20, 40 + i*32), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (70, 70, 235), 2, cv2.LINE_AA)
    cv2.imshow("ZeroDrift mini-rig", img)
    cv2.waitKey(int(seconds * 1000))
    cv2.destroyAllWindows()


# ---------------------------------------------------------------- main loop

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None, help="Arduino port; auto-detected if omitted")
    ap.add_argument("--no-rig", action="store_true",
                    help="camera only -- run the vision side with no hardware")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--exposure", type=float, default=-6.0,
                    help="manual exposure (log2 seconds on Windows). Pinning "
                         "this is what stops the camera chasing the beacon's "
                         "own blink; pass 0 to leave it on auto")
    ap.add_argument("--blink", type=float, default=4.0, help="beacon rate, Hz")
    ap.add_argument("--band", type=float, default=1.0,
                    help="+/- Hz searched around --blink, since phone strobe "
                         "apps are rarely exact")
    ap.add_argument("--history", type=int, default=72,
                    help="frames per analysis window; longer means a lower "
                         "noise floor and sharper frequency discrimination, "
                         "at the cost of slower acquisition")
    ap.add_argument("--work-width", type=int, default=192,
                    help="width the modulation map is computed at")
    ap.add_argument("--lock-threshold", type=float, default=0.40,
                    help="absolute floor on the in-band variance fraction")
    ap.add_argument("--cfar", type=float, default=2.5,
                    help="how many times the background score the peak must "
                         "reach before it counts as a beacon; this is what "
                         "keeps sensor noise from producing phantom locks")
    ap.add_argument("--min-swing", type=float, default=0.04,
                    help="minimum relative brightness swing before a pixel is "
                         "believed at all (rejects noise in flat regions)")
    ap.add_argument("--min-depth", type=float, default=0.25,
                    help="minimum modulation depth (swing as a fraction of the "
                         "pixel's own brightness). A real blinker goes dark; a "
                         "bright surface riding the camera's gain barely dips")
    ap.add_argument("--acq-every", type=int, default=3,
                    help="run the full modulation map every N frames")
    ap.add_argument("--roi", type=int, default=60, help="tracking search radius, px")
    ap.add_argument("--gain", type=float, default=0.02, help="servo deg per px of error")
    ap.add_argument("--lead", type=float, default=2.5,
                    help="frames of motion lead, so the laser aims where the "
                         "beacon is going rather than where it was")
    ap.add_argument("--diagnose", type=float, default=0.0,
                    help="run headless for N seconds and write rig_report.json")
    args = ap.parse_args()

    band = [args.blink]
    if args.band > 0:
        band = list(np.arange(args.blink - args.band, args.blink + args.band + 1e-9, 0.25))
        band = [f for f in band if f > 0.5]

    exposure = None if args.exposure == 0 else args.exposure
    cap, backend, locked = open_camera(args.camera, args.width, args.height, exposure)
    if cap is None:
        show_message("No camera available.\n"
                     "Check Settings > Privacy > Camera, and that no other\n"
                     "app is using it, then relaunch.")
        return 1

    rig = None
    rig_error = ""
    if not args.no_rig:
        port = args.port or find_arduino_port()
        if port:
            try:
                rig = Rig(port)
            except Exception as e:                  # keep the demo alive
                rig_error = f"rig offline ({e.__class__.__name__})"
        else:
            rig_error = "rig offline (no Arduino found)"

    ok, frame = cap.read()
    if not ok:
        show_message("Camera opened but delivered no frames.")
        return 1
    h, w = frame.shape[:2]
    work = (args.work_width, max(2, int(round(args.work_width * h / w))))
    finder = BlinkFinder(args.history, work, band, args.min_swing, args.min_depth)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
    sx, sy = w / work[0], h / work[1]

    state, pos, vel = "SEARCHING", None, (0.0, 0.0)
    freq, score, misses, frame_idx = args.blink, 0.0, 0, 0
    hunting, fps, margin = 0.0, 0.0, 0.0
    samples = []
    t_start = time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            finder.push(gray)

            if frame_idx % args.acq_every == 0:
                smap, f_hat, fps, hunting = finder.analyse()
                if smap is not None:
                    my, mx = np.unravel_index(int(smap.argmax()), smap.shape)
                    score = float(smap[my, mx])
                    floor = finder.noise_floor(smap)
                    margin = score / (floor + 1e-6)
                    if score > args.lock_threshold and margin > args.cfar:
                        found = (mx * sx + sx/2, my * sy + sy/2)
                        if pos is not None:
                            vel = ((found[0]-pos[0])/args.acq_every,
                                   (found[1]-pos[1])/args.acq_every)
                        pos, freq, misses = found, f_hat, 0
                        state = "LOCKED"
                    elif state == "LOCKED":
                        misses += 1
                        if misses > 3:
                            state, pos, vel = "SEARCHING", None, (0.0, 0.0)

            if state == "LOCKED" and pos is not None:
                # Between analyses, follow the beacon cheaply so fast motion
                # stays tracked at full frame rate.
                found = local_peak(gray, pos, args.roi, kernel)
                if found is not None:
                    vel = (0.6*vel[0] + 0.4*(found[0]-pos[0]),
                           0.6*vel[1] + 0.4*(found[1]-pos[1]))
                    pos = found
                if rig is not None:
                    ex = pos[0] + args.lead*vel[0] - w/2
                    ey = pos[1] + args.lead*vel[1] - h/2
                    rig.aim(rig.pan - args.gain*ex, rig.tilt + args.gain*ey)
                    rig.set_laser(True)
            elif rig is not None:
                rig.set_laser(False)

            if args.diagnose:
                samples.append({"t": round(time.time()-t_start, 2), "state": state,
                                "score": round(score, 3), "margin": round(margin, 2),
                                "freq": round(freq, 2),
                                "fps": round(fps, 1), "hunting": round(hunting, 3),
                                "pos": None if pos is None else [round(p) for p in pos]})
                if time.time() - t_start >= args.diagnose:
                    break
                continue

            warn = rig_error
            if fps and fps < 2.5*max(band):
                warn = f"frame rate too low ({fps:.0f} fps) to see a {max(band):.1f} Hz blink"
            elif hunting > 0.25:
                warn = "auto-exposure is chasing the beacon - pin the exposure"
            if state == "LOCKED" and pos is not None:
                p = (int(pos[0]), int(pos[1]))
                cv2.circle(frame, p, 18, (80, 220, 120), 2)
                cv2.circle(frame, p, 26, (80, 220, 120), 1)
            draw_hud(frame, state, score, freq, fps, rig is not None,
                     rig.laser if rig else False, backend, warn)
            cv2.imshow("ZeroDrift mini-rig", frame)

            k = cv2.waitKey(1) & 0xFF
            if k == ord('q'):
                break
            elif rig is not None:
                if k == ord('c'):
                    rig.aim(90, 90)
                elif k == ord('l'):
                    rig.set_laser(not rig.laser)
                elif k == 81: rig.aim(rig.pan-2, rig.tilt)
                elif k == 83: rig.aim(rig.pan+2, rig.tilt)
                elif k == 82: rig.aim(rig.pan, rig.tilt-2)
                elif k == 84: rig.aim(rig.pan, rig.tilt+2)
    finally:
        if rig is not None:
            rig.close()
        cap.release()
        cv2.destroyAllWindows()

    if args.diagnose:
        locks = [s for s in samples if s["state"] == "LOCKED"]
        report = {
            "camera": {"backend": backend, "resolution": [w, h],
                       "exposure_locked": locked, "exposure": args.exposure},
            "rig": rig_error or "connected",
            "frames": len(samples),
            "median_fps": float(np.median([s["fps"] for s in samples] or [0])),
            "best_score": max([s["score"] for s in samples] or [0]),
            "median_score": float(np.median([s["score"] for s in samples] or [0])),
            "best_cfar_margin": max([s["margin"] for s in samples] or [0]),
            "median_cfar_margin": float(np.median([s["margin"] for s in samples] or [0])),
            "locked_fraction": round(len(locks)/max(1, len(samples)), 3),
            "detected_hz": [s["freq"] for s in locks[-5:]],
            "exposure_hunting": max([s["hunting"] for s in samples] or [0]),
            "band_searched": [round(f, 2) for f in band],
            "tail": samples[-15:],
        }
        out = pathlib.Path(__file__).resolve().parent / "rig_report.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        base = pathlib.Path(sys.executable if getattr(sys, "frozen", False)
                            else __file__).resolve().parent
        with open(base / "rig_debug.log", "a", encoding="utf-8") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            traceback.print_exc(file=f)
        try:
            show_message("Something went wrong.\nSee rig_debug.log next to this "
                         "program for details.")
        except Exception:
            pass
        code = 1
    raise SystemExit(code)
