"""The settings window's live copy of config.json: edits, autosave, reloads."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from perch import config
from perch.editing import EditError
from perch.models import Config

log = logging.getLogger(__name__)

SAVE_DELAY_MS = 300
"""Saves wait this long after the last change, so dragging a slider writes once."""


class ConfigStore(QObject):
    """Holds the config being edited and keeps the file in step with it.

    * ``changed``: the config was edited or reloaded; widgets should refresh.
    * ``saved``: the file now matches the config.
    * ``problem(str)``: something the user should read (a refused edit, a
      file that couldn't be saved or reloaded).
    """

    changed = Signal()
    saved = Signal()
    problem = Signal(str)

    def __init__(self, path: Path, initial: Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self._config = initial
        self._on_disk = self._read_disk()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(SAVE_DELAY_MS)
        self._timer.timeout.connect(self.save_now)

    @property
    def config(self) -> Config:
        return self._config

    @property
    def save_pending(self) -> bool:
        return self._timer.isActive()

    def apply(self, edit: Callable[[Config], Config]) -> bool:
        """Run ``edit`` on the config and schedule a save. False if it was refused."""
        try:
            new = edit(self._config)
        except EditError as e:
            self.problem.emit(str(e))
            return False
        if new != self._config:
            self._config = new
            self.changed.emit()
            self._timer.start()
        return True

    def save_now(self) -> bool:
        self._timer.stop()
        try:
            config.save(self._config, self.path)
        except OSError as e:
            self.problem.emit(f"Couldn't save {self.path}: {e.strerror or e}")
            return False
        self._on_disk = self._read_disk()
        self.saved.emit()
        return True

    def changed_on_disk(self) -> bool:
        """Whether someone else (an editor, another Perch) changed the file since we last saw it."""
        return self._read_disk() != self._on_disk

    def reload(self) -> None:
        """Replace the config with the file's contents. Raises ConfigError if it's broken."""
        self._timer.stop()
        loaded = config.load(self.path)
        self._config = loaded
        self._on_disk = self._read_disk()
        self.changed.emit()

    def back_up_to(self, target: Path) -> None:
        if self.save_now():
            shutil.copy2(self.path, target)

    def restore_from(self, source: Path) -> Path:
        """Use ``source`` as the config. The current file is kept as config.json.bak,
        whose path is returned. Raises ConfigError (nothing changed) if ``source`` is broken."""
        restored = config.load(source)
        backup = self.path.with_name(self.path.name + ".bak")
        if self.path.exists():
            shutil.copy2(self.path, backup)
        self._config = restored
        self.save_now()
        self.changed.emit()
        log.info("Restored %s from %s (previous copy: %s)", self.path, source, backup)
        return backup

    def _read_disk(self) -> str | None:
        try:
            return self.path.read_text(encoding="utf-8-sig")
        except OSError:
            return None
