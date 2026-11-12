import json
import re

import pytest

from perch import config
from perch.config import DEFAULT_CONFIG, ConfigError
from perch.models import Config, Group, Layout, Pin, PinKind, Settings, Shortcut, Style, Theme, default_group_id

NOTEPAD = {"name": "Notepad", "target": "notepad.exe"}


def write(tmp_path, data, encoding="utf-8"):
    path = tmp_path / "config.json"
    text = data if isinstance(data, str) else json.dumps(data)
    path.write_text(text, encoding=encoding)
    return path


def test_first_run_creates_the_file_with_sample_groups(tmp_path):
    path = tmp_path / "Perch" / "config.json"
    assert config.load_or_create(path) == DEFAULT_CONFIG
    assert config.load(path) == DEFAULT_CONFIG


def test_existing_file_is_used_and_left_untouched(tmp_path):
    path = write(tmp_path, {"groups": [{"name": "Mine", "shortcuts": [NOTEPAD]}]})
    before = path.read_text(encoding="utf-8")
    assert config.load_or_create(path).groups[0].name == "Mine"
    assert path.read_text(encoding="utf-8") == before


def test_broken_file_is_reported_not_replaced(tmp_path):
    path = write(tmp_path, "{ not json")
    with pytest.raises(ConfigError):
        config.load_or_create(path)
    assert path.read_text(encoding="utf-8") == "{ not json"


def test_save_then_load_round_trips(tmp_path):
    cfg = Config(
        (
            Group("Work", (Shortcut("Docs", r"%USERPROFILE%\Documents"),), opacity=0.8),
            Group("Café ☕", (Shortcut("Menu", "https://example.com"),)),
        )
    )
    path = tmp_path / "config.json"
    config.save(cfg, path)
    assert config.load(path) == cfg


def test_save_leaves_no_temporary_files(tmp_path):
    path = tmp_path / "config.json"
    config.save(DEFAULT_CONFIG, path)
    config.save(DEFAULT_CONFIG, path)
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]


def test_optional_fields_take_defaults(tmp_path):
    cfg = config.load(write(tmp_path, {"groups": [{"name": "A", "shortcuts": [NOTEPAD]}]}))
    assert cfg.groups[0].opacity == Group("x", ()).opacity


def test_byte_order_mark_is_accepted(tmp_path):
    path = write(tmp_path, {"groups": [{"name": "A", "shortcuts": [NOTEPAD]}]}, encoding="utf-8-sig")
    assert config.load(path).groups[0].name == "A"


def test_unknown_keys_work_as_comments(tmp_path):
    data = {"note": "hi", "groups": [{"name": "A", "note": "x", "shortcuts": [dict(NOTEPAD, note="y")]}]}
    assert config.load(write(tmp_path, data)).groups[0].shortcuts[0] == Shortcut("Notepad", "notepad.exe")


def test_group_lookup_ignores_case_and_defaults_to_first():
    assert DEFAULT_CONFIG.group(None) is DEFAULT_CONFIG.groups[0]
    assert DEFAULT_CONFIG.group("settings") is DEFAULT_CONFIG.groups[1]
    assert DEFAULT_CONFIG.group("nope") is None


def test_syntax_error_points_at_the_line(tmp_path):
    path = write(tmp_path, '{\n  "groups": [\n    {"name": "A",,}\n  ]\n}')
    with pytest.raises(ConfigError, match=r"^Line 3, column \d+: "):
        config.load(path)


def group(**overrides):
    return dict({"name": "A", "shortcuts": [NOTEPAD]}, **overrides)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "must hold a JSON object"),
        ({}, '"groups" must be a list with at least one group'),
        ({"groups": []}, '"groups" must be a list with at least one group'),
        ({"groups": ["A"]}, "groups[0] must be an object"),
        ({"groups": [{"shortcuts": [NOTEPAD]}]}, 'groups[0]: "name" must be non-empty text'),
        ({"groups": [group(name="  ")]}, 'groups[0]: "name" must be non-empty text'),
        ({"groups": [group(shortcuts="notepad.exe")]}, 'groups[0] ("A"): "shortcuts" must be a list'),
        (
            {"groups": [group(shortcuts=[{"name": "X"}])]},
            'groups[0] ("A"), shortcuts[0]: "target" must be non-empty text',
        ),
        ({"groups": [group(opacity=0)]}, '"opacity" must be a number from 0.1 to 1.0'),
        ({"groups": [group(opacity=1.5)]}, '"opacity" must be a number'),
        ({"groups": [group(opacity=True)]}, '"opacity" must be a number'),
        ({"groups": [group(opacity="0.5")]}, '"opacity" must be a number'),
        ({"groups": [group(), group(name="a")]}, 'Two groups are named "a"'),
        ({"version": 2, "groups": [group()]}, "version 2, from a newer Perch"),
        ({"version": "1", "groups": [group()]}, '"version" must be a whole number'),
    ],
)
def test_invalid_files_say_where_and_why(tmp_path, data, message):
    with pytest.raises(ConfigError, match=re.escape(message)):
        config.load(write(tmp_path, data))


