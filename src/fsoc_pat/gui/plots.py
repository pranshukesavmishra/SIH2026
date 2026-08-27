"""
Live performance plots.

Three stacked strips, sharing a time axis, chosen because together they answer
the three questions an observer actually has:

  * "How well is it tracking?" — pointing error on a log scale, with the
    field-of-view half-width drawn as the failure line. Log, because the
    interesting behaviour spans 30 urad of quiet lock to 3 degrees of search.
  * "What is it doing?" — the lock state as a coloured band.
  * "How hard is the target manoeuvring?" — the IMM's agile-model probability,
    which is the filter's own running answer, and detection SNR beside it.

Rendering uses pyqtgraph with fixed-length ring buffers, so cost per frame is
constant no matter how long the run.
"""
from __future__ import annotations

from collections import deque

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .frameview import STATE_COLOURS

pg.setConfigOptions(antialias=False, background=(16, 18, 24), foreground=(180, 186, 195))

WINDOW_S = 60.0          # visible history


class PlotStrip(QWidget):
    def __init__(self, fov_deg: float, parent=None):
        super().__init__(parent)
        self._t = deque(maxlen=4000)
        self._err = deque(maxlen=4000)
        self._agile = deque(maxlen=4000)
        self._snr = deque(maxlen=4000)
        self._state_colour = deque(maxlen=4000)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.error_plot = pg.PlotWidget(title="pointing error")
        self.error_plot.setLogMode(y=True)
        self.error_plot.setLabel("left", "urad")
        self.error_plot.showGrid(x=True, y=True, alpha=0.15)
        half_fov_urad = np.radians(fov_deg) / 2 * 1e6
        self.error_plot.addLine(y=np.log10(half_fov_urad),
                                pen=pg.mkPen((235, 90, 90), style=pg.QtCore.Qt.DashLine))
        self._err_curve = self.error_plot.plot(pen=pg.mkPen((120, 200, 255), width=1))
        layout.addWidget(self.error_plot, stretch=3)

        self.mode_plot = pg.PlotWidget(title="manoeuvre probability / SNR")
        self.mode_plot.setYRange(0, 1.05)
        self.mode_plot.showGrid(x=True, y=True, alpha=0.15)
        self._agile_curve = self.mode_plot.plot(pen=pg.mkPen((255, 200, 60), width=1),
                                                name="agile mode")
        self._snr_curve = self.mode_plot.plot(pen=pg.mkPen((120, 220, 140), width=1))
        layout.addWidget(self.mode_plot, stretch=2)

        # State band: drawn as a scatter of thin vertical ticks, cheap and clear.
        self.state_plot = pg.PlotWidget(title="lock state")
        self.state_plot.setYRange(0, 1)
        self.state_plot.hideAxis("left")
        self._state_scatter = pg.ScatterPlotItem(symbol="s", size=4, pxMode=True)
        self.state_plot.addItem(self._state_scatter)
        layout.addWidget(self.state_plot, stretch=1)

        for p in (self.mode_plot, self.state_plot):
            p.setXLink(self.error_plot)

    def append(self, telemetry) -> None:
        self._t.append(telemetry.time_s)
        err = telemetry.pointing_error_rad
        self._err.append(err * 1e6 if err is not None and err > 0 else np.nan)
        self._agile.append(telemetry.mode_probabilities[1])
        self._snr.append((telemetry.detection_snr or 0.0) / 50.0)   # normalised
        colour = STATE_COLOURS.get(telemetry.state.value)
        self._state_colour.append(pg.mkBrush(colour) if colour else pg.mkBrush(120, 120, 120))

    def redraw(self) -> None:
        if not self._t:
            return
        t = np.asarray(self._t)
        self._err_curve.setData(t, np.asarray(self._err), connect="finite")
        self._agile_curve.setData(t, np.asarray(self._agile))
        self._snr_curve.setData(t, np.clip(np.asarray(self._snr), 0, 1))
        self._state_scatter.setData(x=t, y=np.full(len(t), 0.5),
                                    brush=list(self._state_colour), pen=None)
        t_max = t[-1]
        self.error_plot.setXRange(max(0.0, t_max - WINDOW_S), max(WINDOW_S, t_max))

    def clear(self) -> None:
        for buf in (self._t, self._err, self._agile, self._snr, self._state_colour):
            buf.clear()
        self.redraw()
