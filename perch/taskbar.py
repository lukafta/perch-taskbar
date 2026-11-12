"""Where the taskbar is, and where the panel goes relative to it.

The geometry functions are pure (QtCore value types in, value types out) so
they're unit-tested without a display. ``locate`` is the only function that
reads live screen state.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QScreen

from perch import win32


class Edge(Enum):
    """Screen edge the taskbar is docked to. Values match Win32's ABE_* constants."""

    LEFT = 0
    TOP = 1
    RIGHT = 2
    BOTTOM = 3


def detect_edge(screen: QRect, available: QRect) -> Edge | None:
    """The edge the taskbar is on, judged by the strip it removes from the work area.

    Returns None when nothing is reserved: an auto-hide taskbar, or a monitor
    that isn't showing one.
    """
    if available.bottom() < screen.bottom():
        return Edge.BOTTOM
    if available.top() > screen.top():
        return Edge.TOP
    if available.left() > screen.left():
        return Edge.LEFT
    if available.right() < screen.right():
        return Edge.RIGHT
    return None


def reserve(area: QRect, edge: Edge, thickness: int) -> QRect:
    """``area`` with a strip ``thickness`` deep removed along ``edge``."""
    match edge:
        case Edge.BOTTOM:
            return area.adjusted(0, 0, 0, -thickness)
        case Edge.TOP:
            return area.adjusted(0, thickness, 0, 0)
        case Edge.LEFT:
            return area.adjusted(thickness, 0, 0, 0)
        case Edge.RIGHT:
            return area.adjusted(0, 0, -thickness, 0)


def panel_position(size: QSize, work_area: QRect, edge: Edge, anchor: QPoint, gap: int) -> QPoint:
    """Top-left corner for a panel of ``size`` docked against the taskbar.

    The panel sits ``gap`` px off the taskbar, is centred on ``anchor`` (the
    mouse pointer, i.e. the taskbar button that launched us) along the
    taskbar's length, and is kept ``gap`` px inside ``work_area`` at the ends.
    """
    if edge in (Edge.BOTTOM, Edge.TOP):
        x = _clamp(
            anchor.x() - size.width() // 2,
            work_area.left() + gap,
            work_area.right() + 1 - gap - size.width(),
        )
        if edge is Edge.BOTTOM:
            y = work_area.bottom() + 1 - gap - size.height()
        else:
            y = work_area.top() + gap
    else:
        y = _clamp(
            anchor.y() - size.height() // 2,
            work_area.top() + gap,
            work_area.bottom() + 1 - gap - size.height(),
        )
        if edge is Edge.RIGHT:
            x = work_area.right() + 1 - gap - size.width()
        else:
            x = work_area.left() + gap
    return QPoint(x, y)


def locate(screen: QScreen) -> tuple[Edge, QRect]:
    """The taskbar's edge on ``screen`` and the area the panel may occupy."""
    available = screen.availableGeometry()
    edge = detect_edge(screen.geometry(), available)
    if edge is not None:
        return edge, available

    # Nothing reserved, most likely because the taskbar auto-hides. It slides
    # back in over this spot when the user clicks it, so leave room for it.
    shell = win32.taskbar_position()
    if shell is None:
        return Edge.BOTTOM, available
    edge_value, thickness_px = shell
    edge = Edge(edge_value)
    thickness = round(thickness_px / screen.devicePixelRatio())
    return edge, reserve(available, edge, thickness)


def _clamp(value: int, low: int, high: int) -> int:
    # When the panel is larger than the space, pin it to the start (low) edge.
    return max(low, min(value, high))
