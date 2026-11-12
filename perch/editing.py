"""The changes the settings window makes to a Config.

Pure functions: each takes a Config and returns a new one, or raises
EditError with a message written for the user. No Qt, so it's all unit-tested
without a window.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from perch.models import Config, Group, Shortcut, default_group_id


class EditError(Exception):
    """A change that can't be made. The message is shown to the user."""


# -- groups ----------------------------------------------------------------


def find(config: Config, group_id: str) -> Group:
    for group in config.groups:
        if group.id == group_id:
            return group
    raise EditError("That group doesn't exist any more.")


def unique_name(config: Config, base: str = "New group") -> str:
    taken = {g.name.casefold() for g in config.groups}
    if base.casefold() not in taken:
        return base
    number = 2
    while f"{base} {number}".casefold() in taken:
        number += 1
    return f"{base} {number}"


def check_name(config: Config, name: str, group_id: str | None = None) -> str:
    """``name`` tidied, or EditError if it's empty or another group has it."""
    name = name.strip()
    if not name:
        raise EditError("A group needs a name.")
    for group in config.groups:
        if group.id != group_id and group.name.casefold() == name.casefold():
            raise EditError(f'There\'s already a group called "{group.name}".')
    return name


def add_group(config: Config, name: str | None = None) -> tuple[Config, Group]:
    """Append an empty group. Returns the new config and the group."""
    name = check_name(config, name or unique_name(config))
    taken = {g.id for g in config.groups}
    base = default_group_id(name)
    group_id, number = base, 2
    while group_id in taken:  # an earlier group renamed away from this name keeps its id
        group_id = f"{base}-{number}"
        number += 1
    group = Group(name, (), id=group_id)
    return replace(config, groups=config.groups + (group,)), group


def rename_group(config: Config, group_id: str, name: str) -> Config:
    name = check_name(config, name, group_id)
    return _with_group(config, replace(find(config, group_id), name=name))


def delete_group(config: Config, group_id: str) -> Config:
    find(config, group_id)
    if len(config.groups) == 1:
        raise EditError("Perch needs at least one group.")
    return replace(config, groups=tuple(g for g in config.groups if g.id != group_id))


def reorder_groups(config: Config, group_ids: Sequence[str]) -> Config:
    """Put the groups in the order of ``group_ids`` (the first opens by default)."""
    by_id = {g.id: g for g in config.groups}
    if sorted(group_ids) != sorted(by_id):
        raise EditError("The group list changed while you were moving it. Try again.")
    return replace(config, groups=tuple(by_id[i] for i in group_ids))


def update_group(config: Config, group_id: str, **changes: Any) -> Config:
    """Change a group's look: style, layout, columns, opacity."""
    return _with_group(config, replace(find(config, group_id), **changes))


def update_pin(config: Config, group_id: str, **changes: Any) -> Config:
    group = find(config, group_id)
    return _with_group(config, replace(group, pin=replace(group.pin, **changes)))


# -- shortcuts -------------------------------------------------------------


def add_shortcuts(config: Config, group_id: str, shortcuts: Sequence[Shortcut]) -> Config:
    group = find(config, group_id)
    return _with_group(config, replace(group, shortcuts=group.shortcuts + tuple(shortcuts)))


def replace_shortcut(config: Config, group_id: str, index: int, shortcut: Shortcut) -> Config:
    group = find(config, group_id)
    items = list(group.shortcuts)
    items[_index(items, index)] = shortcut
    return _with_group(config, replace(group, shortcuts=tuple(items)))


def remove_shortcut(config: Config, group_id: str, index: int) -> Config:
    group = find(config, group_id)
    items = list(group.shortcuts)
    del items[_index(items, index)]
    return _with_group(config, replace(group, shortcuts=tuple(items)))


def reorder_shortcuts(config: Config, group_id: str, order: Sequence[int]) -> Config:
    """``order`` lists the current indexes in their new order."""
    group = find(config, group_id)
    if sorted(order) != list(range(len(group.shortcuts))):
        raise EditError("The shortcut list changed while you were moving it. Try again.")
    return _with_group(config, replace(group, shortcuts=tuple(group.shortcuts[i] for i in order)))


def shortcut_for_path(path: Path) -> Shortcut:
    """A shortcut for a file or folder dropped or picked in the settings window,
    named after it: "notepad.exe" becomes "Notepad", "Games.lnk" stays "Games"."""
    name = path.name if path.is_dir() else path.stem
    name = name or str(path)  # a drive root like C:\ has no name
    if name.islower():
        name = name[0].upper() + name[1:]
    return Shortcut(name, str(path))


# -- app-wide settings -----------------------------------------------------


def update_settings(config: Config, **changes: Any) -> Config:
    return replace(config, settings=replace(config.settings, **changes))


# -- helpers ---------------------------------------------------------------


def _with_group(config: Config, group: Group) -> Config:
    return replace(config, groups=tuple(group if g.id == group.id else g for g in config.groups))


def _index(items: list, index: int) -> int:
    if not 0 <= index < len(items):
        raise EditError("That shortcut doesn't exist any more.")
    return index
