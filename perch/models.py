"""Plain data describing what the panel shows.

These are the types the config file is read into, so they stay free of any Qt
or Win32 dependency. Every field added after the first release has a default,
so older config files keep loading.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum


def default_group_id(name: str) -> str:
    """The id a group gets when it doesn't have one: a slug of the name plus a
    short hash. Pins made before ids existed used exactly this, so they keep
    working."""
    folded = name.casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")[:48] or "group"
    digest = hashlib.sha1(folded.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


class Style(StrEnum):
    """How a group's shortcuts are drawn."""

    ROWS = "rows"
    """Icon and name on each line, in one vertical list."""
    TILES = "tiles"
    """Large icon with the name underneath, arranged by the group's Layout."""


class Layout(StrEnum):
    """How tiles are arranged. Only Style.TILES uses it."""

    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    SQUARE = "square"
    GRID = "grid"


class PinKind(StrEnum):
    """What a group's taskbar pin looks like."""

    MARK = "mark"
    """The Perch mark in the group's colour, with a letter."""
    COLLAGE = "collage"
    """The group's first four app icons."""
    FILE = "file"
    """An .ico or .png the user chose."""


@dataclass(frozen=True)
class Pin:
    kind: PinKind = PinKind.MARK
    color: str = "amber"
    """A name from palette.PIN_COLORS, or #RRGGBB."""
    letter: str | None = None
    """One or two characters; None uses the group name's first letter."""
    file: str | None = None
    """Image used when kind is FILE."""


@dataclass(frozen=True)
class Shortcut:
    """One launchable entry in a group."""

    name: str
    target: str
    """Executable, .lnk, folder, document or URL. %VARIABLES% and ~ are expanded."""
    icon: str | None = None
    """An .ico, .png or .exe to take the icon from instead of the target."""


@dataclass(frozen=True)
class Group:
    """A named set of shortcuts shown together in one panel."""

    name: str
    shortcuts: tuple[Shortcut, ...]
    opacity: float = 0.97
    """Whole-window opacity, 0.1 (barely visible) to 1.0 (solid)."""
    style: Style = Style.ROWS
    layout: Layout = Layout.VERTICAL
    """Kept when the style is ROWS, so switching back to TILES restores it."""
    columns: int = 4
    """Columns for Layout.GRID."""
    pin: Pin = Pin()
    id: str = ""
    """Never changes once set, so renaming a group doesn't break its taskbar pin.
    Left empty, it's derived from the name."""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", default_group_id(self.name))

    @property
    def pin_letter(self) -> str:
        """The letter on the pin: the chosen one, else the name's first letter or digit."""
        if self.pin.letter:
            return self.pin.letter
        return next((c.upper() for c in self.name if c.isalnum()), "")


class Theme(StrEnum):
    SYSTEM = "system"
    """Follow the Windows app mode."""
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True)
class Settings:
    """App-wide options."""

    theme: Theme = Theme.SYSTEM
    show_header: bool = True
    """Show the group's name at the top of the panel."""


@dataclass(frozen=True)
class Config:
    """Everything the user has set up."""

    groups: tuple[Group, ...]
    settings: Settings = Settings()

    def group(self, key: str | None) -> Group | None:
        """The group whose id is ``key``, else the one named ``key`` (any case);
        the first group if ``key`` is None; None if there's no match."""
        if key is None:
            return self.groups[0] if self.groups else None
        by_id = next((g for g in self.groups if g.id == key), None)
        if by_id is not None:
            return by_id
        wanted = key.casefold()
        return next((g for g in self.groups if g.name.casefold() == wanted), None)
