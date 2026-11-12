"""Small building blocks shared by the settings pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QWidget

PAGE_MARGINS = (28, 24, 28, 24)


def title(text: str) -> QLabel:
    label = QLabel(text)
    font = QFont(label.font())
    font.setPointSizeF(font.pointSizeF() * 1.9)
    font.setWeight(QFont.Weight.DemiBold)
    label.setFont(font)
    label.setAccessibleName(text)
    return label


def hint(text: str, wrap: bool = True) -> QLabel:
    """A line of explanation. Use ``wrap=False`` for short notes beside a control,
    which would otherwise wrap after a word or two."""
    label = QLabel(text)
    label.setWordWrap(wrap)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def row(*widgets: QWidget, stretch: bool = True) -> QWidget:
    """Widgets side by side, left-aligned."""
    holder = QWidget()
    line = QHBoxLayout(holder)
    line.setContentsMargins(0, 0, 0, 0)
    line.setSpacing(12)
    for widget in widgets:
        line.addWidget(widget)
    if stretch:
        line.addStretch(1)
    return holder


def check_only(group: QButtonGroup, button: object | None) -> None:
    """Check ``button`` in an exclusive group, or clear the group when it's None."""
    group.setExclusive(False)
    for each in group.buttons():
        each.setChecked(each is button)
    group.setExclusive(True)