def test_look_and_pin_fields_load(tmp_path):
    data = {
        "groups": [
            group(
                style="tiles",
                layout="grid",
                columns=6,
                pin={"kind": "mark", "color": "#40A0FF", "letter": "Ab"},
                shortcuts=[dict(NOTEPAD, icon="C:\\icons\\pad.ico")],
            )
        ]
    }
    loaded = config.load(write(tmp_path, data)).groups[0]
    assert (loaded.style, loaded.layout, loaded.columns) == (Style.TILES, Layout.GRID, 6)
    assert loaded.pin == Pin(kind=PinKind.MARK, color="#40A0FF", letter="Ab")
    assert loaded.shortcuts[0].icon == "C:\\icons\\pad.ico"


def test_minimal_groups_get_the_default_look(tmp_path):
    loaded = config.load(write(tmp_path, {"groups": [group()]})).groups[0]
    assert (loaded.style, loaded.layout, loaded.pin) == (Style.ROWS, Layout.VERTICAL, Pin())
    assert loaded.pin_letter == "A"


def test_full_round_trip_keeps_every_field(tmp_path):
    cfg = Config(
        (
            Group(
                "Work",
                (Shortcut("Docs", "docs.exe", icon="docs.ico"),),
                style=Style.TILES,
                layout=Layout.SQUARE,
                columns=3,
                pin=Pin(kind=PinKind.FILE, file="C:\\work.png", letter="W"),
            ),
        )
    )
    config.save(cfg, tmp_path / "c.json")
    assert config.load(tmp_path / "c.json") == cfg


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"style": "command"}, '"style" must be one of "rows", "tiles"'),
        ({"layout": "circle"}, '"layout" must be one of "vertical", "horizontal", "square", "grid"'),
        ({"columns": 0}, '"columns" must be a whole number from 1 to 12'),
        ({"columns": 2.5}, '"columns" must be a whole number'),
        ({"pin": "amber"}, '"pin" must be an object'),
        ({"pin": {"color": "red"}}, '"color" must be one of amber, blue, violet, green, pink, or #RRGGBB'),
        ({"pin": {"letter": "ABC"}}, '"letter" must be one or two characters'),
        ({"pin": {"kind": "file"}}, '"kind": "file" needs a "file" path'),
        ({"pin": {"kind": "photo"}}, '"kind" must be one of "mark", "collage", "file"'),
    ],
)
def test_look_and_pin_mistakes_are_explained(tmp_path, fields, message):
    with pytest.raises(ConfigError, match=re.escape(message)):
        config.load(write(tmp_path, {"groups": [group(**fields)]}))


def test_ids_and_settings_round_trip(tmp_path):
    cfg = Config(
        (Group("Work", (), id="work-1"), Group("Home", (Shortcut("A", "a.exe"),))),
        Settings(theme=Theme.DARK, show_header=False),
    )
    config.save(cfg, tmp_path / "c.json")
    loaded = config.load(tmp_path / "c.json")
    assert loaded == cfg
    assert loaded.groups[1].id == default_group_id("Home")


def test_files_without_ids_get_the_default_id(tmp_path):
    loaded = config.load(write(tmp_path, {"groups": [group(name="Essentials")]}))
    assert loaded.groups[0].id == "essentials-a74d251d"
    assert loaded.settings == Settings()


def test_group_lookup_by_id_or_name(tmp_path):
    loaded = config.load(write(tmp_path, {"groups": [group(name="Work", id="w-1"), group(name="w-1")]}))
    assert loaded.group("w-1").name == "Work"  # an id match wins over a name match
    assert loaded.group("WORK").id == "w-1"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"groups": [group(id="Has Spaces")]}, '"id" must be 1–64 lowercase letters'),
        ({"groups": [group(id="x"), group(name="B", id="x")]}, 'Two groups have the id "x"'),
        ({"settings": [], "groups": [group()]}, '"settings" must be an object'),
        ({"settings": {"theme": "blue"}, "groups": [group()]}, '"theme" must be one of "system", "light", "dark"'),
        ({"settings": {"show_header": "yes"}, "groups": [group()]}, '"show_header" must be true or false'),
    ],
)
def test_id_and_settings_mistakes_are_explained(tmp_path, data, message):
    with pytest.raises(ConfigError, match=re.escape(message)):
        config.load(write(tmp_path, data))


def test_empty_groups_are_allowed(tmp_path):
    assert config.load(write(tmp_path, {"groups": [group(shortcuts=[])]})).groups[0].shortcuts == ()
