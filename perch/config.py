"""Reading and writing the user's groups (config.json).

File format, version 1 (every key but "groups", "name", "shortcuts" and
"target" is optional)::

    {
      "version": 1,
      "settings": {"theme": "system", "show_header": true},   # theme: system | light | dark
      "groups": [
        {
          "id": "essentials-a74d251d",      # stable; written by the settings window
          "name": "Essentials",
          "opacity": 0.97,
          "style": "rows",                  # rows | tiles
          "layout": "vertical",             # tiles only: vertical | horizontal | square | grid
          "columns": 4,                     # grid only
          "pin": {"kind": "mark", "color": "amber", "letter": "E"},
          "shortcuts": [
            {"name": "Notepad", "target": "notepad.exe"},
            {"name": "Docs", "target": "%USERPROFILE%\\Documents", "icon": "C:\\icons\\docs.ico"}
          ]
        }
      ]
    }

Keys this build doesn't know are ignored, so ``"note": "..."`` works as a
comment (JSON has none). A file from a newer version is refused rather than
half-read.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Any

from perch import palette
from perch.models import Config, Group, Layout, Pin, PinKind, Settings, Shortcut, Style, Theme

log = logging.getLogger(__name__)

VERSION = 1
MIN_OPACITY = 0.1
MAX_COLUMNS = 12
_GROUP_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")

# Written on first run so there's a real file to edit.
DEFAULT_CONFIG = Config(
    groups=(
        Group(
            "Essentials",
            (
                Shortcut("Notepad", "notepad.exe"),
                Shortcut("Calculator", "calc.exe"),
                Shortcut("File Explorer", "explorer.exe"),
            ),
            pin=Pin(color="amber"),
        ),
        Group(
            "Settings",
            (
                Shortcut("Display", "ms-settings:display"),
                Shortcut("Sound", "ms-settings:sound"),
                Shortcut("Bluetooth & devices", "ms-settings:bluetooth"),
            ),
            style=Style.TILES,
            layout=Layout.HORIZONTAL,
            pin=Pin(color="blue"),
        ),
    )
)


class ConfigError(Exception):
    """The config file can't be used. The message says where and why, for the user."""


def _appdata() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")


def default_path() -> Path:
    """``%APPDATA%\\Perch\\config.json``."""
    return _appdata() / "Perch" / "config.json"


def load_or_create(path: Path) -> Config:
    """Read ``path``, first writing the default config there if it doesn't exist.

    An existing file is never overwritten, even if it's broken: the error goes
    to the user so they can fix their edit.
    """
    if not path.exists():
        save(DEFAULT_CONFIG, path)
        log.info("Created %s with sample groups", path)
        return DEFAULT_CONFIG
    return load(path)


def load(path: Path) -> Config:
    try:
        # utf-8-sig also accepts the byte-order mark some editors add.
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as e:
        raise ConfigError("The file isn't UTF-8 text.") from e
    except OSError as e:
        raise ConfigError(f"Can't read the file: {e.strerror or e}") from e
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Line {e.lineno}, column {e.colno}: {e.msg}.") from e
    return from_dict(data)


