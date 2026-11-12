"""Opening a shortcut's target the way Explorer would."""

from __future__ import annotations

import os

from perch.models import Shortcut


class LaunchError(Exception):
    """A shortcut's target couldn't be opened. The message is written for the user."""


def launch(shortcut: Shortcut) -> None:
    """Open the shortcut's target: an .exe, .lnk, folder, document or URL.

    ``%VARIABLES%`` and a leading ``~`` are expanded, so a config can say
    ``%USERPROFILE%\\Documents`` and work for any user.
    """
    target = os.path.expanduser(os.path.expandvars(shortcut.target))
    try:
        os.startfile(target)
    except OSError as e:
        raise LaunchError(f'Couldn\'t open "{shortcut.name}" ({target}): {e.strerror or e}') from e
