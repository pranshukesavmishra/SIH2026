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
    The ESP32 pan-tilt, presenting the virtual Gimbal's command surface.

    Angles are radians at this interface, exactly as in the simulation;
    degrees exist only on the wire.
    """

    def __init__(self, port: str, baud: int = 115200,
                 counts_per_rad: Tuple[float, float] = (1.0, 1.0),
                 offset_rad: Tuple[float, float] = (0.0, 0.0)):
        import serial                                    # pyserial
        self.ser = serial.Serial(port, baud, timeout=0.05)
        time.sleep(2.0)                                  # ESP32 reset on open
        self.scale = counts_per_rad                      # calibration output
        self.offset = offset_rad
        self.az = 0.0
        self.el = 0.0

    def command(self, az: float, el: float) -> None:
        pan = np.degrees((az - self.offset[0]) * self.scale[0])
        tilt = np.degrees((el - self.offset[1]) * self.scale[1])
        self.ser.write(f"P {pan:.3f} {tilt:.3f}\n".encode())

    def reported_pointing(self) -> Tuple[float, float]:
        self.ser.write(b"?\n")
        deadline = time.time() + 0.1
        while time.time() < deadline:
            line = self.ser.readline().decode(errors="ignore").strip()
            if line.startswith("S "):
                _, pan, tilt, _ = line.split()
                self.az = np.radians(float(pan)) / self.scale[0] + self.offset[0]
                self.el = np.radians(float(tilt)) / self.scale[1] + self.offset[1]
                break
        return self.az, self.el

    def centre(self) -> None:
        self.ser.write(b"C\n")


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
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)   # V4L2: manual
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
