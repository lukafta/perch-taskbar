import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QToolButton, QWidget

from perch import win32
from perch.config import DEFAULT_CONFIG
from perch.models import Group, Layout, Shortcut, Style
from perch.ui import theme
from perch.ui.panel import GAP_FROM_TASKBAR, PerchPanel, _max_columns
from perch.ui.views import RowsView, TilesView

TASKBAR_HEIGHT = 48
GROUP = DEFAULT_CONFIG.groups[0]


def shortcuts(count):
    return tuple(Shortcut(f"App {i}", f"https://example.com/{i}") for i in range(count))


@pytest.fixture
def no_taskbar_query(monkeypatch):
    # The offscreen screen reserves no taskbar, so locate() falls back to
    # asking the shell. Answer for it instead of reading this machine's taskbar.
    monkeypatch.setattr(win32, "taskbar_position", lambda: (3, TASKBAR_HEIGHT))


@pytest.fixture
def make_panel(qapp, no_taskbar_query):
    made = []

    def make(group=GROUP, tokens=None):
        widget = PerchPanel(group, tokens)
        widget.seen = []
        widget.dismissed.connect(lambda: widget.seen.append("dismissed"))
        widget.shortcut_activated.connect(lambda s: widget.seen.append(s))
        made.append(widget)
        return widget

    yield make
    for widget in made:
        widget.hide()
        widget.deleteLater()


@pytest.fixture
def panel(make_panel):
    return make_panel()


def shown(panel):
    panel.popup()
    assert QTest.qWaitForWindowActive(panel), "panel never became the active window"
    return panel


def test_window_is_borderless_tool_window(panel):
    flags = panel.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.Tool
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_header_shows_the_group_name(panel):
    header = panel.findChild(QLabel, "header")
    assert header.text() == "Essentials"


def test_header_can_be_turned_off(qapp, no_taskbar_query):
    panel = PerchPanel(GROUP, show_header=False)
    assert panel.findChild(QLabel, "header") is None
    assert panel.findChild(QToolButton, "gear") is not None
    panel.deleteLater()


def test_gear_asks_for_settings_at_this_group(panel):
    requested = []
    panel.settings_requested.connect(requested.append)
    gear = panel.findChild(QToolButton, "gear")
    assert gear.accessibleName() == "Settings for Essentials"
    gear.click()
    assert requested == [GROUP.id]


def test_preview_panels_have_no_gear(qapp, no_taskbar_query):
    panel = PerchPanel(GROUP, settings_button=False)
    assert panel.findChild(QToolButton, "gear") is None
    panel.deleteLater()


def test_empty_group_says_so(make_panel):
    panel = make_panel(Group("Empty", ()))
    assert panel.buttons() == []
    assert "No shortcuts yet" in panel.findChild(QLabel, "empty").text()


def test_rows_style_has_one_button_per_shortcut_in_order(panel):
    assert isinstance(panel.view(), RowsView)
    assert [b.accessibleName() for b in panel.buttons()] == [s.name for s in GROUP.shortcuts]


def test_row_names_are_plain_text(make_panel):
    group = Group("G", (Shortcut("<b>Bluetooth</b> & devices", "ms-settings:bluetooth"),))
    (button,) = make_panel(group).buttons()
    label = button.text_label()
    assert label.textFormat() == Qt.TextFormat.PlainText
    assert label.text() == "<b>Bluetooth</b> & devices"


def test_tile_ampersand_is_shown_not_eaten(make_panel):
    group = Group("G", (Shortcut("A & B", "ms-settings:bluetooth"),), style=Style.TILES)
    (button,) = make_panel(group).buttons()
    assert isinstance(button, QToolButton)
    assert button.text() == "A && B"  # renders as a single "&"


def test_every_shortcut_gets_an_icon(panel):
    for button in panel.buttons():
        glyph = button.findChildren(QLabel)[0]
        assert not glyph.pixmap().isNull()


@pytest.mark.parametrize(
    ("layout", "count", "shape"),
    [
        (Layout.VERTICAL, 3, (3, 1)),
        (Layout.HORIZONTAL, 5, (1, 5)),
        (Layout.SQUARE, 9, (3, 3)),
        (Layout.GRID, 8, (2, 4)),
    ],
)
def test_tiles_follow_the_layout(make_panel, layout, count, shape):
    view = make_panel(Group("G", shortcuts(count), style=Style.TILES, layout=layout)).view()
    assert isinstance(view, TilesView)
    assert view.grid_shape() == shape


def test_rows_style_ignores_the_layout(make_panel):
    view = make_panel(Group("G", shortcuts(4), layout=Layout.HORIZONTAL)).view()
    assert isinstance(view, RowsView)


def test_wide_horizontal_row_wraps_to_fit_the_screen(make_panel):
    view = make_panel(Group("G", shortcuts(30), style=Style.TILES, layout=Layout.HORIZONTAL)).view()
    view.arrange(8)
    assert view.grid_shape() == (4, 8)


def test_max_columns_fits_the_work_area():
    from PySide6.QtCore import QRect

    # 1920 wide: minus 2x8 gap and 2x6 frame, tiles are 76 + 4 apart.
    assert _max_columns(QRect(0, 0, 1920, 1032)) == 23
    assert _max_columns(QRect(0, 0, 50, 1032)) == 1


def test_light_and_dark_themes_differ(make_panel):
    dark = make_panel(tokens=theme.DARK).styleSheet()
    light = make_panel(tokens=theme.LIGHT).styleSheet()
    assert theme.DARK.surface in dark and theme.LIGHT.surface in light


def test_popup_docks_above_the_taskbar(panel):
    shown(panel)
    screen = QGuiApplication.primaryScreen().geometry()
    taskbar_top = screen.bottom() + 1 - TASKBAR_HEIGHT
    assert taskbar_top - (panel.geometry().bottom() + 1) == GAP_FROM_TASKBAR
    assert screen.contains(panel.geometry())


def test_losing_focus_dismisses(panel, qapp):
    shown(panel)
    other = QWidget()
    other.show()
    other.activateWindow()
    assert QTest.qWaitForWindowActive(other)
    qapp.processEvents()
    assert panel.isHidden()
    assert panel.seen == ["dismissed"]
    other.close()


def test_escape_dismisses(panel):
    shown(panel)
    QTest.keyClick(panel, Qt.Key.Key_Escape)
    assert panel.isHidden()
    assert panel.seen == ["dismissed"]


@pytest.mark.parametrize("style", [Style.ROWS, Style.TILES])
def test_clicking_a_shortcut_reports_it_then_dismisses(make_panel, style):
    group = Group("G", GROUP.shortcuts, style=style)
    panel = shown(make_panel(group))
    QTest.mouseClick(panel.buttons()[1], Qt.MouseButton.LeftButton)
    assert panel.seen == [group.shortcuts[1], "dismissed"]
    assert panel.isHidden()


def test_dismiss_twice_emits_once(panel):
    shown(panel)
    panel.dismiss()
    panel.dismiss()
    assert panel.seen == ["dismissed"]
