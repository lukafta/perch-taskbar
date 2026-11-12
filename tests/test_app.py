"""The command line and the one-shot flow, run offscreen with launching faked."""

import json

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from perch import app, win32
from perch.launcher import LaunchError
from perch.ui.panel import PerchPanel


@pytest.fixture
def env(qapp, tmp_path, monkeypatch):
    """Config in a temp folder, errors recorded instead of shown, launches faked."""
    monkeypatch.setattr(win32, "taskbar_position", lambda: (3, 48))
    errors, launched = [], []
    monkeypatch.setattr(app, "_error", errors.append)
    monkeypatch.setattr(app, "_report_config_error", lambda path, msg: errors.append(msg))
    monkeypatch.setattr(app.launcher, "launch", launched.append)
    monkeypatch.setattr(app, "_desktop", lambda: tmp_path / "Desktop")
    # Never hang the test run if the panel doesn't close.
    QTimer.singleShot(5000, lambda: QApplication.exit(99))
    return {"config": tmp_path / "config.json", "errors": errors, "launched": launched, "tmp": tmp_path}


def click_after_popup(monkeypatch, label):
    """Make the next panel click the button called ``label`` once it's shown."""
    original = PerchPanel.popup

    def popup_then_click(self):
        original(self)
        button = next(b for b in self.buttons() if b.accessibleName() == label)
        QTimer.singleShot(0, lambda: QTest.mouseClick(button, Qt.MouseButton.LeftButton))

    monkeypatch.setattr(PerchPanel, "popup", popup_then_click)


def run(env, *args):
    return app.main(["--config", str(env["config"]), *args])


def test_first_run_creates_config_and_launches_the_clicked_shortcut(env, monkeypatch):
    click_after_popup(monkeypatch, "Calculator")
    assert run(env) == 0
    assert env["config"].exists()
    assert [s.name for s in env["launched"]] == ["Calculator"]
    assert env["errors"] == []


def test_group_option_picks_the_group(env, monkeypatch):
    click_after_popup(monkeypatch, "Sound")
    assert run(env, "--group", "SETTINGS") == 0
    assert [s.target for s in env["launched"]] == ["ms-settings:sound"]


def test_failed_launch_is_reported_and_exits_1(env, monkeypatch):
    def fail(shortcut):
        raise LaunchError(f"boom {shortcut.name}")

    monkeypatch.setattr(app.launcher, "launch", fail)
    click_after_popup(monkeypatch, "Notepad")
    assert run(env) == 1
    assert env["errors"] == ["boom Notepad"]


def test_unknown_group_lists_the_real_ones(env):
    assert run(env, "--group", "Nope") == 1
    assert 'no group named "Nope"' in env["errors"][0]
    assert "Essentials" in env["errors"][0] and "Settings" in env["errors"][0]


def test_broken_config_is_reported_and_left_alone(env):
    env["config"].write_text('{"groups": [}', encoding="utf-8")
    assert run(env) == 1
    assert env["errors"][0].startswith("Line 1, column")
    assert env["config"].read_text(encoding="utf-8") == '{"groups": [}'


def test_create_shortcut_writes_to_the_desktop_with_a_pin_icon(env):
    assert run(env, "--create-shortcut", "settings") == 0
    # Canonical group name, not the case typed on the command line.
    assert (env["tmp"] / "Desktop" / "Perch - Settings.lnk").exists()
    (ico,) = (env["tmp"] / "icons").glob("Perch.Group.settings-*.ico")
    assert ico.read_bytes()[:4] == b"\x00\x00\x01\x00"


def close_settings_soon(found):
    def close():
        from perch.ui.settings import SettingsWindow

        windows = [w for w in QApplication.topLevelWidgets() if isinstance(w, SettingsWindow) and w.isVisible()]
        found.extend(windows)
        for window in windows:
            window.close()

    QTimer.singleShot(200, close)


def test_settings_option_opens_the_window_at_the_group(env):
    found = []
    close_settings_soon(found)
    assert run(env, "--settings", "--group", "Settings") == 0
    assert found and found[0].group_page.name_edit.text() == "Settings"


def test_gear_opens_settings_and_keeps_perch_running(env, monkeypatch):
    original = PerchPanel.popup

    def popup_then_gear(self):
        original(self)
        QTimer.singleShot(0, lambda: self.settings_requested.emit(self._group_id))

    monkeypatch.setattr(PerchPanel, "popup", popup_then_gear)
    found = []
    close_settings_soon(found)
    assert run(env) == 0
    assert found and found[0].current_group_id() == "essentials-a74d251d"


def test_create_shortcut_records_ids_in_the_file(env):
    assert run(env, "--create-shortcut", "Essentials") == 0
    assert '"id": "essentials-a74d251d"' in env["config"].read_text(encoding="utf-8")


def test_create_shortcut_for_unknown_group_fails(env):
    assert run(env, "--create-shortcut", "Nope") == 1
    assert not (env["tmp"] / "Desktop").exists()


def test_config_option_round_trips_through_json(env):
    env["config"].write_text(
        json.dumps({"groups": [{"name": "Solo", "shortcuts": [{"name": "Go", "target": "go.exe"}]}]}),
        encoding="utf-8",
    )
    assert run(env, "--group", "Nope") == 1
    assert "Solo" in env["errors"][0]
