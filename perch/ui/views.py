"""The panel styles: how a group's shortcuts are drawn inside the panel.

Each view emits ``activated(Shortcut)`` when a shortcut is clicked. A third
style, Command (filter box and number keys), is planned.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractButton,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from perch import layouts
from perch.models import Group, Shortcut, Style

ROW_ICON = 20
ROW_HEIGHT = 40
ROW_MIN_WIDTH = 220
TILE_ICON = 32
TILE_SIZE = QSize(76, 84)
TILE_SPACING = 4


class GroupView(QWidget):
    """Base for a style: owns the shortcut buttons and reports clicks."""

    activated = Signal(Shortcut)

    def __init__(self) -> None:
        super().__init__()
        self._buttons: list[QAbstractButton] = []

    def buttons(self) -> list[QAbstractButton]:
        """One button per shortcut, in the group's order."""
        return list(self._buttons)

    def arrange(self, max_columns: int | None) -> None:
        """Fit the view to the screen: at most ``max_columns`` tiles across."""

    def _add(self, button: QAbstractButton, shortcut: Shortcut) -> None:
        button.setAccessibleName(shortcut.name)
        button.clicked.connect(lambda _checked=False: self.activated.emit(shortcut))
        self._buttons.append(button)


class RowsView(GroupView):
    """Icon and name on each line, in one vertical list."""

    def __init__(self, group: Group, icons: Sequence[QIcon], device_pixel_ratio: float) -> None:
        super().__init__()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)
        for shortcut, icon in zip(group.shortcuts, icons):
            button = _RowButton(shortcut, icon, device_pixel_ratio)
            column.addWidget(button)
            self._add(button, shortcut)


class TilesView(GroupView):
    """Large icons with the name underneath, arranged by the group's layout."""

    def __init__(self, group: Group, icons: Sequence[QIcon]) -> None:
        super().__init__()
        self._layout = group.layout
        self._columns = group.columns
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(TILE_SPACING)
        for shortcut, icon in zip(group.shortcuts, icons):
            button = QToolButton()
            button.setObjectName("tile")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setIcon(icon)
            button.setIconSize(QSize(TILE_ICON, TILE_ICON))
            button.setFixedSize(TILE_SIZE)
            label = button.fontMetrics().elidedText(shortcut.name, Qt.TextElideMode.ElideRight, TILE_SIZE.width() - 10)
            button.setText(_literal_ampersands(label))
            button.setToolTip(f"{shortcut.name}\n{shortcut.target}")
            self._add(button, shortcut)
        self.arrange(None)

    def grid_shape(self) -> tuple[int, int]:
        """``(rows, columns)`` as currently arranged."""
        # Tracked here: QGridLayout's own counts never shrink after a re-arrange.
        return self._shape

    def arrange(self, max_columns: int | None) -> None:
        self._shape = layouts.grid_shape(len(self._buttons), self._layout, self._columns, max_columns)
        cols = self._shape[1]
        for button in self._buttons:
            self._grid.removeWidget(button)
        for index, button in enumerate(self._buttons):
            row, col = layouts.cell(index, cols)
            self._grid.addWidget(button, row, col)


def build_view(group: Group, icons: Sequence[QIcon], device_pixel_ratio: float) -> GroupView:
    if group.style is Style.TILES:
        return TilesView(group, icons)
    return RowsView(group, icons, device_pixel_ratio)


class _RowButton(QPushButton):
    """A row: the icon and name are laid out as labels inside the button,
    which allows a wider icon-to-text gap than QPushButton's built-in 4 px."""

    def __init__(self, shortcut: Shortcut, icon: QIcon, device_pixel_ratio: float) -> None:
        super().__init__()
        self.setObjectName("row")
        self.setToolTip(shortcut.target)
        line = QHBoxLayout(self)
        line.setContentsMargins(10, 0, 14, 0)
        line.setSpacing(12)
        glyph = QLabel()
        glyph.setPixmap(icon.pixmap(QSize(ROW_ICON, ROW_ICON), device_pixel_ratio))
        glyph.setFixedSize(ROW_ICON, ROW_ICON)
        text = QLabel(shortcut.name)
        text.setObjectName("rowText")
        # Names come from the config file: never interpret them as rich text.
        text.setTextFormat(Qt.TextFormat.PlainText)
        for label in (glyph, text):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        line.addWidget(glyph)
        line.addWidget(text, 1)

    def text_label(self) -> QLabel:
        return self.findChild(QLabel, "rowText")

    def sizeHint(self) -> QSize:
        return self.layout().sizeHint().expandedTo(QSize(ROW_MIN_WIDTH, ROW_HEIGHT))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


def _literal_ampersands(text: str) -> str:
    # Qt buttons read "&" as a keyboard-mnemonic marker; "&&" shows one "&".
    return text.replace("&", "&&")
