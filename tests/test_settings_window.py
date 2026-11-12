"""Perch Settings, driven through its widgets offscreen. Dialogs are faked."""

import json

import pytest

from perch import config, pinning
from perch.models import Config, Group, Layout, PinKind, Shortcut, Style, Theme
from perch.store import ConfigStore
from perch.ui import theme
from perch.ui.settings import SettingsWindow, dialogs
from perch.ui.settings.other_pages import SetupPaths

ESSENTIALS = Group("Essentials", (Shortcut("Notepad", "notepad.exe"), Shortcut("Calc", "calc.exe")))
WORK = Group("Work", ())


@pytest.fixture
def env(qapp, tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    config.save(Config((ESSENTIALS, WORK)), path)
    paths = SetupPaths(desktop=tmp_path / "Desktop", start_menu=tmp_path / "Start" / "Perch", taskbar_pins=tmp_path / "Pins")
    info: list[str] = []
    monkeypatch.setattr(dialogs, "inform", lambda parent, title, text: info.append(text))
    monkeypatch.setattr(dialogs, "confirm", lambda *args: True)
    windows = []

    def make(group=None):
        store = ConfigStore(path, config.load(path))
        window = SettingsWindow(store, group, setup_paths=paths)
        windows.append(window)
        return window

    yield {"make": make, "path": path, "paths": paths, "info": info, "tmp": tmp_path}
    for window in windows:
        window.store.save_now()
        window.deleteLater()
    theme.apply_color_scheme(Theme.SYSTEM)


def group_names(window):
    return [window.group_list.item(i).text() for i in range(window.group_list.count())]


def saved(env):
    return config.load(env["path"])


def test_opens_at_the_requested_group(env):
    window = env["make"]("work")
    assert group_names(window) == ["Essentials", "Work"]
    assert window.group_page.name_edit.text() == "Work"
    assert window.current_group_id() == WORK.id


def test_choosing_tiles_saves_and_enables_layouts(env):
    window = env["make"]()
    page = window.group_page
    assert not page.layout_buttons[Layout.GRID].isEnabled()
    page.style_buttons[Style.TILES].click()
    page.layout_buttons[Layout.GRID].click()
    page.columns.setValue(3)
    assert page.columns.isEnabled()
    window.store.save_now()
    group = saved(env).groups[0]
    assert (group.style, group.layout, group.columns) == (Style.TILES, Layout.GRID, 3)


def test_rename_keeps_the_id_and_updates_the_menu(env):
    window = env["make"]()
    page = window.group_page
    page.name_edit.setText("Daily")
    page.name_edit.editingFinished.emit()
    assert group_names(window) == ["Daily", "Work"]
    window.store.save_now()
    assert saved(env).groups[0].id == ESSENTIALS.id


def test_duplicate_name_is_refused_and_explained(env):
    window = env["make"]()
    page = window.group_page
    page.name_edit.setText("work")
    page.name_edit.editingFinished.emit()
    assert page.name_edit.text() == "Essentials"
    assert not window.banner.isHidden()
    assert "already a group" in window.banner_text.text()


def test_new_group_is_selected_and_empty(env):
    window = env["make"]()
    window.new_group()
    assert group_names(window) == ["Essentials", "Work", "New group"]
    assert window.group_page.name_edit.text() == "New group"
    assert window.group_page.shortcut_list.count() == 0


def test_delete_moves_to_another_group_and_last_cannot_go(env):
    window = env["make"]()
    window.group_page.delete_button.click()
    assert group_names(window) == ["Work"]
    assert window.group_page.name_edit.text() == "Work"
    assert not window.group_page.delete_button.isEnabled()


@pytest.mark.parametrize(
    ("shortcuts", "expected"),
    [(0, 'Delete "Work"?'), (1, 'Delete "Work" and its 1 shortcut?'), (2, 'Delete "Work" and its 2 shortcuts?')],
)
def test_delete_question_counts_shortcuts_properly(env, monkeypatch, shortcuts, expected):
    asked = []
    monkeypatch.setattr(dialogs, "confirm", lambda parent, title, text, action: asked.append(text) or False)
    window = env["make"]("Work")
    window.group_page.add_paths([env["tmp"]] * shortcuts)
    window.group_page.delete_button.click()
    assert asked[0].startswith(expected)
    assert group_names(window) == ["Essentials", "Work"]  # declined: nothing deleted


def test_adding_files_names_them_after_the_file(env):
    window = env["make"]("Work")
    tool = env["tmp"] / "mytool.exe"
    tool.write_text("")
    window.group_page.add_paths([tool])
    assert window.group_page.shortcut_list.count() == 1
    window.store.save_now()
    assert saved(env).groups[1].shortcuts == (Shortcut("Mytool", str(tool)),)


def test_edit_remove_and_reorder_shortcuts(env, monkeypatch):
    window = env["make"]()
    page = window.group_page
    monkeypatch.setattr(dialogs, "ask_shortcut", lambda parent, shortcut=None, web=False: Shortcut("Pad", "notepad.exe"))
    page.shortcut_list.setCurrentRow(0)
    page.edit_selected()
    page.shortcut_list.reordered.emit([1, 0])
    page.shortcut_list.setCurrentRow(1)
    page.remove_selected()
    window.store.save_now()
    assert saved(env).groups[0].shortcuts == (Shortcut("Calc", "calc.exe"),)


def test_web_link_is_added_from_the_dialog(env, monkeypatch):
    window = env["make"]("Work")
    monkeypatch.setattr(dialogs, "ask_shortcut", lambda parent, shortcut=None, web=False: Shortcut("Qt", "https://qt.io"))
    window.group_page.add_link_button.click()
    window.store.save_now()
    assert saved(env).groups[1].shortcuts == (Shortcut("Qt", "https://qt.io"),)


def test_pin_colour_letter_and_custom_colour(env, monkeypatch):
    window = env["make"]()
    page = window.group_page
    page.color_buttons["violet"].click()
    page.letter.setText("Ab")
    page.letter.editingFinished.emit()
    assert window.store.config.groups[0].pin.color == "violet"
    monkeypatch.setattr(dialogs, "ask_color", lambda parent, initial: "#40A0FF")
    page.custom_color.click()
    pin = window.store.config.groups[0].pin
    assert (pin.color, pin.letter) == ("#40A0FF", "Ab")
    assert page.custom_color.text() == "Custom (#40A0FF)…"
    assert not any(b.isChecked() for b in page.color_buttons.values())


def test_choosing_image_pin_asks_for_a_file_and_cancel_keeps_the_mark(env, monkeypatch):
    window = env["make"]()
    page = window.group_page
    monkeypatch.setattr(dialogs, "ask_image", lambda parent: None)
    page.kind_buttons[PinKind.FILE].click()
    assert window.store.config.groups[0].pin.kind is PinKind.MARK
    assert page.kind_buttons[PinKind.MARK].isChecked()
    monkeypatch.setattr(dialogs, "ask_image", lambda parent: env["tmp"] / "me.png")
    page.kind_buttons[PinKind.FILE].click()
    pin = window.store.config.groups[0].pin
    assert (pin.kind, pin.file) == (PinKind.FILE, str(env["tmp"] / "me.png"))
    assert not page.letter.isEnabled()


def test_dragging_groups_reorders_them(env):
    window = env["make"]()
    window.group_list.reordered.emit([WORK.id, ESSENTIALS.id])
    assert group_names(window) == ["Work", "Essentials"]


def test_settings_page_theme_and_header(env, monkeypatch):
    # The offscreen platform can't switch colour schemes, so record the request.
    applied = []
    monkeypatch.setattr(theme, "apply_color_scheme", applied.append)
    window = env["make"]()
    window.select_page("Settings")
    window.general_page.theme_buttons[Theme.DARK].click()
    window.general_page.show_header.setChecked(False)
    assert applied[-1] is Theme.DARK
    window.store.save_now()
    settings = saved(env).settings
    assert (settings.theme, settings.show_header) == (Theme.DARK, False)


def test_setup_page_shows_which_groups_are_pinned(env):
    window = env["make"]()
    window.setup_page._read_pins = lambda folder: {pinning.app_id(ESSENTIALS.id), "SomeOther.App"}
    window.select_page("Setup")
    window.setup_page.refresh()
    statuses = [label.text() for label in window.setup_page.pin_rows.findChildren(type(window.banner_text)) if label.text() in ("Pinned", "Not pinned")]
    assert statuses == ["Pinned", "Not pinned"]


def test_put_on_desktop_creates_the_shortcut_and_explains_pinning(env):
    pytest.importorskip("win32com")
    window = env["make"]()
    window.pin_group(WORK.id)
    assert (env["paths"].desktop / "Perch - Work.lnk").exists()
    assert "Pin to taskbar" in env["info"][0]


def test_start_menu_entry_can_be_added_and_removed(env):
    pytest.importorskip("win32com")
    window = env["make"]()
    window.select_page("Setup")
    window.setup_page.start_button.click()
    assert (env["paths"].start_menu / "Perch Settings.lnk").exists()
    assert window.setup_page.start_button.text() == "Remove from Start menu"
    window.setup_page.start_button.click()
    assert not env["paths"].start_menu.exists()


def test_backup_and_restore_from_the_config_page(env, monkeypatch):
    window = env["make"]()
    backup = env["tmp"] / "backup.json"
    monkeypatch.setattr(dialogs, "ask_save_path", lambda parent, suggested: backup)
    window.config_page.back_up()
    window.group_page.delete_button.click()
    monkeypatch.setattr(dialogs, "ask_open_path", lambda parent: backup)
    window.config_page.restore()
    assert group_names(window) == ["Essentials", "Work"]
    assert "Restored" in window.config_page.status.text()


def test_hand_edits_are_picked_up(env):
    window = env["make"]()
    data = json.loads(env["path"].read_text(encoding="utf-8"))
    data["groups"][1]["name"] = "Office"
    env["path"].write_text(json.dumps(data), encoding="utf-8")
    window.pick_up_hand_edits()
    assert group_names(window) == ["Essentials", "Office"]
    assert "outside Perch Settings" in window.banner_text.text()


def test_broken_hand_edit_is_reported_not_loaded(env):
    window = env["make"]()
    env["path"].write_text("{ broken", encoding="utf-8")
    window.pick_up_hand_edits()
    assert group_names(window) == ["Essentials", "Work"]
    assert "can't be read" in window.banner_text.text()


def test_closing_saves_and_reports(env):
    window = env["make"]()
    closed = []
    window.closed.connect(lambda: closed.append(True))
    window.group_page.opacity.setValue(50)
    window.close()
    assert closed == [True]
    assert saved(env).groups[0].opacity == 0.5
