"""Shortcut files for pinning groups to the taskbar and finding Perch Settings.

Windows treats every shortcut to the same program as one app, so a second
``pythonw.exe -m perch --group X`` shortcut couldn't be pinned beside the
first. Each group's shortcut therefore carries its own AppUserModelID, which
makes the taskbar treat it as a separate app. Browsers do the same for
per-profile shortcuts.

pywin32 is imported inside the functions that need it, so this module loads
anywhere.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

APP_ID_PREFIX = "Perch.Group."
SETTINGS_APP_ID = "Perch.Settings"
SETTINGS_SHORTCUT = "Perch Settings.lnk"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def app_id(group_id: str) -> str:
    """The AppUserModelID of a group's pin. Group ids never change, so neither does this."""
    return APP_ID_PREFIX + group_id


def shortcut_filename(group_name: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", group_name).rstrip(". ")
    return f"Perch - {safe}.lnk"


def taskbar_pins_folder() -> Path:
    """Where Windows keeps a copy of each shortcut pinned to the taskbar."""
    return _appdata() / "Microsoft" / "Internet Explorer" / "Quick Launch" / "User Pinned" / "TaskBar"


def start_menu_folder() -> Path:
    """Perch's folder in the user's Start menu."""
    return _appdata() / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Perch"


def create_group_shortcut(
    group_id: str,
    group_name: str,
    folder: Path,
    config_path: Path | None = None,
    icon: Path | None = None,
) -> Path:
    """Write "Perch - <name>.lnk" into ``folder`` and return its path.

    It runs ``pythonw -m perch --group <id>`` (no console window) from the
    project folder. The id, unlike the name, survives renames. ``config_path``
    is passed along when the group lives in a non-default config file.
    """
    args = ["-m", "perch", "--group", group_id]
    if config_path is not None:
        args += ["--config", str(config_path.resolve())]
    return _write_link(
        folder / shortcut_filename(group_name),
        args,
        f"Open the {group_name} group in Perch",
        app_id(group_id),
        icon,
    )


def create_settings_shortcut(folder: Path, config_path: Path | None = None, icon: Path | None = None) -> Path:
    """Write "Perch Settings.lnk" into ``folder`` and return its path."""
    args = ["-m", "perch", "--settings"]
    if config_path is not None:
        args += ["--config", str(config_path.resolve())]
    return _write_link(folder / SETTINGS_SHORTCUT, args, "Set up Perch's groups and shortcuts", SETTINGS_APP_ID, icon)


def read_app_id(path: Path) -> str | None:
    """The AppUserModelID stored in a shortcut file, if it has one."""
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
    )
    try:
        link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(path))
        value = link.QueryInterface(propsys.IID_IPropertyStore).GetValue(pscon.PKEY_AppUserModel_ID).GetValue()
    except pythoncom.com_error:
        return None
    return value or None


def pinned_app_ids(folder: Path | None = None) -> set[str]:
    """App ids of everything pinned to the taskbar that carries one."""
    folder = folder or taskbar_pins_folder()
    if not folder.is_dir():
        return set()
    found = (read_app_id(path) for path in folder.glob("*.lnk"))
    return {value for value in found if value}


def _write_link(path: Path, args: list[str], description: str, link_app_id: str, icon: Path | None) -> Path:
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
    )
    link.SetPath(str(_gui_python()))
    link.SetArguments(subprocess.list2cmdline(args))
    link.SetWorkingDirectory(str(PROJECT_ROOT))
    link.SetDescription(description)
    if icon is not None:
        link.SetIconLocation(str(icon.resolve()), 0)
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(link_app_id, pythoncom.VT_LPWSTR))
    store.Commit()

    path.parent.mkdir(parents=True, exist_ok=True)
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(path), 0)
    return path


def _gui_python() -> Path:
    """pythonw.exe beside the running interpreter, which opens no console window."""
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else python


def _appdata() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
