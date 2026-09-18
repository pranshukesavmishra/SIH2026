"""
Driver for the Mk2 rig (rig_firmware_v2.ino): steppers + fine servos.

Speaks the v2 serial protocol exactly as the firmware parses it
(115200 baud, newline-terminated):

    P<int> T<int>   coarse pan/tilt target, in MOTOR STEPS from centre
    p<int> t<int>   fine pan/tilt target, in SERVO DEGREES (20-160 / 40-140)
    L0 / L1         laser off / on
    V0 / V1         vibration injector off / on

Angles are radians at this interface, as everywhere else in the engine;
steps and degrees exist only on the wire. The step scale defaults to a
NEMA17's 200 steps/rev at 16x microstepping and is overridden by the
calibration file once `hil.calibrate` has measured the real value --
measure, never assume.

Safety envelope, independent of what the tracking logic asks for: commanded
coarse moves are rate- and step-limited in software (the Mk1 tilt servo died
from being driven into a bind; the Mk2's steppers can stall and skip), and
a ``dry_run`` mode captures every line that WOULD go on the wire, so the
whole stack -- engine, server, dashboard -- runs and is testable with no
hardware plugged in.
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple

import numpy as np

# NEMA17: 200 full steps/rev; A4988-class drivers ship strapped for 16x
# microstepping on most breakout boards. 3200 microsteps / 2*pi rad.
DEFAULT_STEPS_PER_RAD = 200.0 * 16.0 / (2.0 * np.pi)

FINE_PAN_LIMITS = (20, 160)     # firmware's own constrain() bounds
FINE_TILT_LIMITS = (40, 140)


class Mk2Gimbal:
    """The Mk2 pan-tilt behind the same command surface the engine expects."""

    def __init__(self, port: Optional[str], baud: int = 115200,
                 steps_per_rad: Tuple[float, float] = (DEFAULT_STEPS_PER_RAD,
                                                       DEFAULT_STEPS_PER_RAD),
                 fine_deg_per_rad: Tuple[float, float] = (57.29578, 57.29578),
                 coarse_limit_steps: Tuple[int, int] = (1600, 1200),
                 max_step_per_cmd: int = 400,
                 min_interval_s: float = 0.10,
                 dry_run: bool = False):
        self.dry_run = bool(dry_run) or port is None
        self.sent: List[str] = []          # dry-run capture / debug tail
        if not self.dry_run:
            import serial                  # pyserial
            self.ser = serial.Serial(port, baud, timeout=0.05)
            time.sleep(2.5)                # the Nano resets on port open
        else:
            self.ser = None
        self.steps_per_rad = steps_per_rad
        self.fine_deg_per_rad = fine_deg_per_rad
        self.coarse_limit = coarse_limit_steps
        self.max_step = int(max_step_per_cmd)
        self.min_interval = float(min_interval_s)
        self._last_cmd_t = 0.0
        self._pan_steps = 0
        self._tilt_steps = 0
        self.az = 0.0
        self.el = 0.0

    # ---- wire ----------------------------------------------------------
    def _send(self, line: str) -> None:
        self.sent.append(line)
        if len(self.sent) > 200:
            del self.sent[:100]
        if self.ser is not None:
            self.ser.write((line + "\n").encode())

    # ---- coarse stage --------------------------------------------------
    def command(self, az: float, el: float) -> bool:
        """
        Point the coarse stage at (az, el) radians from centre.

        Returns True if a command actually went out; False when the safety
        envelope held it back (too soon since the last one). Moves larger
        than ``max_step_per_cmd`` are truncated toward the target rather
        than rejected -- the next cycle continues the slew.
        """
        now = time.monotonic()
        if now - self._last_cmd_t < self.min_interval:
            return False
        pan = int(round(np.clip(az * self.steps_per_rad[0],
                                -self.coarse_limit[0], self.coarse_limit[0])))
        tilt = int(round(np.clip(el * self.steps_per_rad[1],
                                 -self.coarse_limit[1], self.coarse_limit[1])))
        pan = self._pan_steps + int(np.clip(pan - self._pan_steps,
                                            -self.max_step, self.max_step))
        tilt = self._tilt_steps + int(np.clip(tilt - self._tilt_steps,
                                              -self.max_step, self.max_step))
        if pan == self._pan_steps and tilt == self._tilt_steps:
            return False
        self._send(f"P{pan} T{tilt}")
        self._pan_steps, self._tilt_steps = pan, tilt
        self.az = pan / self.steps_per_rad[0]
        self.el = tilt / self.steps_per_rad[1]
        self._last_cmd_t = now
        return True

    # ---- fine stage ----------------------------------------------------
    def fine(self, d_az: float, d_el: float) -> None:
        """Nudge the fine servos by a residual (radians), centred on 90/90."""
        p = int(round(np.clip(90.0 + d_az * self.fine_deg_per_rad[0],
                              *FINE_PAN_LIMITS)))
        t = int(round(np.clip(90.0 + d_el * self.fine_deg_per_rad[1],
                              *FINE_TILT_LIMITS)))
        self._send(f"p{p} t{t}")

    # ---- accessories ---------------------------------------------------
    def laser(self, on: bool) -> None:
        self._send("L1" if on else "L0")

    def vibration(self, on: bool) -> None:
        self._send("V1" if on else "V0")

    def centre(self) -> None:
        self._send("P0 T0")
        self._send("p90 t90")
        self._pan_steps = self._tilt_steps = 0
        self.az = self.el = 0.0

    def reported_pointing(self) -> Tuple[float, float]:
        # No telemetry echo in the firmware: reported = last commanded,
        # exactly as on Mk1. The real world offers no ground truth here.
        return self.az, self.el

    def close(self) -> None:
        if self.ser is not None:
            self.laser(False)
            self.ser.close()
