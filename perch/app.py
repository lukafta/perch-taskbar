"""Command line, startup, and what the panel's signals do."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from perch import actions, config, icons, launcher
from perch.models import Config, Group, Shortcut
from perch.store import ConfigStore
from perch.ui import theme
from perch.ui.panel import PerchPanel

log = logging.getLogger("perch")


def main(argv: list[str] | None = None) -> int:
    """Run Perch. ``argv`` excludes the program name (defaults to ``sys.argv[1:]``)."""
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # Our options aren't Qt's, so Qt only sees the program name.
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Perch")
    app.setWindowIcon(icons.app_icon())
    # The panel hides rather than closes, and a resident build will run with
    # no window showing at all, so quitting is always an explicit call.
    app.setQuitOnLastWindowClosed(False)

    config_path = config.default_path() if args.config is None else args.config
    try:
        cfg = config.load_or_create(config_path)
    except config.ConfigError as e:
        _report_config_error(config_path, str(e))
        return 1
    theme.apply_color_scheme(cfg.settings.theme)

    if args.create_shortcut is not None:
        return _create_shortcut(cfg, args.create_shortcut, config_path)

    group = cfg.group(args.group)
    if group is None:
        _error(_unknown_group(args.group, cfg, config_path))
        return 1
    if args.settings:
        return _run_settings(app, ConfigStore(config_path, cfg), group.id)
    return _run_panel(app, cfg, group, config_path)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m perch",
        description="Pop up a group of shortcuts above the Windows taskbar.",
    )
    parser.add_argument(
        "--group", metavar="GROUP", help="group to show, by name or id (default: the first one)"
    )
    parser.add_argument(
        "--settings", action="store_true", help="open Perch Settings (at --group, if given)"
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        type=Path,
        help=r"config file to use (default: %%APPDATA%%\Perch\config.json)",
    )
    parser.add_argument(
        "--create-shortcut",
        metavar="GROUP",
        help="put a shortcut that opens GROUP on the desktop, ready to pin to the taskbar",
    )
    return parser.parse_args(argv)


def _run_panel(app: QApplication, cfg: Config, group: Group, config_path: Path) -> int:
    panel = PerchPanel(group, show_header=cfg.settings.show_header)
    failures: list[str] = []
    settings_open = False

    def on_shortcut(shortcut: Shortcut) -> None:
        try:
            launcher.launch(shortcut)
        except launcher.LaunchError as e:
            failures.append(str(e))

    def on_settings(group_id: str) -> None:
        # The settings window takes over this process; the panel's dismissal
        # (it loses focus to the window) no longer ends it.
        nonlocal settings_open
        settings_open = True
        window = _open_settings(app, ConfigStore(config_path, cfg), group_id)
        panel.setProperty("settings_window", window)  # keep it alive

    def on_dismissed() -> None:
        if settings_open:
            return
        # One-shot mode: report any failure, then exit. The message box must
        # come first, because exiting the event loop also closes open dialogs.
        for message in failures:
            _error(message)
        app.exit(1 if failures else 0)

    panel.shortcut_activated.connect(on_shortcut)
    panel.settings_requested.connect(on_settings)
    panel.dismissed.connect(on_dismissed)
    panel.popup()
    return app.exec()


def _run_settings(app: QApplication, store: ConfigStore, group_id: str) -> int:
    window = _open_settings(app, store, group_id)
    code = app.exec()
    del window
    return code


def _open_settings(app: QApplication, store: ConfigStore, group_id: str):
    # Imported here: the panel-only path shouldn't pay for building the settings UI.
    from perch.ui.settings import SettingsWindow

    window = SettingsWindow(store, group_id)
    window.closed.connect(lambda: app.exit(0))
    window.show()
    window.raise_()
    window.activateWindow()
    return window


def _create_shortcut(cfg: Config, key: str, config_path: Path) -> int:
    group = cfg.group(key)
    if group is None:
        _error(_unknown_group(key, cfg, config_path))
        return 1
    if group.id not in config_path.read_text(encoding="utf-8-sig"):
        # The shortcut opens the group by id; make sure the file records it.
        config.save(cfg, config_path)
    path = actions.put_group_on_desktop(group, config_path, _desktop())
    print(f"Created {path}")
    print("To pin it: right-click it > Show more options > Pin to taskbar. Then you can delete it.")
    return 0


def _desktop() -> Path:
    return actions.desktop()


def _unknown_group(name: str, cfg: Config, config_path: Path) -> str:
    names = "\n".join(f"  • {g.name}" for g in cfg.groups)
    return f'There\'s no group named "{name}" in {config_path}.\n\nGroups:\n{names}'


def _error(message: str) -> None:
    # Logged for terminal runs; the box is what a taskbar launch (no console) shows.
    log.error(message)
    QMessageBox.warning(None, "Perch", message)


def _report_config_error(path: Path, message: str) -> None:
    log.error("%s: %s", path, message)
    box = QMessageBox(
        QMessageBox.Icon.Warning,
        "Perch",
        f"Perch couldn't use its config file:\n{path}\n\n{message}",
    )
    open_button = box.addButton("Open in Notepad", QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Close)
    box.exec()
    if box.clickedButton() is open_button:
        subprocess.Popen(["notepad.exe", str(path)])
