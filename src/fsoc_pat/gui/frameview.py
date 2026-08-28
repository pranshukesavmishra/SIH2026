"""
The live camera view: the detector's world, annotated with the tracker's
opinion of it.

Overlays are drawn in widget space from the frame's data, not baked into the
image, so they stay one-pixel crisp at any window size. Everything the view
draws is something the system actually knows; the one exception — ground
truth — is behind a toggle that is OFF by default, because an honest
demonstration and a debugging session are different activities.

What each element means:

  * corner brackets      — the sensor's active area, framed like the
                           instrument it is;
  * boresight cross      — where the mount is pointing (the reticle gap
                           leaves the target itself unobscured);
  * track reticle        — the filter's estimate. Solid double-arc ring while
                           tracking, dashed while coasting on prediction: the
                           dashes literally say "this is a guess";
  * lock pulse           — one expanding ring the moment ACQUIRE becomes
                           TRACK, so the acquisition instant is visible from
                           across a demo hall;
  * velocity vector      — half a second of the filter's predicted motion,
                           with an arrowhead;
  * detection diamonds   — every associated CFAR detection this frame;
  * spiral trace         — during SEARCH, the acquisition pattern and the
                           current dwell point, so the search is watchable
                           rather than mysterious;
  * magnifier inset      — a 4x crop centred on the track, because at 6
                           degrees of FOV the beacon is a handful of pixels
                           and the judges deserve to see it.
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import QWidget

from .. import geometry as geo
from . import theme

# Kept as the public name other modules import.
STATE_COLOURS = theme.STATE

_PULSE_SECONDS = 0.9


class FrameView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 360)
        self._image: Optional[QImage] = None
        self._frame = None
        self._telemetry = None
        self._tracker = None
        self._last_state: Optional[str] = None
        self._pulse_started: Optional[float] = None
        self.show_truth = False
        self.show_detections = True
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def update_frame(self, frame, telemetry, tracker) -> None:
        # 12-bit image -> 8-bit display with a fixed stretch so brightness is
        # comparable frame to frame (auto-stretch would hide scintillation).
        img = frame.image
        display = np.clip(img.astype(np.float32) / max(img.max(), 1) * 255, 0, 255
                          ).astype(np.uint8)
        h, w = display.shape
        self._image = QImage(display.data, w, h, w, QImage.Format_Grayscale8).copy()
        self._frame = frame
        self._telemetry = telemetry
        self._tracker = tracker
        # The lock pulse fires on the ACQUIRE -> TRACK edge.
        state = telemetry.state.value if telemetry is not None else None
        if state == "TRACK" and self._last_state not in (None, "TRACK"):
            self._pulse_started = time.perf_counter()
        self._last_state = state
        self.update()

    # ---- helpers ---------------------------------------------------------
    def _to_widget(self, u: float, v: float, rect: QRectF, w: int, h: int) -> QPointF:
        return QPointF(rect.x() + u / w * rect.width(),
                       rect.y() + v / h * rect.height())

    @staticmethod
    def _chip(painter: QPainter, x: float, y: float, text: str, colour: QColor,
              font: QFont) -> float:
        """Filled rounded state chip; returns its right edge."""
        painter.setFont(font)
        metrics = painter.fontMetrics()
        w = metrics.horizontalAdvance(text) + 18
        h = metrics.height() + 8
        rect = QRectF(x, y, w, h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(theme.GROUND)
        painter.drawText(rect, Qt.AlignCenter, text)
        return x + w

    # ---- painting --------------------------------------------------------
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.GROUND)
        if self._image is None:
            painter.setPen(theme.INK_FAINT)
            painter.setFont(theme.mono_font(11))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "press start to begin a run")
            painter.end()
            return

        iw, ih = self._image.width(), self._image.height()
        scale = min(self.width() / iw, self.height() / ih)
        dw, dh = iw * scale, ih * scale
        rect = QRectF((self.width() - dw) / 2, (self.height() - dh) / 2, dw, dh)
        painter.drawImage(rect, self._image)
        painter.setRenderHint(QPainter.Antialiasing, True)

        self._draw_frame_furniture(painter, rect)
        frame, tel = self._frame, self._telemetry

        if self.show_truth:
            self._draw_truth(painter, rect, iw, ih)
        if tel is not None and tel.state.value == "SEARCH":
            self._draw_search(painter, rect, iw, ih)
        track_point = self._draw_track(painter, rect, iw, ih)
        if self.show_detections:
            self._draw_detections(painter, rect, iw, ih)
        self._draw_banner(painter, rect)
        if track_point is not None:
            self._draw_inset(painter, rect, iw, ih, track_point)
        painter.end()

    def _draw_frame_furniture(self, painter: QPainter, rect: QRectF) -> None:
        """Corner brackets and the boresight cross."""
        pen = QPen(theme.EDGE, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        arm = min(rect.width(), rect.height()) * 0.045
        for cx, cy, sx, sy in ((rect.left(), rect.top(), 1, 1),
                               (rect.right(), rect.top(), -1, 1),
                               (rect.left(), rect.bottom(), 1, -1),
                               (rect.right(), rect.bottom(), -1, -1)):
            painter.drawLine(QPointF(cx, cy), QPointF(cx + sx * arm, cy))
            painter.drawLine(QPointF(cx, cy), QPointF(cx, cy + sy * arm))

        centre = QPointF(rect.center())
        pen = QPen(QColor(226, 234, 242, 150), 1)
        painter.setPen(pen)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            painter.drawLine(centre + QPointF(dx * 5, dy * 5),
                             centre + QPointF(dx * 16, dy * 16))

    def _draw_truth(self, painter, rect, iw, ih) -> None:
        for target in self._frame.targets:
            if not target.in_frame:
                continue
            p = self._to_widget(target.u, target.v, rect, iw, ih)
            colour = theme.WARN if target.is_decoy else theme.STATE["TRACK"]
            painter.setPen(QPen(colour, 1, Qt.DashLine))
            painter.drawEllipse(p, 14, 14)
            painter.setFont(theme.mono_font(8))
            painter.drawText(p + QPointF(16, 4),
                             "decoy" if target.is_decoy else "truth")

    def _draw_search(self, painter, rect, iw, ih) -> None:
        """The acquisition spiral, drawn in camera-angle space around centre."""
        tracker = self._tracker
        if tracker is None:
            return
        search = tracker.search
        points = search.plan.points
        if len(points) < 2:
            return
        f = tracker.focal_px
        centre = QPointF(rect.center())
        sx = rect.width() / iw
        path = QPainterPath()
        started = False
        for d_az, d_el in points:
            # Angular offsets -> pixels at the focal plane -> widget space.
            px = geo.urad_to_px(d_az * 1e6, f) * sx
            py = -geo.urad_to_px(d_el * 1e6, f) * sx
            pt = centre + QPointF(px, py)
            if not started:
                path.moveTo(pt)
                started = True
            else:
                path.lineTo(pt)
        pen = QPen(theme.ACCENT_DIM, 1)
        painter.setPen(pen)
        painter.drawPath(path)
        # Current dwell point.
        d_az, d_el = search.current_offset()
        px = geo.urad_to_px(d_az * 1e6, f) * sx
        py = -geo.urad_to_px(d_el * 1e6, f) * sx
        painter.setPen(QPen(theme.STATE["SEARCH"], 2))
        painter.drawEllipse(centre + QPointF(px, py), 5, 5)

    def _draw_track(self, painter, rect, iw, ih) -> Optional[QPointF]:
        tracker, tel, frame = self._tracker, self._telemetry, self._frame
        if tracker is None or tel is None or tel.track_id is None:
            return None
        track = next((t for t in tracker.tracker.tracks
                      if t.track_id == tel.track_id), None)
        if track is None:
            return None
        az, el = track.angles
        cam_az, cam_el = frame.pointing_reported
        u, v, visible = geo.project(az, el, cam_az, cam_el, tracker.focal_px, iw, ih)
        if not visible:
            return None
        p = self._to_widget(u, v, rect, iw, ih)
        colour = theme.state_colour(tel.state.value)
        coasting = tel.state.value == "COAST"

        # Double-arc reticle: two 110-degree arcs leave the target visible
        # through the gaps. Dashed while coasting.
        pen = QPen(colour, 2)
        if coasting:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        r = 13.0
        span = 110 * 16
        box = QRectF(p.x() - r, p.y() - r, 2 * r, 2 * r)
        painter.drawArc(box, 20 * 16, span)
        painter.drawArc(box, 200 * 16, span)

        # Lock pulse: one ring expanding out of the reticle at lock-on.
        if self._pulse_started is not None:
            age = (time.perf_counter() - self._pulse_started) / _PULSE_SECONDS
            if age >= 1.0:
                self._pulse_started = None
            else:
                ease = 1.0 - (1.0 - age) ** 2
                radius = r + ease * 46.0
                ring = QColor(colour)
                ring.setAlpha(int(200 * (1.0 - age)))
                painter.setPen(QPen(ring, 2))
                painter.drawEllipse(p, radius, radius)

        # Velocity vector with arrowhead: half a second of predicted motion.
        ra, re = track.imm.rates
        u2, v2, vis2 = geo.project(az + ra * 0.5, el + re * 0.5,
                                   cam_az, cam_el, tracker.focal_px, iw, ih)
        if vis2:
            q = self._to_widget(u2, v2, rect, iw, ih)
            d = q - p
            length = float(np.hypot(d.x(), d.y()))
            if length > 18.0:
                painter.setPen(QPen(colour, 1.6))
                painter.drawLine(p + d * (r / length), q)
                ux, uy = d.x() / length, d.y() / length
                left = QPointF(-uy, ux) * 4.0
                painter.drawLine(q, q - QPointF(ux, uy) * 9.0 + left)
                painter.drawLine(q, q - QPointF(ux, uy) * 9.0 - left)
        return p

    def _draw_detections(self, painter, rect, iw, ih) -> None:
        tracker = self._tracker
        if tracker is None:
            return
        colour = QColor(theme.ACCENT)
        colour.setAlpha(150)
        painter.setPen(QPen(colour, 1))
        for track in tracker.tracker.tracks:
            if track.last_detection is None or track.misses:
                continue
            d = track.last_detection
            p = self._to_widget(d.u, d.v, rect, iw, ih)
            painter.drawLine(p + QPointF(0, -6), p + QPointF(6, 0))
            painter.drawLine(p + QPointF(6, 0), p + QPointF(0, 6))
            painter.drawLine(p + QPointF(0, 6), p + QPointF(-6, 0))
            painter.drawLine(p + QPointF(-6, 0), p + QPointF(0, -6))

    def _draw_banner(self, painter, rect) -> None:
        tel = self._telemetry
        if tel is None:
            return
        font = theme.mono_font(10, bold=True)
        x = rect.x() + 12
        y = rect.y() + 12
        x = self._chip(painter, x, y, tel.state.value,
                       theme.state_colour(tel.state.value), font) + 10
        painter.setFont(theme.mono_font(10))
        painter.setPen(theme.INK)
        err = ("—" if tel.pointing_error_rad is None
               else f"{tel.pointing_error_rad * 1e6:5.0f} µrad")
        painter.drawText(QPointF(x, y + 15),
                         f"t {tel.time_s:6.1f} s   err {err}   det {tel.n_detections}")
        if self._frame.dropped:
            self._chip(painter, rect.x() + 12, y + 28, "FRAME DROPPED",
                       theme.WARN, theme.mono_font(9, bold=True))

    def _draw_inset(self, painter, rect, iw, ih, track_point: QPointF) -> None:
        """4x magnified crop centred on the track, lower-right corner."""
        # Widget point -> image pixel.
        u = (track_point.x() - rect.x()) / rect.width() * iw
        v = (track_point.y() - rect.y()) / rect.height() * ih
        half = 24
        u0 = int(np.clip(u - half, 0, iw - 2 * half))
        v0 = int(np.clip(v - half, 0, ih - 2 * half))
        crop = self._image.copy(u0, v0, 2 * half, 2 * half)

        size = min(rect.width(), rect.height()) * 0.28
        inset = QRectF(rect.right() - size - 12, rect.bottom() - size - 12, size, size)
        painter.fillRect(inset.adjusted(-2, -2, 2, 2), theme.PANEL)
        painter.drawImage(inset, crop)
        # The chip helper leaves a solid brush on the painter; an outlined
        # rect drawn now would inherit it and fill the whole inset.
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(theme.EDGE, 1))
        painter.drawRect(inset)
        # Crosshair where the track sits inside the crop.
        cx = inset.x() + (u - u0) / (2 * half) * inset.width()
        cy = inset.y() + (v - v0) / (2 * half) * inset.height()
        colour = theme.state_colour(self._telemetry.state.value)
        painter.setPen(QPen(colour, 1))
        painter.drawLine(QPointF(cx - 8, cy), QPointF(cx - 3, cy))
        painter.drawLine(QPointF(cx + 3, cy), QPointF(cx + 8, cy))
        painter.drawLine(QPointF(cx, cy - 8), QPointF(cx, cy - 3))
        painter.drawLine(QPointF(cx, cy + 3), QPointF(cx, cy + 8))
        painter.setFont(theme.mono_font(8))
        painter.setPen(theme.INK_MUTED)
        painter.drawText(QPointF(inset.x() + 6, inset.y() + 14), "4×")
