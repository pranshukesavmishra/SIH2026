"""
The live camera view: the detector's world, annotated with the tracker's
opinion of it.

Overlays are drawn in widget space from the frame's data, not baked into the
image, so they stay one-pixel crisp at any zoom:

  * boresight cross — where the mount is pointing;
  * detection diamonds — every CFAR exceedance this frame;
  * the locked track — a circle whose colour is the lock state, with a
    velocity vector showing where the filter believes the target is going;
  * a state banner and, during SEARCH, the spiral's progress.

Ground-truth markers can be toggled on for development and OFF for honest
demonstrations; the distinction is the point of having the toggle.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QFont, QPixmap
from PySide6.QtWidgets import QWidget

from .. import geometry as geo

STATE_COLOURS = {
    "SEARCH": QColor(80, 160, 255),
    "ACQUIRE": QColor(255, 200, 60),
    "TRACK": QColor(70, 220, 120),
    "COAST": QColor(255, 140, 50),
    "REACQUIRE": QColor(255, 90, 90),
}


class FrameView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 360)
        self._image: Optional[QImage] = None
        self._frame = None
        self._telemetry = None
        self._tracker = None
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
        self.update()

    # ---- painting --------------------------------------------------------
    def _to_widget(self, u: float, v: float, rect: QRectF, w: int, h: int) -> QPointF:
        return QPointF(rect.x() + u / w * rect.width(),
                       rect.y() + v / h * rect.height())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(12, 14, 18))
        if self._image is None:
            painter.setPen(QColor(120, 130, 140))
            painter.drawText(self.rect(), Qt.AlignCenter, "no simulation running")
            painter.end()
            return

        # Letterbox the image into the widget, preserving aspect.
        iw, ih = self._image.width(), self._image.height()
        scale = min(self.width() / iw, self.height() / ih)
        dw, dh = iw * scale, ih * scale
        rect = QRectF((self.width() - dw) / 2, (self.height() - dh) / 2, dw, dh)
        painter.drawImage(rect, self._image)

        frame, tel = self._frame, self._telemetry
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Boresight cross.
        centre = self._to_widget(iw / 2, ih / 2, rect, iw, ih)
        pen = QPen(QColor(200, 200, 210, 180), 1)
        painter.setPen(pen)
        painter.drawLine(centre + QPointF(-14, 0), centre + QPointF(-4, 0))
        painter.drawLine(centre + QPointF(4, 0), centre + QPointF(14, 0))
        painter.drawLine(centre + QPointF(0, -14), centre + QPointF(0, -4))
        painter.drawLine(centre + QPointF(0, 4), centre + QPointF(0, 14))

        # Ground truth (development only): green = beacon, red = decoy.
        if self.show_truth:
            for target in frame.targets:
                if not target.in_frame:
                    continue
                p = self._to_widget(target.u, target.v, rect, iw, ih)
                colour = QColor(235, 80, 80) if target.is_decoy else QColor(80, 235, 120)
                painter.setPen(QPen(colour, 1, Qt.DashLine))
                painter.drawEllipse(p, 13, 13)

        # The locked track, drawn from the tracker's estimate.
        tracker = self._tracker
        if tracker is not None and tel is not None and tel.track_id is not None:
            track = next((t for t in tracker.tracker.tracks
                          if t.track_id == tel.track_id), None)
            if track is not None:
                az, el = track.angles
                cam_az, cam_el = frame.pointing_reported
                u, v, visible = geo.project(az, el, cam_az, cam_el,
                                            tracker.focal_px, iw, ih)
                if visible:
                    p = self._to_widget(u, v, rect, iw, ih)
                    colour = STATE_COLOURS.get(tel.state.value, QColor(200, 200, 200))
                    painter.setPen(QPen(colour, 2))
                    painter.drawEllipse(p, 10, 10)
                    # Velocity vector: half a second of predicted motion.
                    ra, re = track.imm.rates
                    u2, v2, vis2 = geo.project(az + ra * 0.5, el + re * 0.5,
                                               cam_az, cam_el, tracker.focal_px, iw, ih)
                    if vis2:
                        painter.drawLine(p, self._to_widget(u2, v2, rect, iw, ih))

        # Detections.
        if self.show_detections and tel is not None and tracker is not None:
            painter.setPen(QPen(QColor(150, 170, 255, 160), 1))
            for track in tracker.tracker.tracks:
                if track.last_detection is None or track.misses:
                    continue
                d = track.last_detection
                p = self._to_widget(d.u, d.v, rect, iw, ih)
                painter.drawLine(p + QPointF(0, -6), p + QPointF(6, 0))
                painter.drawLine(p + QPointF(6, 0), p + QPointF(0, 6))
                painter.drawLine(p + QPointF(0, 6), p + QPointF(-6, 0))
                painter.drawLine(p + QPointF(-6, 0), p + QPointF(0, -6))

        # State banner.
        if tel is not None:
            colour = STATE_COLOURS.get(tel.state.value, QColor(200, 200, 200))
            painter.setFont(QFont("Consolas", 11, QFont.Bold))
            painter.setPen(colour)
            err = ("--" if tel.pointing_error_rad is None
                   else f"{tel.pointing_error_rad * 1e6:7.0f} urad")
            painter.drawText(int(rect.x()) + 10, int(rect.y()) + 22,
                             f"{tel.state.value}   t={tel.time_s:6.1f}s   err {err}   "
                             f"det {tel.n_detections}")
            if frame.dropped:
                painter.setPen(QColor(255, 90, 90))
                painter.drawText(int(rect.x()) + 10, int(rect.y()) + 42, "FRAME DROPPED")
        painter.end()
