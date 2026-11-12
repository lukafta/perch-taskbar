"""Every dialog the settings window opens, in one place.

Pages call these instead of QFileDialog / QMessageBox directly, so tests can
replace them and run without anything modal appearing.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from perch.models import Shortcut

PROGRAM_FILTER = "Programs and shortcuts (*.exe *.lnk *.bat *.cmd *.url);;All files (*)"
IMAGE_FILTER = "Icons and images (*.ico *.png);;All files (*)"
ICON_FILTER = "Icons, images and programs (*.ico *.png *.exe);;All files (*)"
CONFIG_FILTER = "Perch config (*.json);;All files (*)"


def ask_files(parent: QWidget) -> list[Path]:
    paths, _ = QFileDialog.getOpenFileNames(parent, "Add shortcuts", "", PROGRAM_FILTER)
    return [Path(p) for p in paths]


def ask_folder(parent: QWidget) -> Path | None:
    path = QFileDialog.getExistingDirectory(parent, "Add a folder")
    return Path(path) if path else None


def ask_image(parent: QWidget) -> Path | None:
    path, _ = QFileDialog.getOpenFileName(parent, "Choose a pin image", "", IMAGE_FILTER)
    return Path(path) if path else None


def ask_color(parent: QWidget, initial: str) -> str | None:
    color = QColorDialog.getColor(QColor(initial), parent, "Pin colour")
    return color.name().upper() if color.isValid() else None


def ask_save_path(parent: QWidget, suggested: Path) -> Path | None:
    path, _ = QFileDialog.getSaveFileName(parent, "Back up your groups", str(suggested), CONFIG_FILTER)
    return Path(path) if path else None


def ask_open_path(parent: QWidget) -> Path | None:
    path, _ = QFileDialog.getOpenFileName(parent, "Restore groups from a file", "", CONFIG_FILTER)
    return Path(path) if path else None


def confirm(parent: QWidget, title: str, text: str, action: str) -> bool:
    box = QMessageBox(QMessageBox.Icon.Question, title, text, parent=parent)
    ok = box.addButton(action, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    box.exec()
    return box.clickedButton() is ok


def inform(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def ask_shortcut(parent: QWidget, shortcut: Shortcut | None = None, web: bool = False) -> Shortcut | None:
    """Edit an existing shortcut, or make a new one (``web`` for a link)."""
    dialog = ShortcutDialog(parent, shortcut, web)
    return dialog.result_shortcut() if dialog.exec() == QDialog.DialogCode.Accepted else None


class ShortcutDialog(QDialog):
    def __init__(self, parent: QWidget, shortcut: Shortcut | None, web: bool) -> None:
        super().__init__(parent)
        if shortcut is not None:
            self.setWindowTitle("Edit shortcut")
        else:
            self.setWindowTitle("Add a web link" if web else "Add a shortcut")
        self.setMinimumWidth(480)

        self.name = QLineEdit(shortcut.name if shortcut else "")
        self.target = QLineEdit(shortcut.target if shortcut else ("https://" if web else ""))
        self.icon = QLineEdit((shortcut.icon or "") if shortcut else "")
        self.icon.setPlaceholderText("Optional: the target's own icon is used otherwise")

        form = QFormLayout()
        form.addRow("&Name", self.name)
        form.addRow("&Opens" if not web else "&Address", self._with_browse(self.target, self._browse_target))
        form.addRow("&Icon", self._with_browse(self.icon, self._browse_icon))
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.hide()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def result_shortcut(self) -> Shortcut:
        icon = self.icon.text().strip() or None
        return Shortcut(self.name.text().strip(), self.target.text().strip(), icon=icon)

    def _accept(self) -> None:
        missing = [label for label, field in (("a name", self.name), ("what it opens", self.target)) if not field.text().strip()]
        if missing:
            self.error.setText(f"Give the shortcut {' and '.join(missing)}.")
            self.error.show()
            return
        self.accept()

    def _with_browse(self, field: QLineEdit, browse) -> QWidget:
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(field, 1)
        button = QPushButton("Browse…")
        button.clicked.connect(browse)
        line.addWidget(button)
        return row

    def _browse_target(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose what the shortcut opens", "", PROGRAM_FILTER)
        if path:
            self.target.setText(str(Path(path)))
            if not self.name.text().strip():
                self.name.setText(Path(path).stem)

    def _browse_icon(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose an icon", "", ICON_FILTER)
        if path:
            self.icon.setText(str(Path(path)))
