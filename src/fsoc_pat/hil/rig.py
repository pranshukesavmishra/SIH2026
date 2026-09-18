"""
Drivers for the physical rig, behind the same contracts as the simulation.

The design rule for this package: the detector, tracker, estimator and
controller must not know whether they are running against the simulator or
against a webcam and two servos. Everything hardware-specific lives here, and
everything here presents interfaces the virtual counterparts already defined.
That is the transfer claim -- "the identical code drives real optics" -- and
it is enforced by construction, not by a diagram.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class LiveFrame:
    """Duck-typed stand-in for simulator.Frame: same fields the tracker reads."""
    index: int
    time_s: float
    image: np.ndarray
    pointing_true: Tuple[float, float]        # best knowledge = reported
    pointing_reported: Tuple[float, float]
    dropped: bool = False
    targets: List = field(default_factory=list)
    glint: Optional[tuple] = None

    @property
    def primary(self):
        return None                            # no ground truth in the real world


class SerialGimbal:
    """
    The Nano pan-tilt (rig_firmware.ino), presenting the virtual Gimbal's
    command surface.

    Angles are radians at this interface, exactly as in the simulation;
    degrees exist only on the wire. The firmware's actual protocol is
    strict about it: integer degrees, "P<pan> T<tilt>\\n" with no space
    after P and no decimals (it parses with sscanf "%d"), no query
    command, no centre command -- it only understands P/T and L0/L1.
    There is no telemetry echo, so `reported_pointing` returns the last
    commanded position rather than reading hardware state back; the real
    world offers no ground truth here anyway (see LiveFrame.primary).
    """

    PAN_LIMITS = (20, 160)     # matches the firmware's own constrain()
    TILT_LIMITS = (40, 140)

    def __init__(self, port: str, baud: int = 115200,
                 counts_per_rad: Tuple[float, float] = (1.0, 1.0),
                 offset_rad: Tuple[float, float] = (0.0, 0.0)):
        import serial                                    # pyserial
        self.ser = serial.Serial(port, baud, timeout=0.05)
        time.sleep(2.5)                                  # Nano resets on open
        self.scale = counts_per_rad                      # calibration output
        self.offset = offset_rad
        self.az = 0.0
        self.el = 0.0

    def raw_command(self, pan_deg: float, tilt_deg: float) -> None:
        """Send an absolute P/T command exactly as the firmware expects it."""
        pan = int(round(np.clip(pan_deg, *self.PAN_LIMITS)))
        tilt = int(round(np.clip(tilt_deg, *self.TILT_LIMITS)))
        self.ser.write(f"P{pan} T{tilt}\n".encode())

    def command(self, az: float, el: float) -> None:
        pan = np.degrees((az - self.offset[0]) * self.scale[0]) + 90.0
        tilt = np.degrees((el - self.offset[1]) * self.scale[1]) + 90.0
        self.raw_command(pan, tilt)
        self.az, self.el = az, el

    def reported_pointing(self) -> Tuple[float, float]:
        return self.az, self.el

    def centre(self) -> None:
        self.raw_command(90, 90)
        self.az, self.el = 0.0, 0.0

    def laser(self, on: bool) -> None:
        self.ser.write(b"L1" if on else b"L0")


class UsbCamera:
    """A UVC camera with manual exposure, delivering grayscale frames."""

    def __init__(self, index: int = 0, width: int = 640, height: int = 480,
                 exposure: Optional[float] = None, gain: Optional[float] = None):
        import cv2
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if exposure is not None:
            # Auto-exposure hunts on every beacon blink; manual is mandatory.
            # V4L2 (Linux) wants CAP_PROP_AUTO_EXPOSURE=0.25 for manual mode;
            # AVFoundation (macOS) wants the flag at 0 instead and largely
            # ignores CAP_PROP_EXPOSURE's absolute scale -- so try both and
            # don't treat either failing as fatal, just best-effort locking.
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)   # V4L2: manual
            self.cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)      # AVFoundation: manual
            self.cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
        if gain is not None:
            self.cap.set(cv2.CAP_PROP_GAIN, gain)
        self._cv2 = cv2

    def read(self) -> Optional[np.ndarray]:
        ok, frame = self.cap.read()
        if not ok:
            return None
        gray = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2GRAY)
        # The pipeline was built against 12-bit frames; scale 8-bit up so
        # every threshold and normalisation carries over unchanged.
        return (gray.astype(np.uint16) << 4)

    def release(self) -> None:
        self.cap.release()


def find_serial_port() -> Optional[str]:
    """
    Best-effort auto-detect of the Arduino: scan the system's serial ports
    for one that looks like a USB-serial adapter (CH340/CP210x/FTDI-style
    names on macOS/Linux, or any COMx on Windows) rather than a Bluetooth
    or virtual/debug port. Returns None if nothing plausible is found --
    callers should fall back to asking the user.
    """
    from serial.tools import list_ports

    candidates = list(list_ports.comports())
    if not candidates:
        return None

    def score(p) -> int:
        dev = (p.device or "").lower()
        desc = (p.description or "").lower()
        s = 0
        if "usbserial" in dev or "wchusbserial" in dev or "usbmodem" in dev:
            s += 10
        if "ch340" in desc or "ch34" in desc:
            s += 8
        if "cp210" in desc:
            s += 8
        if "ftdi" in desc or "ft232" in desc:
            s += 8
        if "arduino" in desc:
            s += 8
        if dev.startswith("/dev/cu.") and "bluetooth" not in dev and "debug" not in dev:
            s += 3
        if dev.upper().startswith("COM"):
            s += 3
        if "bluetooth" in dev or "debug" in dev:
            s -= 20
        return s

    best = max(candidates, key=score)
    return best.device if score(best) > 0 else None


def find_camera(max_index: int = 4) -> Optional[int]:
    """
    Best-effort auto-detect of a working camera: try indices in order and
    return the first one that actually opens and yields a real frame.
    Distinguishes "no camera" from "camera present but access denied" so
    callers can tell the user which problem they actually have.
    """
    import cv2

    for idx in range(max_index):
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            continue
        ok, frame = cap.read()
        cap.release()
        if ok and frame is not None:
            return idx
    return None
