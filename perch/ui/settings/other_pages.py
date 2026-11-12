"""The Setup, Config file and Settings pages."""

from __future__ import annotations

import datetime
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from perch import actions, config, editing, icons, pinning
from perch.models import Theme
from perch.store import ConfigStore
from perch.ui.settings import common, dialogs

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SetupPaths:
    """Where setup reads and writes. Tests point these at temporary folders."""

    desktop: Path
    start_menu: Path
    taskbar_pins: Path

    @classmethod
    def default(cls) -> SetupPaths:
        return cls(actions.desktop(), pinning.start_menu_folder(), pinning.taskbar_pins_folder())


class SetupPage(QWidget):
    """Getting Perch onto the taskbar and into the Start menu.

    ``pin_requested(group_id)`` is handled by the window, the same as the
    group editor's Pin to taskbar button.
    """

    pin_requested = Signal(str)

    def __init__(
        self,
        store: ConfigStore,
        paths: SetupPaths,
        read_pins: Callable[[Path], set[str]] = pinning.pinned_app_ids,
    ) -> None:
        super().__init__()
        self._store = store
        self._paths = paths
        self._read_pins = read_pins

        page = QVBoxLayout(self)
        page.setContentsMargins(*common.PAGE_MARGINS)
        page.setSpacing(18)
        page.addWidget(common.title("Setup"))

        pins = QGroupBox("Taskbar pins")
        pins_column = QVBoxLayout(pins)
        pins_column.setSpacing(12)
        pins_column.addWidget(
            common.hint(
                "Each group can have its own taskbar icon. Perch puts a shortcut for the group on your "
                "desktop; right-click it and choose Show more options, then Pin to taskbar. "
                "Windows doesn't let apps pin themselves."
            )
        )
        self._pins_column = pins_column
        self.pin_rows = QWidget()
        pins_column.addWidget(self.pin_rows)
        check_again = QPushButton("Check again")
        check_again.clicked.connect(self.refresh)
        pins_column.addWidget(common.row(check_again))
        page.addWidget(pins)

        start = QGroupBox("Start menu")
        start_column = QVBoxLayout(start)
        start_column.setSpacing(12)
        start_column.addWidget(
            common.hint("Add Perch Settings to the Start menu, so you can open this window by searching for Perch.")
        )
        self.start_status = QLabel()
        self.start_button = QPushButton()
        self.start_button.clicked.connect(self._toggle_start_menu)
        start_column.addWidget(common.row(self.start_status, self.start_button))
        page.addWidget(start)
        page.addStretch(1)

        store.changed.connect(self._refresh_if_visible)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    def refresh(self) -> None:
        try:
            pinned = self._read_pins(self._paths.taskbar_pins)
        except Exception:  # noqa: BLE001 - a status line must never take the window down
            log.exception("Couldn't read the taskbar pins")
            pinned = set()

        old = self.pin_rows
        self.pin_rows = QWidget()
        grid = QGridLayout(self.pin_rows)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(2, 1)
        for row, group in enumerate(self._store.config.groups):
            icon = QLabel()
            icon.setPixmap(icons.pin_icon(group).pixmap(QSize(24, 24), self.devicePixelRatioF()))
            name = QLabel(group.name)
            name.setTextFormat(Qt.TextFormat.PlainText)
            is_pinned = pinning.app_id(group.id) in pinned
            status = QLabel("Pinned" if is_pinned else "Not pinned")
            status.setAccessibleName(f"{group.name}: {status.text()}")
            button = QPushButton("Put on desktop again" if is_pinned else "Put on desktop")
            button.setAccessibleName(f"Put a shortcut for {group.name} on the desktop")
            button.clicked.connect(lambda _checked=False, gid=group.id: self.pin_requested.emit(gid))
            grid.addWidget(icon, row, 0)
            grid.addWidget(name, row, 1)
            grid.addWidget(status, row, 2)
            grid.addWidget(button, row, 3)
        self._pins_column.replaceWidget(old, self.pin_rows)
        old.deleteLater()

        if actions.settings_in_start_menu(self._paths.start_menu):
            self.start_status.setText("Perch Settings is in the Start menu.")
            self.start_button.setText("Remove from Start menu")
        else:
            self.start_status.setText("Perch Settings isn't in the Start menu yet.")
            self.start_button.setText("Add to Start menu")

    def _refresh_if_visible(self) -> None:
        if self.isVisible():
            self.refresh()

    def _toggle_start_menu(self) -> None:
        try:
            if actions.settings_in_start_menu(self._paths.start_menu):
                actions.remove_settings_from_start_menu(self._paths.start_menu)
            else:
                self._store.save_now()
                actions.add_settings_to_start_menu(self._store.path, self._paths.start_menu)
        except Exception as e:  # noqa: BLE001 - shown to the user instead
            log.exception("Start menu change failed")
            self._store.problem.emit(f"Couldn't change the Start menu: {e}")
        self.refresh()


