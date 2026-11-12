"""Perch Settings: a side menu of groups and pages, and the page being shown."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QCloseEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from perch import actions, config, editing, icons, launcher
from perch.models import PinKind, Shortcut
from perch.store import ConfigStore
from perch.ui import theme
from perch.ui.panel import PerchPanel
from perch.ui.settings import dialogs
from perch.ui.settings.group_page import GroupPage
from perch.ui.settings.other_pages import ConfigPage, GeneralPage, SetupPage, SetupPaths

log = logging.getLogger(__name__)

PAGES = ("Setup", "Config file", "Settings")


class GroupList(QListWidget):
    """The groups in the side menu. Drag to reorder; the first opens by default.

    ``reordered(list[str])``: group ids in their new order.
    """

    reordered = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAccessibleName("Groups")
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setIconSize(QSize(24, 24))
        self.setSpacing(2)

    def ids(self) -> list[str]:
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]

    def dropEvent(self, event: QDropEvent) -> None:
        before = self.ids()
        super().dropEvent(event)
        if self.ids() != before:
            self.reordered.emit(self.ids())


class SettingsWindow(QWidget):
    """``closed()`` is emitted once the window has saved and closed."""

    closed = Signal()

    def __init__(self, store: ConfigStore, group_key: str | None = None, setup_paths: SetupPaths | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Perch Settings")
        self.setWindowIcon(icons.app_icon())
        self.resize(1040, 780)
        self.setMinimumSize(720, 520)
        self.store = store
        self._setup_paths = setup_paths or SetupPaths.default()
        self._sidebar_key: tuple | None = None
        self._applied_theme = None
        self._preview: PerchPanel | None = None

        # Side menu
        self.group_list = GroupList()
        self.group_list.currentItemChanged.connect(self._group_chosen)
        self.group_list.reordered.connect(lambda ids: self.store.apply(lambda c: editing.reorder_groups(c, ids)))
        new_group = QPushButton("New group")
        new_group.clicked.connect(self.new_group)
        self.page_list = QListWidget()
        self.page_list.setAccessibleName("Perch")
        self.page_list.addItems(PAGES)
        self.page_list.setFixedHeight(self.page_list.sizeHintForRow(0) * len(PAGES) + 3 * len(PAGES) + 8)
        self.page_list.currentRowChanged.connect(self._page_chosen)

        sidebar = QWidget()
        sidebar.setFixedWidth(250)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 20, 8, 16)
        side.setSpacing(8)
        side.addWidget(_caption("Groups"))
        side.addWidget(self.group_list, 1)
        side.addWidget(new_group)
        side.addSpacing(16)
        side.addWidget(_caption("Perch"))
        side.addWidget(self.page_list)

        # Pages
        self.group_page = GroupPage(store)
        self.group_page.preview_requested.connect(self.preview)
        self.group_page.pin_requested.connect(self.pin_group)
        self.setup_page = SetupPage(store, self._setup_paths)
        self.setup_page.pin_requested.connect(self.pin_group)
        self.config_page = ConfigPage(store)
        self.general_page = GeneralPage(store)
        self.stack = QStackedWidget()
        for page in (self.group_page, self.setup_page, self.config_page, self.general_page):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)

        # Problems banner
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        self.banner.setStyleSheet("QFrame#banner { background-color: #FFE6C2; border-radius: 6px; } QFrame#banner QLabel { color: #3D2A0A; }")
        self.banner_text = QLabel()
        self.banner_text.setWordWrap(True)
        self.banner_text.setTextFormat(Qt.TextFormat.PlainText)
        dismiss = QPushButton("Dismiss")
        dismiss.clicked.connect(self.banner.hide)
        banner_row = QHBoxLayout(self.banner)
        banner_row.setContentsMargins(14, 10, 10, 10)
        banner_row.addWidget(self.banner_text, 1)
        banner_row.addWidget(dismiss)
        self.banner.hide()

        content = QVBoxLayout()
        content.setContentsMargins(0, 12, 12, 0)
        content.addWidget(self.banner)
        content.addWidget(self.stack, 1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addLayout(content, 1)

        store.problem.connect(self.show_problem)
        store.changed.connect(self._on_changed)
        self._on_changed()
        start = store.config.group(group_key)
        self.select_group(start.id if start else store.config.groups[0].id)

    # -- navigation --------------------------------------------------------

    def select_group(self, group_id: str) -> None:
        ids = self.group_list.ids()
        row = ids.index(group_id) if group_id in ids else 0
        self.group_list.setCurrentRow(row)
        if self.group_list.currentRow() == row:  # already current: no change signal
            self._group_chosen(self.group_list.currentItem(), None)

    def select_page(self, name: str) -> None:
        self.page_list.setCurrentRow(PAGES.index(name))

    def current_group_id(self) -> str | None:
        item = self.group_list.currentItem()
        if item is None or self.stack.currentIndex() != 0:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _group_chosen(self, item: QListWidgetItem | None, _previous) -> None:
        if item is None:
            return
        with QSignalBlocker(self.page_list):
            self.page_list.setCurrentRow(-1)
        self.group_page.show_group(item.data(Qt.ItemDataRole.UserRole))
        self.stack.setCurrentIndex(0)

    def _page_chosen(self, row: int) -> None:
        if row < 0:
            return
        with QSignalBlocker(self.group_list):
            self.group_list.setCurrentRow(-1)
        self.stack.setCurrentIndex(row + 1)

    # -- actions -----------------------------------------------------------

    def new_group(self) -> None:
        created: list[str] = []

        def add(c):
            new_config, group = editing.add_group(c)
            created.append(group.id)
            return new_config

        if self.store.apply(add):
            self.select_group(created[0])
            self.group_page.name_edit.setFocus()
            self.group_page.name_edit.selectAll()

    def preview(self, group_id: str) -> None:
        group = self.store.config.group(group_id)
        if group is None:
            return
        if self._preview is not None:
            self._preview.dismiss()
        panel = PerchPanel(group, show_header=self.store.config.settings.show_header, settings_button=False)
        panel.shortcut_activated.connect(self._launch)
        panel.dismissed.connect(panel.deleteLater)
        panel.destroyed.connect(lambda: setattr(self, "_preview", None))
        self._preview = panel
        panel.popup()

    def pin_group(self, group_id: str) -> None:
        group = self.store.config.group(group_id)
        if group is None:
            return
        self.store.save_now()  # the shortcut opens the group by id, so the file must have it
        try:
            path = actions.put_group_on_desktop(group, self.store.path, self._setup_paths.desktop)
        except Exception as e:  # noqa: BLE001 - shown to the user instead
            log.exception("Couldn't create the shortcut")
            self.show_problem(f"Couldn't create the shortcut: {e}")
            return
        dialogs.inform(
            self,
            "Pin to taskbar",
            f'"{path.stem}" is on your desktop.\n\n'
            "To pin it, right-click it and choose Show more options, then Pin to taskbar. "
            "You can delete the desktop shortcut afterwards.\n\n"
            "If this group was pinned before, unpin the old icon first.",
        )
        self.setup_page.refresh()

    def show_problem(self, message: str) -> None:
        self.banner_text.setText(message)
        self.banner.show()

    # -- keeping in step with the config -----------------------------------

    def _on_changed(self) -> None:
        self._refresh_sidebar()
        wanted = self.store.config.settings.theme
        if wanted != self._applied_theme:
            theme.apply_color_scheme(wanted)
            self._applied_theme = wanted
        # The group being edited was deleted: move to the first one.
        if self.stack.currentIndex() == 0 and self.group_page.group() is None:
            self.select_group(self.store.config.groups[0].id)

    def _refresh_sidebar(self) -> None:
        groups = self.store.config.groups
        key = tuple(
            (g.id, g.name, g.pin, g.pin_letter, tuple(s.target for s in g.shortcuts[:4]) if g.pin.kind is PinKind.COLLAGE else ())
            for g in groups
        )
        if key == self._sidebar_key:
            return
        self._sidebar_key = key
        selected = self.group_list.currentItem()
        selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected is not None else None
        with QSignalBlocker(self.group_list):
            self.group_list.clear()
            for group in groups:
                collage = [icons.shortcut_icon(s) for s in group.shortcuts[:4]] if group.pin.kind is PinKind.COLLAGE else []
                item = QListWidgetItem(icons.pin_icon(group, collage), group.name)
                item.setData(Qt.ItemDataRole.UserRole, group.id)
                self.group_list.addItem(item)
                if group.id == selected_id:
                    self.group_list.setCurrentItem(item)

    def _launch(self, shortcut: Shortcut) -> None:
        try:
            launcher.launch(shortcut)
        except launcher.LaunchError as e:
            dialogs.inform(self, "Perch", str(e))

    # -- Qt events ---------------------------------------------------------

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.pick_up_hand_edits()

    def pick_up_hand_edits(self) -> None:
        """Reload config.json if it was edited by hand since this window last saved it."""
        if self.store.save_pending or not self.store.changed_on_disk():
            return
        try:
            self.store.reload()
        except config.ConfigError as e:
            self.show_problem(
                f"config.json was changed outside Perch Settings and can't be read: {e} "
                "Fix the file and come back to this window, or keep editing here to replace it."
            )
            return
        self.show_problem("Picked up changes made to config.json outside Perch Settings.")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.store.save_pending:
            self.store.save_now()
        if self._preview is not None:
            self._preview.dismiss()
        super().closeEvent(event)
        self.closed.emit()


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    font = QFont(label.font())
    font.setWeight(QFont.Weight.DemiBold)
    label.setFont(font)
    return label
