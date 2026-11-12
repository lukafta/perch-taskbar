import pytest

from perch import editing
from perch.editing import EditError
from perch.models import Config, Group, Layout, PinKind, Shortcut, Style, Theme

A = Shortcut("A", "a.exe")
B = Shortcut("B", "b.exe")
C = Shortcut("C", "c.exe")


@pytest.fixture
def cfg():
    return Config((Group("Essentials", (A, B, C)), Group("Work", (A,))))


def ids(config):
    return [g.id for g in config.groups]


def test_new_groups_get_unique_names(cfg):
    cfg, first = editing.add_group(cfg)
    cfg, second = editing.add_group(cfg)
    assert (first.name, second.name) == ("New group", "New group 2")
    assert first.shortcuts == ()
    assert len(set(ids(cfg))) == 4


def test_new_group_never_reuses_a_renamed_groups_id(cfg):
    old_id = cfg.groups[1].id
    cfg = editing.rename_group(cfg, old_id, "Office")
    cfg, again = editing.add_group(cfg, "Work")
    assert again.id != old_id
    assert len(set(ids(cfg))) == 3


def test_rename_keeps_the_id(cfg):
    group_id = cfg.groups[1].id
    renamed = editing.rename_group(cfg, group_id, "  Office ")
    assert renamed.groups[1].name == "Office"
    assert renamed.groups[1].id == group_id


@pytest.mark.parametrize(("name", "message"), [("", "needs a name"), ("essentials", 'already a group called "Essentials"')])
def test_bad_names_are_refused(cfg, name, message):
    with pytest.raises(EditError, match=message):
        editing.rename_group(cfg, cfg.groups[1].id, name)


def test_renaming_to_its_own_name_in_another_case_is_fine(cfg):
    assert editing.rename_group(cfg, cfg.groups[1].id, "WORK").groups[1].name == "WORK"


def test_delete_group(cfg):
    assert ids(editing.delete_group(cfg, cfg.groups[0].id)) == [cfg.groups[1].id]


def test_last_group_cannot_be_deleted(cfg):
    cfg = editing.delete_group(cfg, cfg.groups[0].id)
    with pytest.raises(EditError, match="at least one group"):
        editing.delete_group(cfg, cfg.groups[0].id)


def test_reorder_groups(cfg):
    order = list(reversed(ids(cfg)))
    assert ids(editing.reorder_groups(cfg, order)) == order


def test_reorder_with_a_stale_list_is_refused(cfg):
    with pytest.raises(EditError):
        editing.reorder_groups(cfg, [cfg.groups[0].id])


def test_unknown_group_is_refused(cfg):
    with pytest.raises(EditError, match="doesn't exist"):
        editing.update_group(cfg, "nope", style=Style.TILES)


def test_update_group_and_pin(cfg):
    group_id = cfg.groups[0].id
    cfg = editing.update_group(cfg, group_id, style=Style.TILES, layout=Layout.GRID, columns=3, opacity=0.5)
    cfg = editing.update_pin(cfg, group_id, kind=PinKind.MARK, color="blue", letter="X")
    group = cfg.groups[0]
    assert (group.style, group.layout, group.columns, group.opacity) == (Style.TILES, Layout.GRID, 3, 0.5)
    assert (group.pin.color, group.pin.letter) == ("blue", "X")


def test_shortcut_edits(cfg):
    group_id = cfg.groups[0].id
    cfg = editing.add_shortcuts(cfg, group_id, [Shortcut("D", "d.exe")])
    cfg = editing.replace_shortcut(cfg, group_id, 0, Shortcut("A2", "a2.exe"))
    cfg = editing.remove_shortcut(cfg, group_id, 1)
    cfg = editing.reorder_shortcuts(cfg, group_id, [2, 0, 1])
    assert [s.name for s in cfg.groups[0].shortcuts] == ["D", "A2", "C"]


def test_shortcut_index_out_of_range_is_refused(cfg):
    with pytest.raises(EditError):
        editing.remove_shortcut(cfg, cfg.groups[1].id, 5)


def test_settings(cfg):
    cfg = editing.update_settings(cfg, theme=Theme.DARK, show_header=False)
    assert (cfg.settings.theme, cfg.settings.show_header) == (Theme.DARK, False)


@pytest.mark.parametrize(
    ("name", "expected"),
    [("notepad.exe", "Notepad"), ("Games.lnk", "Games"), ("readme.txt", "Readme"), ("iTunes.exe", "iTunes")],
)
def test_shortcut_for_a_file_is_named_after_it(tmp_path, name, expected):
    path = tmp_path / name
    path.write_text("")
    shortcut = editing.shortcut_for_path(path)
    assert shortcut == Shortcut(expected, str(path))


def test_shortcut_for_a_folder_keeps_its_name(tmp_path):
    folder = tmp_path / "Photos 2026"
    folder.mkdir()
    assert editing.shortcut_for_path(folder).name == "Photos 2026"