class ConfigPage(QWidget):
    """Where the groups are stored, and backups."""

    def __init__(self, store: ConfigStore) -> None:
        super().__init__()
        self._store = store

        page = QVBoxLayout(self)
        page.setContentsMargins(*common.PAGE_MARGINS)
        page.setSpacing(18)
        page.addWidget(common.title("Config file"))

        location = QGroupBox("Location")
        column = QVBoxLayout(location)
        column.setSpacing(12)
        # A read-only box rather than a label: a long path scrolls inside it
        # instead of stretching the page wider than the window.
        self.path_box = QLineEdit(str(store.path))
        self.path_box.setReadOnly(True)
        self.path_box.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.path_box.setAccessibleName("Config file location")
        self.path_box.setCursorPosition(0)
        column.addWidget(self.path_box)
        open_button = QPushButton("Open in Notepad")
        open_button.clicked.connect(lambda: subprocess.Popen(["notepad.exe", str(store.path)]))
        show_button = QPushButton("Show in folder")
        show_button.clicked.connect(lambda: subprocess.Popen(["explorer.exe", f"/select,{store.path}"]))
        reload_button = QPushButton("Reload from file")
        reload_button.clicked.connect(self.reload)
        column.addWidget(common.row(open_button, show_button, reload_button))
        column.addWidget(
            common.hint(
                "Perch Settings saves every change straight away. If you edit the file by hand, "
                "your changes show up here when you come back to this window, or when you press Reload."
            )
        )
        page.addWidget(location)

        backups = QGroupBox("Backups")
        backup_column = QVBoxLayout(backups)
        backup_column.setSpacing(12)
        backup_column.addWidget(
            common.hint("Save a copy of your groups, or bring back groups from a copy. Restoring keeps your current groups in config.json.bak.")
        )
        backup_button = QPushButton("Back up to a file…")
        backup_button.clicked.connect(self.back_up)
        restore_button = QPushButton("Restore from a file…")
        restore_button.clicked.connect(self.restore)
        backup_column.addWidget(common.row(backup_button, restore_button))
        page.addWidget(backups)

        self.status = QLabel()
        self.status.setAccessibleName("Config file status")
        page.addWidget(self.status)
        page.addStretch(1)
        store.saved.connect(lambda: self.status.setText(f"Saved at {_now()}."))

    def reload(self) -> None:
        try:
            self._store.reload()
        except config.ConfigError as e:
            self._store.problem.emit(f"config.json can't be read: {e}")
            return
        self.status.setText(f"Reloaded at {_now()}.")

    def back_up(self) -> None:
        suggested = Path.home() / "Documents" / f"perch-groups-{datetime.date.today():%Y-%m-%d}.json"
        target = dialogs.ask_save_path(self, suggested)
        if target is None:
            return
        try:
            self._store.back_up_to(target)
        except OSError as e:
            self._store.problem.emit(f"Couldn't write {target}: {e.strerror or e}")
            return
        self.status.setText(f"Backed up to {target}.")

    def restore(self) -> None:
        source = dialogs.ask_open_path(self)
        if source is None:
            return
        if not dialogs.confirm(
            self,
            "Restore groups",
            f"Replace your groups with the ones in {source.name}? "
            "Your current groups are kept in config.json.bak.",
            "Restore",
        ):
            return
        try:
            backup = self._store.restore_from(source)
        except config.ConfigError as e:
            self._store.problem.emit(f"{source.name} can't be used: {e}")
            return
        self.status.setText(f"Restored from {source}. Previous groups: {backup}.")


class GeneralPage(QWidget):
    """App-wide options."""

    THEME_LABELS = {Theme.SYSTEM: "Follow Windows", Theme.LIGHT: "Light", Theme.DARK: "Dark"}

    def __init__(self, store: ConfigStore) -> None:
        super().__init__()
        self._store = store
        self._loading = False

        page = QVBoxLayout(self)
        page.setContentsMargins(*common.PAGE_MARGINS)
        page.setSpacing(18)
        page.addWidget(common.title("Settings"))

        appearance = QGroupBox("Appearance")
        column = QVBoxLayout(appearance)
        column.addWidget(QLabel("Theme for the panel and this window"))
        self.theme_group = QButtonGroup(self)
        self.theme_buttons = {theme: QRadioButton(label) for theme, label in self.THEME_LABELS.items()}
        for button in self.theme_buttons.values():
            self.theme_group.addButton(button)
            column.addWidget(button)
        self.theme_group.buttonToggled.connect(self._theme_toggled)
        page.addWidget(appearance)

        panel = QGroupBox("Panel")
        panel_column = QVBoxLayout(panel)
        self.show_header = QCheckBox("Show the group's name at the top of the panel")
        self.show_header.toggled.connect(self._header_toggled)
        panel_column.addWidget(self.show_header)
        panel_column.addWidget(common.hint("The gear button stays either way, so Perch Settings is always one click away."))
        page.addWidget(panel)
        page.addStretch(1)

        store.changed.connect(self._reload)
        self._reload()

    def _reload(self) -> None:
        settings = self._store.config.settings
        self._loading = True
        try:
            common.check_only(self.theme_group, self.theme_buttons[settings.theme])
            self.show_header.setChecked(settings.show_header)
        finally:
            self._loading = False

    def _theme_toggled(self, button, checked: bool) -> None:
        theme = next((t for t, b in self.theme_buttons.items() if b is button), None)
        if checked and not self._loading and theme is not None:
            self._store.apply(lambda c: editing.update_settings(c, theme=theme))

    def _header_toggled(self, checked: bool) -> None:
        if not self._loading:
            self._store.apply(lambda c: editing.update_settings(c, show_header=checked))


def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")
