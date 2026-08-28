"""
Live performance plots.

Three stacked strips on a shared time axis, because together they answer the
three questions an observer actually has:

  * "How well is it tracking?" — pointing error on a log scale, drawn as a
    filled area so the eye reads a band of performance rather than a wiggling
    line, with the field-of-view half-width as the labelled failure line.
    Log, because the interesting behaviour spans 30 µrad of quiet lock to
    3 degrees of search.
  * "What is it doing?" — the lock state as solid coloured spans. Spans, not
    ticks: state is an interval, and the width of an orange COAST span *is*
    the length of a beacon blink, visible without reading a single number.
  * "How hard is the target manoeuvring?" — the IMM's own agile-model
    probability, filled amber, with detection SNR behind it.

Rendering uses fixed-length ring buffers and one setData per curve per
refresh, so cost per frame is constant no matter how long the run.
"""
from __future__ import annotations

from collections import deque

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget

from . import theme

pg.setConfigOptions(
    antialias=True,
    background=(theme.PANEL.red(), theme.PANEL.green(), theme.PANEL.blue()),
    foreground=(theme.INK_MUTED.red(), theme.INK_MUTED.green(), theme.INK_MUTED.blue()),
)

WINDOW_S = 60.0          # visible history


def _style(plot: pg.PlotWidget, title: str) -> None:
    """Uppercase eyebrow title, hairline axes, quiet grid."""
    plot.setTitle(f'<span style="color:{theme.INK_MUTED.name()}; font-size:9pt; '
                  f'letter-spacing:2px;">{title.upper()}</span>')
    plot.showGrid(x=True, y=True, alpha=0.12)
    for side in ("left", "bottom"):
        axis = plot.getAxis(side)
        axis.setPen(pg.mkPen(theme.EDGE))
        axis.setTextPen(pg.mkPen(theme.INK_MUTED))
    plot.getPlotItem().getViewBox().setDefaultPadding(0.02)


class PlotStrip(QWidget):
    def __init__(self, fov_deg: float, parent=None):
        super().__init__(parent)
        self._t = deque(maxlen=4000)
        self._err = deque(maxlen=4000)
        self._agile = deque(maxlen=4000)
        self._snr = deque(maxlen=4000)
        self._state = deque(maxlen=4000)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        accent = (theme.ACCENT.red(), theme.ACCENT.green(), theme.ACCENT.blue())

        self.error_plot = pg.PlotWidget()
        _style(self.error_plot, "pointing error")
        self.error_plot.setLogMode(y=True)
        self.error_plot.setLabel("left", "µrad")
        half_fov_urad = np.radians(fov_deg) / 2 * 1e6
        limit = pg.InfiniteLine(pos=np.log10(half_fov_urad), angle=0,
                                pen=pg.mkPen(theme.WARN, style=pg.QtCore.Qt.DashLine),
                                label="FOV edge",
                                labelOpts={"color": theme.WARN, "position": 0.92,
                                           "anchors": [(1, 1), (1, 1)]})
        self.error_plot.addItem(limit)
        # Filled to the 1 µrad baseline: the area under the curve is the
        # performance band the eye actually reads.
        self._err_curve = self.error_plot.plot(
            pen=pg.mkPen(accent, width=1.4),
            fillLevel=0.0, brush=pg.mkBrush(accent + (36,)))
        layout.addWidget(self.error_plot, stretch=3)

        self.mode_plot = pg.PlotWidget()
        _style(self.mode_plot, "manoeuvre probability · SNR")
        self.mode_plot.setYRange(0, 1.05)
        snr_colour = (theme.INK_FAINT.red(), theme.INK_FAINT.green(), theme.INK_FAINT.blue())
        self._snr_curve = self.mode_plot.plot(pen=pg.mkPen(snr_colour, width=1))
        amber = theme.STATE["ACQUIRE"]
        amber_rgb = (amber.red(), amber.green(), amber.blue())
        self._agile_curve = self.mode_plot.plot(
            pen=pg.mkPen(amber_rgb, width=1.4),
            fillLevel=0.0, brush=pg.mkBrush(amber_rgb + (36,)))
        layout.addWidget(self.mode_plot, stretch=2)

        self.state_plot = pg.PlotWidget()
        _style(self.state_plot, "lock state")
        self.state_plot.setYRange(0, 1)
        self.state_plot.hideAxis("left")
        self.state_plot.setMaximumHeight(74)
        self._state_bars = pg.BarGraphItem(x0=[], x1=[], y0=0.18, y1=0.82,
                                           brushes=[], pen=None)
        self.state_plot.addItem(self._state_bars)
        layout.addWidget(self.state_plot, stretch=1)

        for p in (self.mode_plot, self.state_plot):
            p.setXLink(self.error_plot)

    def append(self, telemetry) -> None:
        self._t.append(telemetry.time_s)
        err = telemetry.pointing_error_rad
        self._err.append(err * 1e6 if err is not None and err > 0 else np.nan)
        self._agile.append(telemetry.mode_probabilities[1])
        self._snr.append((telemetry.detection_snr or 0.0) / 50.0)   # normalised
        self._state.append(telemetry.state.value)

    def redraw(self) -> None:
        if not self._t:
            return
        t = np.asarray(self._t)
        self._err_curve.setData(t, np.asarray(self._err), connect="finite")
        self._agile_curve.setData(t, np.asarray(self._agile))
        self._snr_curve.setData(t, np.clip(np.asarray(self._snr), 0, 1))

        # Coalesce the state sequence into spans; ~a handful of rectangles
        # instead of thousands of ticks.
        states = list(self._state)
        x0, x1, brushes = [], [], []
        start = 0
        for i in range(1, len(states) + 1):
            if i == len(states) or states[i] != states[start]:
                x0.append(t[start])
                x1.append(t[i - 1] if i == len(states) else t[i])
                brushes.append(pg.mkBrush(theme.state_colour(states[start])))
                start = i
        self._state_bars.setOpts(x0=x0, x1=x1, brushes=brushes)

        t_max = t[-1]
        self.error_plot.setXRange(max(0.0, t_max - WINDOW_S), max(WINDOW_S, t_max))

    def clear(self) -> None:
        for buf in (self._t, self._err, self._agile, self._snr, self._state):
            buf.clear()
        self._state_bars.setOpts(x0=[], x1=[], brushes=[])
        self._err_curve.setData([], [])
        self._agile_curve.setData([], [])
        self._snr_curve.setData([], [])
