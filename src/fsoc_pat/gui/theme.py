"""
The visual identity of the console, in one place.

One palette, one type ramp, one stylesheet. Every widget and every painted
overlay draws from here, so the camera view, the plots, the control panel and
the exported video frames read as a single instrument rather than a stack of
library defaults.

The look is a dark mission console: a deep blue-carbon ground so the star
field and the plots carry the light, one cyan data accent, and the five lock
states as the only other saturated colours on screen. State colour is meaning,
not decoration — the same five hues everywhere, from the reticle to the state
strip to the video export.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

# ---- palette -------------------------------------------------------------
GROUND      = QColor(10, 14, 20)      # window ground
PANEL       = QColor(16, 22, 30)      # plot / view panels
RAISED      = QColor(23, 31, 41)      # controls, chips
EDGE        = QColor(40, 52, 66)      # hairlines
INK         = QColor(226, 234, 242)   # primary text
INK_MUTED   = QColor(138, 152, 166)   # secondary text
INK_FAINT   = QColor(84, 98, 112)     # tertiary / disabled
ACCENT      = QColor(83, 200, 232)    # the one data accent (signal cyan)
ACCENT_DIM  = QColor(83, 200, 232, 60)
WARN        = QColor(255, 107, 94)

STATE = {
    "SEARCH":    QColor(90, 159, 255),
    "ACQUIRE":   QColor(255, 194, 77),
    "TRACK":     QColor(63, 214, 143),
    "COAST":     QColor(255, 157, 77),
    "REACQUIRE": QColor(255, 107, 94),
}

def state_colour(name: str) -> QColor:
    return STATE.get(name, INK_MUTED)


def mono_font(point_size: int = 10, bold: bool = False) -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setPointSize(point_size)
    font.setBold(bold)
    return font


def _hex(c: QColor) -> str:
    return c.name()


# ---- application stylesheet ----------------------------------------------
def stylesheet() -> str:
    return f"""
QMainWindow, QWidget {{
    background: {_hex(GROUND)};
    color: {_hex(INK)};
    font-size: 12px;
}}
QSplitter::handle {{ background: {_hex(GROUND)}; width: 6px; }}

QGroupBox {{
    background: {_hex(PANEL)};
    border: 1px solid {_hex(EDGE)};
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: {_hex(INK_MUTED)};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    font-size: 10px;
}}

QPushButton {{
    background: {_hex(RAISED)};
    border: 1px solid {_hex(EDGE)};
    border-radius: 5px;
    padding: 7px 12px;
    color: {_hex(INK)};
}}
QPushButton:hover {{ border-color: {_hex(ACCENT)}; }}
QPushButton:pressed {{ background: {_hex(PANEL)}; }}
QPushButton:checked {{
    background: {_hex(ACCENT)};
    color: {_hex(GROUND)};
    border-color: {_hex(ACCENT)};
    font-weight: 600;
}}
QPushButton#primary {{
    background: {_hex(ACCENT)};
    color: {_hex(GROUND)};
    border: none;
    font-weight: 700;
}}
QPushButton#primary:hover {{ background: #6fd4ef; }}

QCheckBox {{ spacing: 8px; color: {_hex(INK)}; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {_hex(EDGE)};
    border-radius: 3px;
    background: {_hex(RAISED)};
}}
QCheckBox::indicator:checked {{
    background: {_hex(ACCENT)};
    border-color: {_hex(ACCENT)};
}}

QDoubleSpinBox, QSpinBox, QComboBox {{
    background: {_hex(RAISED)};
    border: 1px solid {_hex(EDGE)};
    border-radius: 4px;
    padding: 3px 6px;
    color: {_hex(INK)};
    selection-background-color: {_hex(ACCENT)};
}}
QDoubleSpinBox:focus, QSpinBox:focus {{ border-color: {_hex(ACCENT)}; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    width: 14px; background: {_hex(RAISED)}; border: none;
}}

QStatusBar {{
    background: {_hex(PANEL)};
    border-top: 1px solid {_hex(EDGE)};
    color: {_hex(INK_MUTED)};
    font-family: monospace;
}}
QLabel#formLabel {{ color: {_hex(INK_MUTED)}; }}
QToolTip {{
    background: {_hex(RAISED)}; color: {_hex(INK)};
    border: 1px solid {_hex(EDGE)};
}}
QScrollBar:vertical {{
    background: {_hex(GROUND)}; width: 10px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {_hex(EDGE)}; border-radius: 5px; min-height: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""
