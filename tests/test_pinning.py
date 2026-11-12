import pytest

from perch import pinning
from perch.models import Group, default_group_id
from perch.pinning import app_id, create_group_shortcut, create_settings_shortcut, pinned_app_ids, read_app_id

win32com = pytest.importorskip("win32com", reason="needs pywin32 (Windows)")


def read_shortcut(path):
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
    )
    link.QueryInterface(pythoncom.IID_IPersistFile).Load(str(path))
    store = link.QueryInterface(propsys.IID_IPropertyStore)
    return {
        "target": link.GetPath(0)[0],
        "args": link.GetArguments(),
        "cwd": link.GetWorkingDirectory(),
        "app_id": store.GetValue(pscon.PKEY_AppUserModel_ID).GetValue(),
        "icon": link.GetIconLocation()[0],
    }


def test_default_ids_are_stable_and_ignore_case():
    assert default_group_id("Work Stuff") == default_group_id("work stuff")
    assert default_group_id("Work Stuff").startswith("work-stuff-")


def test_default_ids_keep_punctuation_variants_apart():
    assert default_group_id("A/B") != default_group_id("A-B")


def test_app_ids_are_valid_for_windows():
    for name in ["Essentials", "Café ☕", "x" * 300, "!!!"]:
        value = app_id(default_group_id(name))
        assert " " not in value and len(value) <= 128


def test_default_app_id_never_changes():
    # A group with no stored id gets one from its name. Existing pins rely on it.
    assert app_id(Group("Essentials", ()).id) == "Perch.Group.essentials-a74d251d"


def test_group_shortcut_opens_the_group_by_id(tmp_path):
    group = Group("Work Stuff", (), id="work-1")
    path = create_group_shortcut(group.id, group.name, tmp_path)
    assert path.name == "Perch - Work Stuff.lnk"
    link = read_shortcut(path)
    assert link["target"].lower().endswith("pythonw.exe")
    assert link["args"] == "-m perch --group work-1"
    assert link["cwd"] == str(pinning.PROJECT_ROOT)
    assert link["app_id"] == "Perch.Group.work-1"


def test_shortcut_carries_a_custom_config_path(tmp_path):
    custom = tmp_path / "my config.json"
    link = read_shortcut(create_group_shortcut("a-1", "A", tmp_path, custom))
    assert link["args"] == f'-m perch --group a-1 --config "{custom}"'


def test_shortcut_points_at_its_pin_icon(tmp_path):
    ico = tmp_path / "pin.ico"
    ico.write_bytes(b"\x00\x00\x01\x00\x00\x00")
    link = read_shortcut(create_group_shortcut("a-1", "A", tmp_path, icon=ico))
    assert link["icon"] == str(ico)


def test_settings_shortcut(tmp_path):
    path = create_settings_shortcut(tmp_path)
    assert path.name == "Perch Settings.lnk"
    link = read_shortcut(path)
    assert link["args"] == "-m perch --settings"
    assert link["app_id"] == pinning.SETTINGS_APP_ID


def test_pinned_app_ids_reads_every_shortcut(tmp_path):
    create_group_shortcut("a-1", "A", tmp_path)
    create_group_shortcut("b-2", "B", tmp_path)
    (tmp_path / "not a shortcut.lnk").write_bytes(b"junk")
    assert pinned_app_ids(tmp_path) == {"Perch.Group.a-1", "Perch.Group.b-2"}
    assert read_app_id(tmp_path / "not a shortcut.lnk") is None


def test_no_pins_folder_means_nothing_pinned(tmp_path):
    assert pinned_app_ids(tmp_path / "missing") == set()


def test_filename_drops_characters_windows_forbids():
    assert pinning.shortcut_filename('A/B: "c"?') == "Perch - A_B_ _c__.lnk"
