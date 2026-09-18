"""
The simulation thread.

The GUI must never run the simulation on the interface thread: a 30 fps loop
doing morphology and Kalman updates would freeze every widget. The worker owns
the simulator and the tracker, emits a downsampled stream of display frames,
and accepts control commands (pause, reset, speed) through Qt's queued signal
mechanism, which is the thread-safe channel PySide provides.

Telemetry is NOT streamed piecemeal: the worker appends to the tracker's own
telemetry list and the GUI reads consistent snapshots on a timer. One producer,
one consumer, no shared mutable iteration.
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..config import SimConfig
from ..metrics import build_report
from ..pipeline import CoarseAlignmentTracker
from ..simulator import Simulator


class SimulationWorker(QObject):
    """Runs one scenario; lives on its own QThread."""

    frame_ready = Signal(object, object)      # (Frame, TrackerTelemetry)
    run_finished = Signal(object)             # PerformanceReport
    status = Signal(str)

    def __init__(self, cfg: SimConfig):
        super().__init__()
        self.cfg = cfg
        self._paused = False
        self._stop = False
        self._realtime = True
        self.simulator: Optional[Simulator] = None
        self.tracker: Optional[CoarseAlignmentTracker] = None
        self._wall_started = 0.0

    # ---- control slots (called via queued connections) -------------------
    @Slot(bool)
    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    @Slot(bool)
    def set_realtime(self, realtime: bool) -> None:
        """True = pace to the camera frame rate; False = run flat out."""
        self._realtime = realtime

    @Slot()
    def stop(self) -> None:
        self._stop = True

    # ---- the loop --------------------------------------------------------
    @Slot()
    def run(self) -> None:
        self.simulator = Simulator(self.cfg)
        self.tracker = CoarseAlignmentTracker(self.cfg)
        dt = self.simulator.dt
        command = None
        total = self.simulator.total_frames
        self._wall_started = time.perf_counter()
        next_deadline = time.perf_counter()

        for _ in range(total):
            if self._stop:
                break
            while self._paused and not self._stop:
                time.sleep(0.05)

            frame = self.simulator.step(command)
            command = self.tracker.update(frame)
            self.frame_ready.emit(frame, self.tracker.telemetry[-1])

            if self._realtime:
                next_deadline += dt
                delay = next_deadline - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_deadline = time.perf_counter()   # fell behind: no debt spiral

        wall = time.perf_counter() - self._wall_started
        report = build_report(self.tracker.telemetry, self.cfg.name,
                              self.cfg.camera.frame_rate_hz, wall_time_s=wall)
        self.run_finished.emit(report)


def start_worker(cfg: SimConfig):
    """Create a worker on a fresh thread; returns (thread, worker)."""
    thread = QThread()
    worker = SimulationWorker(cfg)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.run_finished.connect(thread.quit)
    return thread, worker
