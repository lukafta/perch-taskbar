"""Panel styling for Windows light and dark mode, from the design's tokens."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from perch.models import Theme
from perch.palette import AMBER


def apply_color_scheme(theme: Theme) -> None:
    """Make the whole app light, dark, or follow Windows (Qt 6.8 and later)."""
    hints = QGuiApplication.styleHints()
    if not hasattr(hints, "setColorScheme"):
        return
    if theme is Theme.LIGHT:
        hints.setColorScheme(Qt.ColorScheme.Light)
    elif theme is Theme.DARK:
        hints.setColorScheme(Qt.ColorScheme.Dark)
    else:
        hints.unsetColorScheme()


@dataclass(frozen=True)
class Tokens:
    surface: str
    stroke: str
    text: str
    muted: str
    """Secondary text. Both themes' values pass 4.5:1 on their surface."""
    hover: str
    pressed: str
    focus: str
    """Keyboard focus ring: amber, darkened on light so it keeps 3:1 contrast."""


DARK = Tokens(
    surface="rgba(36, 36, 36, 245)",
    stroke="rgba(255, 255, 255, 20)",
    text="#F3F3F3",
    muted="#A3A3A3",
    hover="rgba(255, 255, 255, 15)",
    pressed="rgba(255, 255, 255, 9)",
    focus=AMBER,
)

LIGHT = Tokens(
    surface="rgba(249, 249, 249, 245)",
    stroke="rgba(0, 0, 0, 20)",
    text="#1A1A1A",
    muted="#5F5F5F",
    hover="rgba(0, 0, 0, 13)",
    pressed="rgba(0, 0, 0, 8)",
    focus="#B86A00",
)

FONT = '"Segoe UI Variable Text", "Segoe UI"'


def stylesheet(t: Tokens) -> str:
    # The top-level window is fully transparent; QFrame#panel paints the
    # rounded, tinted body.
    return f"""
QFrame#panel {{
    background-color: {t.surface};
    border: 1px solid {t.stroke};
    border-radius: 10px;
}}
QFrame#panel QLabel {{
    background: transparent;
    color: {t.text};
    font-family: {FONT};
    font-size: 10pt;
}}
QFrame#panel QLabel#header {{
    color: {t.muted};
    font-size: 9pt;
    font-weight: 600;
    padding: 4px 10px 2px 10px;
}}
QPushButton#row, QToolButton#tile {{
    color: {t.text};
    background-color: transparent;
    border: 1px solid transparent;
    outline: none;
    font-family: {FONT};
}}
QPushButton#row {{
    border-radius: 6px;
}}
QToolButton#tile {{
    border-radius: 10px;
    font-size: 9pt;
    padding: 6px 2px 4px 2px;
}}
QPushButton#row:hover, QToolButton#tile:hover {{
    background-color: {t.hover};
}}
QPushButton#row:pressed, QToolButton#tile:pressed {{
    background-color: {t.pressed};
}}
QPushButton#row:focus, QToolButton#tile:focus {{
    border-color: {t.focus};
}}
QToolButton#gear {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    outline: none;
}}
QToolButton#gear:hover {{
    background-color: {t.hover};
}}
QToolButton#gear:focus {{
    border-color: {t.focus};
}}
QFrame#panel QLabel#empty {{
    color: {t.muted};
    font-size: 9pt;
    padding: 6px 10px 10px 10px;
}}
"""
