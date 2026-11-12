"""Things both the command line and the settings window do."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths

from perch import config, icons, palette, pinning
from perch.models import Group


def desktop() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation))


def config_argument(config_path: Path) -> Path | None:
    """What shortcuts should pass as --config: nothing for the default file."""
    return None if config_path == config.default_path() else config_path


def icons_folder(config_path: Path) -> Path:
    """Pin icons live beside the config file they were made from."""
    return config_path.parent / "icons"


def put_group_on_desktop(group: Group, config_path: Path, folder: Path | None = None) -> Path:
    """Draw the group's pin icon and put a shortcut to the group on the desktop
    (or ``folder``), ready to pin. Returns the shortcut's path."""
    icon_path = icons_folder(config_path) / f"{pinning.app_id(group.id)}.ico"
    icon = icons.write_pin_icon(group, icon_path, [icons.shortcut_icon(s) for s in group.shortcuts])
    return pinning.create_group_shortcut(
        group.id, group.name, folder or desktop(), config_argument(config_path), icon=icon
    )


def add_settings_to_start_menu(config_path: Path, folder: Path | None = None) -> Path:
    """Put "Perch Settings" in the Start menu (or ``folder``). Returns the shortcut's path."""
    icon_path = icons_folder(config_path) / "perch.ico"
    amber = palette.PIN_COLORS["amber"]
    icons.write_ico([icons.draw_mark(size, amber) for size in icons.ICO_SIZES], icon_path)
    return pinning.create_settings_shortcut(
        folder or pinning.start_menu_folder(), config_argument(config_path), icon=icon_path
    )


def settings_in_start_menu(folder: Path | None = None) -> Path | None:
    path = (folder or pinning.start_menu_folder()) / pinning.SETTINGS_SHORTCUT
    return path if path.exists() else None


def remove_settings_from_start_menu(folder: Path | None = None) -> None:
    folder = folder or pinning.start_menu_folder()
    (folder / pinning.SETTINGS_SHORTCUT).unlink(missing_ok=True)
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
