"""The editor for one group: name, look, taskbar pin, shortcuts."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QButtonGroup,
    QFileIconProvider,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from perch import config, editing, icons, palette
from perch.editing import EditError
from perch.models import Group, Layout, PinKind, Shortcut, Style
from perch.store import ConfigStore
from perch.ui.settings import common, dialogs

STYLE_LABELS = {Style.ROWS: "Rows", Style.TILES: "Tiles"}
LAYOUT_LABELS = {
    Layout.VERTICAL: "Vertical",
    Layout.HORIZONTAL: "Horizontal",
    Layout.SQUARE: "Square",
    Layout.GRID: "Grid",
}
PIN_KIND_LABELS = {
    PinKind.MARK: "Perch mark with a letter",
    PinKind.COLLAGE: "Collage of the first four app icons",
    PinKind.FILE: "An image file",
}


class ShortcutList(QListWidget):
    """The group's shortcuts. Drag entries to reorder; drop files from Explorer to add.

    * ``files_dropped(list[Path])``: files or folders dropped from outside.
    * ``reordered(list[int])``: the old indexes, in their new order.
    """

    files_dropped = Signal(list)
    reordered = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAccessibleName("Shortcuts")
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setIconSize(QSize(24, 24))
        self.setSpacing(2)
        self.setMinimumHeight(220)

    def order(self) -> list[int]:
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._from_outside(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._from_outside(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if self._from_outside(event):
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
            event.acceptProposedAction()
            if paths:
                self.files_dropped.emit(paths)
            return
        super().dropEvent(event)
        order = self.order()
        if order != sorted(order):
            self.reordered.emit(order)

    def _from_outside(self, event: QDropEvent | QDragMoveEvent | QDragEnterEvent) -> bool:
        return event.source() is not self and event.mimeData().hasUrls()


class GroupPage(QWidget):
    """Edits one group. Every change goes straight to the ConfigStore, which saves it.

    * ``preview_requested(group_id)``, ``pin_requested(group_id)``: handled by the window.
    """

    preview_requested = Signal(str)
    pin_requested = Signal(str)

    def __init__(self, store: ConfigStore) -> None:
        super().__init__()
        self._store = store
        self._group_id: str | None = None
        self._loading = False
        self._provider = QFileIconProvider()
        self._icons: dict[tuple[str, str | None], QIcon] = {}

        page = QVBoxLayout(self)
        page.setContentsMargins(*common.PAGE_MARGINS)
        page.setSpacing(18)
        page.addLayout(self._build_header())
        page.addWidget(self._build_look())
        page.addWidget(self._build_pin())
        page.addWidget(self._build_shortcuts())
        page.addStretch(1)
        store.changed.connect(self._reload)

    # -- public ------------------------------------------------------------

    def show_group(self, group_id: str) -> None:
        self._group_id = group_id
        self._reload()

    def group(self) -> Group | None:
        if self._group_id is None:
            return None
        try:
            return editing.find(self._store.config, self._group_id)
        except EditError:
            return None

    def add_paths(self, paths: list[Path]) -> None:
        shortcuts = [editing.shortcut_for_path(path) for path in paths]
        if shortcuts and self._edit(editing.add_shortcuts, shortcuts):
            self.shortcut_list.setCurrentRow(self.shortcut_list.count() - 1)

    def add_shortcut(self, shortcut: Shortcut) -> None:
        if self._edit(editing.add_shortcuts, [shortcut]):
            self.shortcut_list.setCurrentRow(self.shortcut_list.count() - 1)

    def edit_selected(self) -> None:
        group, row = self.group(), self.shortcut_list.currentRow()
        if group is None or row < 0:
            return
        changed = dialogs.ask_shortcut(self, group.shortcuts[row])
        if changed is not None:
            self._edit(editing.replace_shortcut, row, changed)

    def remove_selected(self) -> None:
        row = self.shortcut_list.currentRow()
        if row >= 0 and self._edit(editing.remove_shortcut, row):
            self.shortcut_list.setCurrentRow(min(row, self.shortcut_list.count() - 1))

    # -- building ----------------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        self.name_edit = QLineEdit()
        self.name_edit.setAccessibleName("Group name")
        font = QFont(self.name_edit.font())
        font.setPointSizeF(font.pointSizeF() * 1.5)
        font.setWeight(QFont.Weight.DemiBold)
        self.name_edit.setFont(font)
        self.name_edit.editingFinished.connect(self._rename)

        self.preview_button = QPushButton("Preview")
        self.preview_button.setToolTip("Open this group's panel above the taskbar")
        self.preview_button.clicked.connect(lambda: self.preview_requested.emit(self._group_id))
        self.pin_button = QPushButton("Pin to taskbar…")
        self.pin_button.setToolTip("Put a shortcut for this group on the desktop, ready to pin")
        self.pin_button.clicked.connect(lambda: self.pin_requested.emit(self._group_id))
        self.delete_button = QPushButton("Delete group")
        self.delete_button.clicked.connect(self._delete)

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(self.name_edit, 1)
        for button in (self.preview_button, self.pin_button, self.delete_button):
            header.addWidget(button)
        return header

    def _build_look(self) -> QGroupBox:
        box = QGroupBox("Look")
        form = QFormLayout(box)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)

        self.style_group = QButtonGroup(self)
        self.style_buttons = {style: QRadioButton(label) for style, label in STYLE_LABELS.items()}
        for button in self.style_buttons.values():
            self.style_group.addButton(button)
        command = QRadioButton("Command (coming in a later update)")
        command.setEnabled(False)
        self.style_group.buttonToggled.connect(self._style_toggled)
        form.addRow("Style", common.row(*self.style_buttons.values(), command))

        self.layout_group = QButtonGroup(self)
        self.layout_buttons = {layout: QRadioButton(label) for layout, label in LAYOUT_LABELS.items()}
        for button in self.layout_buttons.values():
            self.layout_group.addButton(button)
        self.layout_group.buttonToggled.connect(self._layout_toggled)
        self.layout_hint = common.hint("Layouts apply to Tiles. Rows is always one vertical list.")
        layout_column = QWidget()
        stack = QVBoxLayout(layout_column)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(common.row(*self.layout_buttons.values()))
        stack.addWidget(self.layout_hint)
        form.addRow("Layout", layout_column)

        self.columns = QSpinBox()
        self.columns.setRange(1, config.MAX_COLUMNS)
        self.columns.setAccessibleName("Columns")
        self.columns.valueChanged.connect(self._columns_changed)
        form.addRow("Columns", common.row(self.columns, common.hint("Used by the Grid layout.", wrap=False)))

        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(round(config.MIN_OPACITY * 100), 100)
        self.opacity.setFixedWidth(280)
        self.opacity.setAccessibleName("Opacity")
        self.opacity.valueChanged.connect(self._opacity_changed)
        self.opacity_value = QLabel()
        self.opacity_value.setMinimumWidth(48)
        form.addRow("Opacity", common.row(self.opacity, self.opacity_value))
        return box

    def _build_pin(self) -> QGroupBox:
        box = QGroupBox("Taskbar pin")
        outer = QHBoxLayout(box)
        outer.setSpacing(24)

        self.pin_preview = QLabel()
        self.pin_preview.setFixedSize(QSize(132, 76))
        self.pin_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pin_preview.setStyleSheet("background-color: #1C1C1C; border-radius: 8px;")
        self.pin_preview.setAccessibleName("Pin preview on a dark taskbar")
        outer.addWidget(self.pin_preview, 0, Qt.AlignmentFlag.AlignTop)

        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(12)
        outer.addLayout(form, 1)

        self.kind_group = QButtonGroup(self)
        self.kind_buttons = {kind: QRadioButton(label) for kind, label in PIN_KIND_LABELS.items()}
        kinds = QWidget()
        kind_stack = QVBoxLayout(kinds)
        kind_stack.setContentsMargins(0, 0, 0, 0)
        for button in self.kind_buttons.values():
            self.kind_group.addButton(button)
            kind_stack.addWidget(button)
        self.kind_group.buttonToggled.connect(self._kind_toggled)
        form.addRow("Shows", kinds)

        self.color_group = QButtonGroup(self)
        self.color_buttons: dict[str, QToolButton] = {}
        for name, colors in palette.PIN_COLORS.items():
            swatch = QToolButton()
            swatch.setCheckable(True)
            swatch.setIcon(_swatch_icon(colors.fill))
            swatch.setIconSize(QSize(22, 22))
            swatch.setFixedSize(QSize(36, 36))
            swatch.setAccessibleName(name.title())
            swatch.setToolTip(name.title())
            self.color_group.addButton(swatch)
            self.color_buttons[name] = swatch
        self.color_group.buttonClicked.connect(self._color_clicked)
        self.custom_color = QPushButton("Custom…")
        self.custom_color.clicked.connect(self._pick_color)
        form.addRow("Colour", common.row(*self.color_buttons.values(), self.custom_color))

        self.letter = QLineEdit()
        self.letter.setMaxLength(2)
        self.letter.setFixedWidth(64)
        self.letter.setAccessibleName("Pin letter")
        self.letter.editingFinished.connect(self._letter_changed)
        form.addRow("Letter", common.row(self.letter, common.hint("Leave empty to use the group name's first letter.", wrap=False)))

        self.pin_file = QLineEdit()
        self.pin_file.setReadOnly(True)
        self.pin_file.setPlaceholderText("No image chosen")
        self.pin_file.setAccessibleName("Pin image")
        self.choose_file = QPushButton("Choose…")
        self.choose_file.clicked.connect(self._choose_image)
        image_row = QWidget()
        line = QHBoxLayout(image_row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(self.pin_file, 1)
        line.addWidget(self.choose_file)
        form.addRow("Image", image_row)
        form.addRow(common.hint("Changed the pin? Use Pin to taskbar again, then unpin the old icon and pin the new one."))
        return box

    def _build_shortcuts(self) -> QGroupBox:
        self.shortcuts_box = QGroupBox("Shortcuts")
        column = QVBoxLayout(self.shortcuts_box)
        column.setSpacing(10)

        self.shortcut_list = ShortcutList()
        self.shortcut_list.files_dropped.connect(self.add_paths)
        self.shortcut_list.reordered.connect(lambda order: self._edit(editing.reorder_shortcuts, order))
        self.shortcut_list.itemDoubleClicked.connect(lambda _item: self.edit_selected())
        self.shortcut_list.currentRowChanged.connect(lambda _row: self._update_shortcut_buttons())
        column.addWidget(self.shortcut_list)

        self.add_files_button = QPushButton("Add apps or files…")
        self.add_files_button.clicked.connect(lambda: self.add_paths(dialogs.ask_files(self)))
        self.add_folder_button = QPushButton("Add folder…")
        self.add_folder_button.clicked.connect(self._add_folder)
        self.add_link_button = QPushButton("Add web link…")
        self.add_link_button.clicked.connect(self._add_link)
        self.edit_button = QPushButton("Edit…")
        self.edit_button.clicked.connect(self.edit_selected)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_selected)

        buttons = QHBoxLayout()
        for button in (self.add_files_button, self.add_folder_button, self.add_link_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.edit_button)
        buttons.addWidget(self.remove_button)
        column.addLayout(buttons)
        column.addWidget(
            common.hint("Drag apps, shortcuts, files or folders onto the list to add them. Drag entries to reorder them.")
        )
        return self.shortcuts_box

    # -- showing the group -------------------------------------------------

    def _reload(self) -> None:
        group = self.group()
        if group is None:
            return
        self._loading = True
        try:
            if not self.name_edit.hasFocus():
                self.name_edit.setText(group.name)
            self.delete_button.setEnabled(len(self._store.config.groups) > 1)

            tiles = group.style is Style.TILES
            common.check_only(self.style_group, self.style_buttons[group.style])
            common.check_only(self.layout_group, self.layout_buttons[group.layout])
            for button in self.layout_buttons.values():
                button.setEnabled(tiles)
            self.layout_hint.setVisible(not tiles)
            self.columns.setValue(group.columns)
            self.columns.setEnabled(tiles and group.layout is Layout.GRID)
            percent = round(group.opacity * 100)
            self.opacity.setValue(percent)
            self.opacity_value.setText(f"{percent}%")

            pin = group.pin
            mark = pin.kind is PinKind.MARK
            common.check_only(self.kind_group, self.kind_buttons[pin.kind])
            common.check_only(self.color_group, self.color_buttons.get(pin.color.lower()))
            custom = pin.color.lower() not in palette.PIN_COLORS
            self.custom_color.setText(f"Custom ({pin.color.upper()})…" if custom else "Custom…")
            for widget in (*self.color_buttons.values(), self.custom_color, self.letter):
                widget.setEnabled(mark)
            first = next((c.upper() for c in group.name if c.isalnum()), "")
            self.letter.setPlaceholderText(first)
            if not self.letter.hasFocus():
                self.letter.setText(pin.letter or "")
            self.pin_file.setText(pin.file or "")
            self.choose_file.setEnabled(pin.kind is PinKind.FILE)
            self._show_pin_preview(group)

            self._fill_shortcuts(group)
            self.shortcuts_box.setTitle(f"Shortcuts ({len(group.shortcuts)})")
        finally:
            self._loading = False
        self._update_shortcut_buttons()

    def _show_pin_preview(self, group: Group) -> None:
        icon = icons.pin_icon(group, [self._icon(s) for s in group.shortcuts[:4]])
        ratio = self.devicePixelRatioF()
        canvas = QPixmap(QSize(132, 76) * ratio)
        canvas.setDevicePixelRatio(ratio)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.drawPixmap(QPoint(18, 14), icon.pixmap(QSize(48, 48), ratio))
        painter.drawPixmap(QPoint(86, 26), icon.pixmap(QSize(24, 24), ratio))
        painter.end()
        self.pin_preview.setPixmap(canvas)

    def _fill_shortcuts(self, group: Group) -> None:
        current = self.shortcut_list.currentRow()
        with QSignalBlocker(self.shortcut_list):
            self.shortcut_list.clear()
            for index, shortcut in enumerate(group.shortcuts):
                item = QListWidgetItem(self._icon(shortcut), f"{shortcut.name}\n{shortcut.target}")
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(shortcut.target)
                self.shortcut_list.addItem(item)
            if group.shortcuts:
                self.shortcut_list.setCurrentRow(max(0, min(current, len(group.shortcuts) - 1)))

    def _update_shortcut_buttons(self) -> None:
        selected = self.shortcut_list.currentRow() >= 0
        self.edit_button.setEnabled(selected)
        self.remove_button.setEnabled(selected)

    def _icon(self, shortcut: Shortcut) -> QIcon:
        key = (shortcut.target, shortcut.icon)
        if key not in self._icons:
            self._icons[key] = icons.shortcut_icon(shortcut, self._provider)
        return self._icons[key]

    # -- edits -------------------------------------------------------------

    def _edit(self, edit, *args, **kwargs) -> bool:
        if self._group_id is None:
            return False
        group_id = self._group_id
        return self._store.apply(lambda c: edit(c, group_id, *args, **kwargs))

    def _rename(self) -> None:
        group = self.group()
        if self._loading or group is None or self.name_edit.text().strip() == group.name:
            return
        if not self._edit(editing.rename_group, self.name_edit.text()):
            self.name_edit.setText(group.name)

    def _delete(self) -> None:
        group = self.group()
        if group is None:
            return
        count = len(group.shortcuts)
        what = f'"{group.name}"' if count == 0 else f'"{group.name}" and its {count} shortcut{"" if count == 1 else "s"}'
        if dialogs.confirm(
            self,
            "Delete group",
            f"Delete {what}? If it's pinned to the taskbar, that pin will stop working.",
            "Delete",
        ):
            self._store.apply(lambda c: editing.delete_group(c, group.id))

    def _style_toggled(self, button: QAbstractButton, checked: bool) -> None:
        style = next((s for s, b in self.style_buttons.items() if b is button), None)
        if checked and not self._loading and style is not None:
            self._edit(editing.update_group, style=style)

    def _layout_toggled(self, button: QAbstractButton, checked: bool) -> None:
        layout = next((l for l, b in self.layout_buttons.items() if b is button), None)
        if checked and not self._loading and layout is not None:
            self._edit(editing.update_group, layout=layout)

    def _columns_changed(self, value: int) -> None:
        if not self._loading:
            self._edit(editing.update_group, columns=value)

    def _opacity_changed(self, value: int) -> None:
        self.opacity_value.setText(f"{value}%")
        if not self._loading:
            self._edit(editing.update_group, opacity=value / 100)

    def _kind_toggled(self, button: QAbstractButton, checked: bool) -> None:
        kind = next((k for k, b in self.kind_buttons.items() if b is button), None)
        if not checked or self._loading or kind is None:
            return
        group = self.group()
        if kind is PinKind.FILE and group is not None and not group.pin.file:
            chosen = dialogs.ask_image(self)
            if chosen is None:
                self._reload()  # put the radio back
                return
            self._edit(editing.update_pin, kind=kind, file=str(chosen))
        else:
            self._edit(editing.update_pin, kind=kind)

    def _color_clicked(self, button: QAbstractButton) -> None:
        name = next((n for n, b in self.color_buttons.items() if b is button), None)
        if name is not None:
            self._edit(editing.update_pin, color=name)

    def _pick_color(self) -> None:
        group = self.group()
        if group is None:
            return
        chosen = dialogs.ask_color(self, palette.pin_colors(group.pin.color).fill)
        if chosen is not None:
            self._edit(editing.update_pin, color=chosen)

    def _letter_changed(self) -> None:
        if not self._loading:
            self._edit(editing.update_pin, letter=self.letter.text().strip() or None)

    def _choose_image(self) -> None:
        chosen = dialogs.ask_image(self)
        if chosen is not None:
            self._edit(editing.update_pin, kind=PinKind.FILE, file=str(chosen))

    def _add_folder(self) -> None:
        folder = dialogs.ask_folder(self)
        if folder is not None:
            self.add_paths([folder])

    def _add_link(self) -> None:
        shortcut = dialogs.ask_shortcut(self, web=True)
        if shortcut is not None:
            self.add_shortcut(shortcut)


def _swatch_icon(fill: str) -> QIcon:
    size = 44
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(0, 0, 0, 60), 2))
    painter.setBrush(QColor(fill))
    painter.drawEllipse(3, 3, size - 6, size - 6)
    painter.end()
    return QIcon(pixmap)
