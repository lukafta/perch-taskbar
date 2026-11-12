import json

import pytest

from perch import config, editing
from perch.models import Config, Group, Shortcut, Style
from perch.store import ConfigStore


@pytest.fixture
def store(qapp, tmp_path):
    path = tmp_path / "config.json"
    cfg = Config((Group("Essentials", (Shortcut("A", "a.exe"),)), Group("Work", ())))
    config.save(cfg, path)
    store = ConfigStore(path, cfg)
    store.seen = []
    store.changed.connect(lambda: store.seen.append("changed"))
    store.problem.connect(store.seen.append)
    return store


def test_edit_changes_then_saves_after_a_pause(store):
    group_id = store.config.groups[0].id
    assert store.apply(lambda c: editing.update_group(c, group_id, style=Style.TILES))
    assert store.seen == ["changed"]
    assert store.save_pending
    assert config.load(store.path).groups[0].style is Style.ROWS  # not yet
    store.save_now()
    assert config.load(store.path).groups[0].style is Style.TILES
    assert not store.changed_on_disk()


def test_refused_edit_reports_and_changes_nothing(store):
    before = store.config
    assert not store.apply(lambda c: editing.rename_group(c, c.groups[1].id, "essentials"))
    assert store.config is before
    assert store.seen == ['There\'s already a group called "Essentials".']
    assert not store.save_pending


def test_hand_edits_are_noticed_and_reloaded(store):
    data = json.loads(store.path.read_text(encoding="utf-8"))
    data["groups"][1]["name"] = "Office"
    store.path.write_text(json.dumps(data), encoding="utf-8")
    assert store.changed_on_disk()
    store.reload()
    assert store.config.groups[1].name == "Office"
    assert not store.changed_on_disk()


def test_broken_hand_edit_raises_and_keeps_the_config(store):
    before = store.config
    store.path.write_text("{ broken", encoding="utf-8")
    with pytest.raises(config.ConfigError):
        store.reload()
    assert store.config is before


def test_backup_and_restore(store, tmp_path):
    backup = tmp_path / "copy.json"
    store.back_up_to(backup)
    store.apply(lambda c: editing.delete_group(c, c.groups[1].id))
    store.save_now()
    previous = store.restore_from(backup)
    assert [g.name for g in store.config.groups] == ["Essentials", "Work"]
    assert [g.name for g in config.load(store.path).groups] == ["Essentials", "Work"]
    assert [g.name for g in config.load(previous).groups] == ["Essentials"]


def test_restoring_a_broken_file_changes_nothing(store, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    before = store.config
    with pytest.raises(config.ConfigError):
        store.restore_from(bad)
    assert store.config is before
    assert not (tmp_path / "config.json.bak").exists()
