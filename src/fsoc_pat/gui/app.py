"""
The main window: camera view left, live plots right, controls far right,
status bar with the headline numbers.

    python -m fsoc_pat.gui.app [scenario.yaml]

Display updates are decoupled from simulation frames: the worker emits every
frame, but the view repaints on a 30 ms timer using only the latest one, so a
faster-than-real-time run does not flood the paint queue.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QSplitter, QStatusBar,
                               QWidget)

from ..config import SimConfig
from ..metrics import PerformanceReport
from .controls import ControlPanel
from .frameview import FrameView
from .plots import PlotStrip
from .worker import start_worker

DEFAULT_SCENARIO = "scenarios/leo_pass_nominal.yaml"


class MainWindow(QMainWindow):
    def __init__(self, scenario_path: str):
        super().__init__()
        self.scenario_path = scenario_path
        self.cfg = SimConfig.load(scenario_path)
        self.setWindowTitle(f"FSOC-PAT coarse alignment — {self.cfg.name}")
        self.resize(1440, 860)

        self.frame_view = FrameView()
        self.plots = PlotStrip(self.cfg.camera.fov_deg)
        self.controls = ControlPanel(self.cfg)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.frame_view)
        splitter.addWidget(self.plots)
        splitter.addWidget(self.controls)
        splitter.setSizes([720, 460, 260])
        self.setCentralWidget(splitter)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status_label = QLabel("ready")
        self.status.addWidget(self.status_label)

        self._thread = None
        self._worker = None
        self._latest = None
        self._report: Optional[PerformanceReport] = None

        self._display_timer = QTimer(self)
        self._display_timer.setInterval(33)
        self._display_timer.timeout.connect(self._refresh_display)

        self.controls.run_requested.connect(self.start_run)
        self.controls.stop_requested.connect(self.stop_run)
        self.controls.pause_toggled.connect(self._on_pause)
        self.controls.realtime_toggled.connect(self._on_realtime)
        self.controls.truth_toggled.connect(self._on_truth)
        self.controls.export_requested.connect(self.export_report)
        self.controls.scenario_open_requested.connect(self.open_scenario)
        self.controls.scenario_save_requested.connect(self.save_scenario)

    # ---- run lifecycle ---------------------------------------------------
    @Slot()
    def start_run(self) -> None:
        self.plots.clear()
        self._thread, self._worker = start_worker(self.cfg)
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.run_finished.connect(self._on_finished)
        self._worker.set_realtime(self.controls.realtime_check.isChecked())
        self.controls.set_running(True)
        self._display_timer.start()
        self._thread.start()

    @Slot()
    def stop_run(self) -> None:
        if self._worker is not None:
            self._worker.stop()

    @Slot(object, object)
    def _on_frame(self, frame, telemetry) -> None:
        self._latest = (frame, telemetry)
        self.plots.append(telemetry)

    @Slot()
    def _refresh_display(self) -> None:
        if self._latest is None or self._worker is None:
            return
        frame, telemetry = self._latest
        self.frame_view.update_frame(frame, telemetry, self._worker.tracker)
        self.plots.redraw()
        err = ("—" if telemetry.pointing_error_rad is None
               else f"{telemetry.pointing_error_rad * 1e6:.0f} urad")
        # Rolling-mean processing time: the instantaneous value spikes during
        # the acquisition transient (many candidate tracks alive at once) and
        # made the status bar read as a performance problem that wasn't there.
        recent = self._worker.tracker.telemetry[-30:]
        proc = sum(t.processing_ms for t in recent) / max(len(recent), 1)
        self.status_label.setText(
            f"t = {telemetry.time_s:6.1f} s   state {telemetry.state.value:9}   "
            f"pointing error {err}   processing {proc:.1f} ms (1 s mean)")

    @Slot(object)
    def _on_finished(self, report) -> None:
        self._report = report
        self._display_timer.stop()
        self.controls.set_running(False)
        self.status_label.setText(
            f"run complete — acquisition {report.acquisition_time_s if report.acquisition_time_s is not None else float('nan'):.2f} s, "
            f"lock {report.lock_retention_pct:.1f} %, "
            f"pointing error p95 {report.pointing_error_urad.get('p95', float('nan')):.0f} urad")
        if self._thread is not None:
            self._thread.wait(2000)

    # ---- controls --------------------------------------------------------
    @Slot(bool)
    def _on_pause(self, paused: bool) -> None:
        if self._worker is not None:
            self._worker.set_paused(paused)

    @Slot(bool)
    def _on_realtime(self, realtime: bool) -> None:
        if self._worker is not None:
            self._worker.set_realtime(realtime)

    @Slot(bool)
    def _on_truth(self, show: bool) -> None:
        self.frame_view.show_truth = show

    @Slot()
    def export_report(self) -> None:
        if self._report is None:
            QMessageBox.information(self, "no report",
                                    "Run a scenario to completion first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "save report",
                                              f"{self.cfg.name}.report.json",
                                              "JSON (*.json)")
        if path:
            self._report.to_json(path)
            Path(path).with_suffix(".txt").write_text(
                self._report.to_text() + "\n", encoding="utf-8")

    @Slot()
    def open_scenario(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "open scenario", "scenarios",
                                              "YAML (*.yaml *.yml)")
        if not path:
            return
        self.stop_run()
        self.cfg = SimConfig.load(path)
        self.scenario_path = path
        self.setWindowTitle(f"FSOC-PAT coarse alignment — {self.cfg.name}")
        # Rebuild the panel so its widgets bind to the newly loaded config.
        old = self.controls
        self.controls = ControlPanel(self.cfg)
        splitter = self.centralWidget()
        splitter.replaceWidget(2, self.controls)
        old.deleteLater()
        self.controls.run_requested.connect(self.start_run)
        self.controls.stop_requested.connect(self.stop_run)
        self.controls.pause_toggled.connect(self._on_pause)
        self.controls.realtime_toggled.connect(self._on_realtime)
        self.controls.truth_toggled.connect(self._on_truth)
        self.controls.export_requested.connect(self.export_report)
        self.controls.scenario_open_requested.connect(self.open_scenario)
        self.controls.scenario_save_requested.connect(self.save_scenario)
        self.plots.clear()
        self.status_label.setText(f"loaded {path}")

    @Slot()
    def save_scenario(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "save scenario",
                                              f"scenarios/{self.cfg.name}.yaml",
                                              "YAML (*.yaml *.yml)")
        if path:
            self.cfg.save(path)
            self.status_label.setText(f"saved {path}")

    def closeEvent(self, event) -> None:
        self.stop_run()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        event.accept()


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    scenario = argv[0] if argv else DEFAULT_SCENARIO
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(scenario)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
