"""Monochrome, Tesla-inspired visual theme."""
from PySide6.QtGui import QColor, QFont, QFontDatabase

BG = "#000000"
SURFACE = "#0b0b0b"
SURFACE_2 = "#141414"
BORDER = "#222222"
BORDER_HI = "#3a3a3a"
TEXT = "#ffffff"
MUTED = "#8a8a8a"
DIM = "#555555"
OK = "#ffffff"
DANGER = "#ff453a"

FONT_FAMILY = "Segoe UI Variable Display"


def font_family() -> str:
    families = set(QFontDatabase.families())
    for name in ("Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", "Arial"):
        if name in families:
            return name
    return QFont().defaultFamily()


def qcolor(hex_value: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_value)
    c.setAlphaF(alpha)
    return c


def mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        a.alphaF() + (b.alphaF() - a.alphaF()) * t,
    )


def stylesheet(family: str) -> str:
    return f"""
* {{ font-family: "{family}"; color: {TEXT}; outline: none; }}
QMainWindow, QDialog, QWidget#Root {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel[role="h1"] {{ font-size: 34px; font-weight: 300; letter-spacing: 1px; }}
QLabel[role="h2"] {{ font-size: 20px; font-weight: 400; }}
QLabel[role="caption"] {{ color: {MUTED}; font-size: 11px; letter-spacing: 2px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {MUTED}; font-size: 13px; }}
QLabel[role="value"] {{ font-size: 15px; }}
QLabel[role="big"] {{ font-size: 44px; font-weight: 200; }}

QFrame#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 22px; }}
QFrame#Divider {{ background: {BORDER}; max-height: 1px; min-height: 1px; border: none; }}

QLineEdit, QComboBox, QSpinBox {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 12px;
    padding: 10px 14px; font-size: 13px; selection-background-color: #ffffff; selection-color: #000;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {TEXT}; }}
QLineEdit:disabled {{ color: {DIM}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER_HI}; selection-background-color: #ffffff;
    selection-color: #000; padding: 4px;
}}
QCheckBox {{ font-size: 13px; spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {BORDER_HI}; background: {SURFACE_2}; }}
QCheckBox::indicator:checked {{ background: #ffffff; border: 1px solid #ffffff; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {BORDER_HI}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{ background: #ffffff; color: #000; border: none; padding: 6px 10px; border-radius: 6px; }}
"""
