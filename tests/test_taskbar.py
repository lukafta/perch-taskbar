import pytest
from PySide6.QtCore import QPoint, QRect, QSize

from perch.taskbar import Edge, detect_edge, panel_position, reserve

SCREEN = QRect(0, 0, 1920, 1080)
PANEL = QSize(200, 150)
GAP = 8


@pytest.mark.parametrize(
    ("available", "edge"),
    [
        (QRect(0, 0, 1920, 1032), Edge.BOTTOM),
        (QRect(0, 48, 1920, 1032), Edge.TOP),
        (QRect(62, 0, 1858, 1080), Edge.LEFT),
        (QRect(0, 0, 1858, 1080), Edge.RIGHT),
        (QRect(0, 0, 1920, 1080), None),  # auto-hide: nothing reserved
    ],
)
def test_detect_edge(available, edge):
    assert detect_edge(SCREEN, available) is edge


def test_detect_edge_on_secondary_monitor_left_of_primary():
    screen = QRect(-2560, 0, 2560, 1440)
    assert detect_edge(screen, QRect(-2560, 0, 2560, 1392)) is Edge.BOTTOM


@pytest.mark.parametrize(
    ("edge", "expected"),
    [
        (Edge.BOTTOM, QRect(0, 0, 1920, 1032)),
        (Edge.TOP, QRect(0, 48, 1920, 1032)),
        (Edge.LEFT, QRect(48, 0, 1872, 1080)),
        (Edge.RIGHT, QRect(0, 0, 1872, 1080)),
    ],
)
def test_reserve(edge, expected):
    assert reserve(SCREEN, edge, 48) == expected


def test_bottom_taskbar_panel_sits_above_it_centred_on_pointer():
    work = QRect(0, 0, 1920, 1032)
    pos = panel_position(PANEL, work, Edge.BOTTOM, QPoint(960, 1060), GAP)
    placed = QRect(pos, PANEL)
    assert placed.center().x() in (959, 960)
    # Exactly GAP rows of clear space between the panel and the taskbar.
    assert work.bottom() - placed.bottom() == GAP


def test_panel_is_kept_inside_the_left_end():
    work = QRect(0, 0, 1920, 1032)
    pos = panel_position(PANEL, work, Edge.BOTTOM, QPoint(10, 1060), GAP)
    assert pos.x() == GAP


def test_panel_is_kept_inside_the_right_end():
    work = QRect(0, 0, 1920, 1032)
    placed = QRect(panel_position(PANEL, work, Edge.BOTTOM, QPoint(1915, 1060), GAP), PANEL)
    assert work.right() - placed.right() == GAP


def test_top_taskbar_panel_hangs_below_it():
    work = QRect(0, 48, 1920, 1032)
    pos = panel_position(PANEL, work, Edge.TOP, QPoint(500, 20), GAP)
    assert pos.y() == 48 + GAP


@pytest.mark.parametrize(("edge", "x"), [(Edge.LEFT, 62 + GAP), (Edge.RIGHT, 1858 - GAP - 200)])
def test_vertical_taskbar_panel_sits_beside_it_centred_on_pointer(edge, x):
    work = QRect(62, 0, 1858, 1080) if edge is Edge.LEFT else QRect(0, 0, 1858, 1080)
    pos = panel_position(PANEL, work, edge, QPoint(30, 600), GAP)
    assert pos == QPoint(x, 600 - 75)


def test_panel_larger_than_work_area_pins_to_start():
    work = QRect(0, 0, 150, 1032)
    pos = panel_position(PANEL, work, Edge.BOTTOM, QPoint(75, 1060), GAP)
    assert pos.x() == GAP
