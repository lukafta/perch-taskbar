"""The floating panel that pops up from the taskbar."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QKeyEvent, QScreen
from PySide6.QtWidgets import (
    QAbstractButton,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from perch import icons, taskbar, win32
from perch.models import Group, Shortcut
from perch.ui import theme, views

GAP_FROM_TASKBAR = 8
"""Logical pixels between the taskbar and the panel."""

FRAME_PADDING = 5
"""Logical pixels between the panel's edge and its contents."""

FOREGROUND_RETRY_MS = 150
"""How long to give Windows to activate the panel before forcing it."""


class PerchPanel(QWidget):
    """Borderless panel that docks to the taskbar and hides when it loses focus.

    The panel never quits the app or launches anything itself. It reports what
    happened through signals and the owner decides:

    * ``shortcut_activated(Shortcut)``: the user picked a shortcut.
    * ``dismissed()``: the panel hid itself (focus moved elsewhere, Esc, or a
      shortcut was picked).
    * ``settings_requested(group_id)``: the gear button was clicked.
    """

    shortcut_activated = Signal(Shortcut)
    dismissed = Signal()
    settings_requested = Signal(str)

    def __init__(
        self,
        group: Group,
        tokens: theme.Tokens | None = None,
        show_header: bool = True,
        settings_button: bool = True,
    ) -> None:
        """``tokens`` picks light or dark; by default it follows the app's colour scheme.
        ``settings_button`` adds a gear that opens Perch Settings at this group."""
        self._group_id = group.id
        tokens = tokens or system_tokens()
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool  # no taskbar button and no Alt+Tab entry
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        # Transparent top-level window: only the rounded frame below is painted.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(group.name)
        self.setWindowOpacity(group.opacity)
        self.setStyleSheet(theme.stylesheet(tokens))
        # Hold keyboard focus on the panel itself rather than the first button,
        # so nothing looks pre-selected until the user presses Tab.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        frame = QFrame(self)
        frame.setObjectName("panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        body = QVBoxLayout(frame)
        body.setContentsMargins(FRAME_PADDING, FRAME_PADDING, FRAME_PADDING, FRAME_PADDING)
        body.setSpacing(2)
        if show_header or settings_button:
            top = QHBoxLayout()
            top.setContentsMargins(0, 0, 0, 0)
            if show_header:
                header = QLabel(group.name)
                header.setObjectName("header")
                header.setTextFormat(Qt.TextFormat.PlainText)
                top.addWidget(header, 1)
            else:
                top.addStretch(1)
            if settings_button:
                gear = QToolButton()
                gear.setObjectName("gear")
                gear.setIcon(icons.gear_icon(tokens.muted))
                gear.setIconSize(QSize(16, 16))
                gear.setFixedSize(QSize(30, 30))
                gear.setAccessibleName(f"Settings for {group.name}")
                gear.setToolTip("Perch Settings")
                gear.clicked.connect(lambda _checked=False: self.settings_requested.emit(self._group_id))
                top.addWidget(gear)
            body.addLayout(top)

        provider = QFileIconProvider()
        shortcut_icons = [icons.shortcut_icon(s, provider) for s in group.shortcuts]
        self._view = views.build_view(group, shortcut_icons, _screen_under_cursor().devicePixelRatio())
        self._view.activated.connect(self._activate)
        body.addWidget(self._view)
        if not group.shortcuts:
            empty = QLabel("No shortcuts yet. Add some in Perch Settings.")
            empty.setObjectName("empty")
            body.addWidget(empty)

    def view(self) -> views.GroupView:
        return self._view

    def buttons(self) -> list[QAbstractButton]:
        """One button per shortcut, in the group's order."""
        return self._view.buttons()

    def popup(self) -> None:
        """Show against the taskbar, centred on the mouse pointer, and take focus."""
        cursor = QCursor.pos()
        screen = _screen_under_cursor()
        edge, work_area = taskbar.locate(screen)

        # Size for the target monitor's DPI, and wrap tiles that wouldn't fit across it.
        self.setScreen(screen)
        self._view.arrange(_max_columns(work_area))
        self.adjustSize()
        self.move(taskbar.panel_position(self.size(), work_area, edge, cursor, GAP_FROM_TASKBAR))

        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        QTimer.singleShot(FOREGROUND_RETRY_MS, self._ensure_foreground)

    def dismiss(self) -> None:
        """Hide the panel and emit ``dismissed``. Safe to call more than once."""
        if self.isHidden():
            return
        self.hide()
        self.dismissed.emit()

    # -- Qt event handlers -------------------------------------------------

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        # Clicking anywhere outside the panel (another window, the desktop,
        # the taskbar) moves activation away from us.
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.dismiss()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
        else:
            super().keyPressEvent(event)

    # -- internals ---------------------------------------------------------

    def _activate(self, shortcut: Shortcut) -> None:
        self.shortcut_activated.emit(shortcut)
        self.dismiss()

    def _ensure_foreground(self) -> None:
        # Dismiss-on-focus-loss only fires if the panel was active to begin
        # with. Windows' focus-stealing guard can turn down activateWindow()
        # (it flashes the taskbar instead), which would leave the panel stuck
        # open, so fall back to the Win32 workaround.
        if (
            self.isVisible()
            and not self.isActiveWindow()
            and QGuiApplication.platformName() == "windows"
        ):
            win32.force_foreground(int(self.winId()))


def system_tokens() -> theme.Tokens:
    """Light or dark, following the Windows app mode (dark if Windows doesn't say)."""
    scheme = QGuiApplication.styleHints().colorScheme()
    return theme.LIGHT if scheme == Qt.ColorScheme.Light else theme.DARK


def _screen_under_cursor() -> QScreen:
    return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()


def _max_columns(work_area: QRect) -> int:
    """How many tiles fit across ``work_area`` with the panel's gaps and padding."""
    chrome = 2 * GAP_FROM_TASKBAR + 2 * (FRAME_PADDING + 1)
    step = views.TILE_SIZE.width() + views.TILE_SPACING
    return max(1, (work_area.width() - chrome + views.TILE_SPACING) // step)