def save(config: Config, path: Path) -> None:
    """Write ``config`` to ``path`` atomically.

    The text goes to a temporary file in the same folder, which then replaces
    ``path`` in one step, so a crash mid-write can't leave a truncated file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(to_dict(config), indent=2, ensure_ascii=False) + "\n"
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def to_dict(config: Config) -> dict[str, Any]:
    return {
        "version": VERSION,
        "settings": {
            "theme": config.settings.theme.value,
            "show_header": config.settings.show_header,
        },
        "groups": [_group_to_dict(g) for g in config.groups],
    }


def _group_to_dict(group: Group) -> dict[str, Any]:
    pin: dict[str, Any] = {"kind": group.pin.kind.value, "color": group.pin.color}
    if group.pin.letter:
        pin["letter"] = group.pin.letter
    if group.pin.file:
        pin["file"] = group.pin.file
    shortcuts = []
    for s in group.shortcuts:
        entry = {"name": s.name, "target": s.target}
        if s.icon:
            entry["icon"] = s.icon
        shortcuts.append(entry)
    return {
        "id": group.id,
        "name": group.name,
        "opacity": group.opacity,
        "style": group.style.value,
        "layout": group.layout.value,
        "columns": group.columns,
        "pin": pin,
        "shortcuts": shortcuts,
    }


def from_dict(data: Any) -> Config:
    if not isinstance(data, dict):
        raise ConfigError("The file must hold a JSON object: { ... }.")

    version = data.get("version", VERSION)
    if not _is_int(version) or version < 1:
        raise ConfigError('"version" must be a whole number.')
    if version > VERSION:
        raise ConfigError(
            f"This file is version {version}, from a newer Perch. "
            f"This copy reads up to version {VERSION}."
        )

    groups = data.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ConfigError('"groups" must be a list with at least one group.')
    parsed = tuple(_group(g, f"groups[{i}]") for i, g in enumerate(groups))

    names: set[str] = set()
    ids: set[str] = set()
    for group in parsed:
        key = group.name.casefold()
        if key in names:
            raise ConfigError(f'Two groups are named "{group.name}". Group names must be unique.')
        if group.id in ids:
            raise ConfigError(f'Two groups have the id "{group.id}". Group ids must be unique.')
        names.add(key)
        ids.add(group.id)

    settings = _settings(data["settings"]) if "settings" in data else Settings()
    return Config(parsed, settings)


def _settings(data: Any) -> Settings:
    where = '"settings"'
    if not isinstance(data, dict):
        raise ConfigError(f"{where} must be an object: {{ ... }}.")
    fields: dict[str, Any] = {}
    if "theme" in data:
        fields["theme"] = _choice(data["theme"], Theme, "theme", where)
    if "show_header" in data:
        if not isinstance(data["show_header"], bool):
            raise ConfigError(f'{where}: "show_header" must be true or false.')
        fields["show_header"] = data["show_header"]
    return Settings(**fields)


def _group(data: Any, where: str) -> Group:
    if not isinstance(data, dict):
        raise ConfigError(f"{where} must be an object: {{ ... }}.")
    name = _text(data, "name", where)
    where = f'{where} ("{name}")'

    shortcuts = data.get("shortcuts")
    if not isinstance(shortcuts, list):
        raise ConfigError(f'{where}: "shortcuts" must be a list, even an empty one: [].')
    parsed = tuple(_shortcut(s, f"{where}, shortcuts[{i}]") for i, s in enumerate(shortcuts))

    fields: dict[str, Any] = {}
    if "id" in data:
        group_id = data["id"]
        if not isinstance(group_id, str) or not _GROUP_ID.fullmatch(group_id):
            raise ConfigError(
                f'{where}: "id" must be 1–64 lowercase letters, digits and dashes, '
                "starting with a letter or digit."
            )
        fields["id"] = group_id
    if "opacity" in data:
        opacity = data["opacity"]
        if not _is_number(opacity) or not MIN_OPACITY <= opacity <= 1.0:
            raise ConfigError(f'{where}: "opacity" must be a number from {MIN_OPACITY} to 1.0.')
        fields["opacity"] = float(opacity)
    if "style" in data:
        fields["style"] = _choice(data["style"], Style, "style", where)
    if "layout" in data:
        fields["layout"] = _choice(data["layout"], Layout, "layout", where)
    if "columns" in data:
        columns = data["columns"]
        if not _is_int(columns) or not 1 <= columns <= MAX_COLUMNS:
            raise ConfigError(f'{where}: "columns" must be a whole number from 1 to {MAX_COLUMNS}.')
        fields["columns"] = columns
    if "pin" in data:
        fields["pin"] = _pin(data["pin"], f'{where}, "pin"')
    return Group(name, parsed, **fields)


def _pin(data: Any, where: str) -> Pin:
    if not isinstance(data, dict):
        raise ConfigError(f"{where} must be an object: {{ ... }}.")
    fields: dict[str, Any] = {}
    if "kind" in data:
        fields["kind"] = _choice(data["kind"], PinKind, "kind", where)
    if "color" in data:
        color = data["color"]
        if not isinstance(color, str) or not palette.is_color(color):
            names = ", ".join(palette.PIN_COLORS)
            raise ConfigError(f'{where}: "color" must be one of {names}, or #RRGGBB.')
        fields["color"] = color
    if "letter" in data:
        letter = data["letter"]
        if not isinstance(letter, str) or not 1 <= len(letter.strip()) <= 2:
            raise ConfigError(f'{where}: "letter" must be one or two characters.')
        fields["letter"] = letter.strip()
    if "file" in data:
        fields["file"] = _text(data, "file", where)
    if fields.get("kind") is PinKind.FILE and "file" not in fields:
        raise ConfigError(f'{where}: "kind": "file" needs a "file" path.')
    return Pin(**fields)


def _shortcut(data: Any, where: str) -> Shortcut:
    if not isinstance(data, dict):
        raise ConfigError(f"{where} must be an object: {{ ... }}.")
    icon = _text(data, "icon", where) if "icon" in data else None
    return Shortcut(_text(data, "name", where), _text(data, "target", where), icon=icon)


def _choice(value: Any, enum: type[StrEnum], key: str, where: str) -> Any:
    try:
        return enum(value)
    except ValueError:
        options = ", ".join(f'"{e.value}"' for e in enum)
        raise ConfigError(f'{where}: "{key}" must be one of {options}.') from None


def _text(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f'{where}: "{key}" must be non-empty text.')
    return value.strip()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
