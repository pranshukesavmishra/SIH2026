"""
The scenario control panel.

Deliberately not a reflection-generated tree of every config field: an
operator tunes perhaps a dozen things live, and burying them among fifty
freezes the demo. The dozen are grouped by what they physically are, edit the
underlying SimConfig directly, and everything else remains reachable through
the YAML scenario files, which the panel can load and save.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QPushButton, QVBoxLayout, QWidget)

from ..config import SimConfig


class ControlPanel(QWidget):
    run_requested = Signal()
    stop_requested = Signal()
    pause_toggled = Signal(bool)
    realtime_toggled = Signal(bool)
    truth_toggled = Signal(bool)
    export_requested = Signal()
    scenario_open_requested = Signal()
    scenario_save_requested = Signal()

    def __init__(self, cfg: SimConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        layout = QVBoxLayout(self)

        # ---- run control -------------------------------------------------
        scenario_box = QGroupBox("scenario")
        scenario_form = QVBoxLayout(scenario_box)
        self.open_button = QPushButton("open scenario…")
        self.save_button = QPushButton("save scenario as…")
        scenario_form.addWidget(self.open_button)
        scenario_form.addWidget(self.save_button)
        layout.addWidget(scenario_box)
        self.open_button.clicked.connect(self.scenario_open_requested)
        self.save_button.clicked.connect(self.scenario_save_requested)

        run_box = QGroupBox("run")
        run_form = QVBoxLayout(run_box)
        self.run_button = QPushButton("start")
        self.pause_button = QPushButton("pause")
        self.pause_button.setCheckable(True)
        self.realtime_check = QCheckBox("real-time pacing")
        self.realtime_check.setChecked(True)
        self.truth_check = QCheckBox("show ground truth")
        self.export_button = QPushButton("export performance report")
        for w in (self.run_button, self.pause_button, self.realtime_check,
                  self.truth_check, self.export_button):
            run_form.addWidget(w)
        layout.addWidget(run_box)

        self.run_button.clicked.connect(self._on_run_clicked)
        self.pause_button.toggled.connect(self.pause_toggled)
        self.realtime_check.toggled.connect(self.realtime_toggled)
        self.truth_check.toggled.connect(self.truth_toggled)
        self.export_button.clicked.connect(self.export_requested)
        self._running = False

        # ---- disturbances ------------------------------------------------
        dist_box = QGroupBox("disturbances")
        dist_form = QFormLayout(dist_box)
        self.turb_check = QCheckBox()
        self.turb_check.setChecked(cfg.turbulence.enabled)
        self.turb_rms = self._spin(0, 2000, cfg.turbulence.tilt_rms_urad, " urad")
        self.turb_greenwood = self._spin(1, 200, cfg.turbulence.greenwood_hz, " Hz")
        self.vib_check = QCheckBox()
        self.vib_check.setChecked(cfg.vibration.enabled)
        self.drop_prob = self._spin(0, 0.5, cfg.noise.frame_drop_probability, "", step=0.01)
        dist_form.addRow("turbulence", self.turb_check)
        dist_form.addRow("tilt RMS", self.turb_rms)
        dist_form.addRow("Greenwood", self.turb_greenwood)
        dist_form.addRow("vibration", self.vib_check)
        dist_form.addRow("frame drop p", self.drop_prob)
        layout.addWidget(dist_box)

        # ---- beacon ------------------------------------------------------
        beacon_box = QGroupBox("beacon")
        beacon_form = QFormLayout(beacon_box)
        beacon = cfg.beacons[0]
        self.beacon_amp = self._spin(1e4, 1e8, beacon.amplitude_e_s, " e/s", decimals=0)
        self.beacon_blink = self._spin(0, 14, beacon.blink_hz, " Hz")
        beacon_form.addRow("amplitude", self.beacon_amp)
        beacon_form.addRow("blink", self.beacon_blink)
        layout.addWidget(beacon_box)

        layout.addStretch(1)

        for widget, apply in [
            (self.turb_check, lambda v: setattr(cfg.turbulence, "enabled", bool(v))),
            (self.vib_check, lambda v: setattr(cfg.vibration, "enabled", bool(v))),
        ]:
            widget.toggled.connect(apply)
        self.turb_rms.valueChanged.connect(lambda v: setattr(cfg.turbulence, "tilt_rms_urad", v))
        self.turb_greenwood.valueChanged.connect(lambda v: setattr(cfg.turbulence, "greenwood_hz", v))
        self.drop_prob.valueChanged.connect(lambda v: setattr(cfg.noise, "frame_drop_probability", v))
        self.beacon_amp.valueChanged.connect(lambda v: setattr(cfg.beacons[0], "amplitude_e_s", v))
        self.beacon_blink.valueChanged.connect(lambda v: setattr(cfg.beacons[0], "blink_hz", v))

    def _spin(self, lo, hi, value, suffix, step=None, decimals=2) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(lo, hi)
        box.setValue(value)
        box.setSuffix(suffix)
        box.setDecimals(decimals)
        if step:
            box.setSingleStep(step)
        return box

    def _on_run_clicked(self) -> None:
        if self._running:
            self.stop_requested.emit()
        else:
            self.run_requested.emit()

    def set_running(self, running: bool) -> None:
        self._running = running
        self.run_button.setText("stop" if running else "start")
        self.pause_button.setChecked(False)
