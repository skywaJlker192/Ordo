import os
from datetime import datetime
from pathlib import Path

import pytest

from ordo.conditions import parse_size
from ordo.engine import apply_plan, plan_files, scan, undo_batch
from ordo.errors import ConfigError
from ordo.filetypes import detect
from ordo.journal import Journal
from ordo.rules import load_config, parse_config

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
PRESET = Path(__file__).parent.parent / "ordo" / "presets" / "downloads.json"


@pytest.fixture(autouse=True)
def ordo_home(tmp_path, monkeypatch):
    home = tmp_path / "ordo_home"
    monkeypatch.setenv("ORDO_HOME", str(home))
    return home


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "Downloads"
    d.mkdir()
    return d


def cfg_of(*rules):
    return parse_config({"watch": [], "rules": list(rules)})


def rule(name, conditions, actions, **extra):
    return {"name": name, "conditions": conditions, "actions": actions, **extra}


def cond(field, op, value):
    return {"field": field, "op": op, "value": value}


def test_detects_type_by_content_not_extension(folder):
    f = folder / "photo.txt"
    f.write_bytes(PNG)
    info = detect(f)
    assert (info.kind, info.real_ext, info.by_content) == ("image", "png", True)


def test_screenshot_goes_to_year_month_folder(folder):
    f = folder / "Screenshot 1.png"
    f.write_bytes(PNG)
    ts = datetime(2026, 3, 15, 12, 0).timestamp()
    os.utime(f, (ts, ts))
    cfg = cfg_of(rule(
        "Скриншоты",
        [cond("type", "equals", "image"), cond("name", "startswith", "screenshot")],
        [{"do": "move", "to": "Скриншоты/{year}-{month}"}],
    ))
    ops = plan_files([f], cfg.rules, folder)
    assert [o.dst for o in ops] == [folder / "Скриншоты" / "2026-03" / "Screenshot 1.png"]


def test_preview_does_not_touch_disk(folder):
    f = folder / "a.png"
    f.write_bytes(PNG)
    cfg = cfg_of(rule("img", [cond("type", "equals", "image")], [{"do": "move", "to": "Img"}]))
    plan_files(scan(folder), cfg.rules, folder)
    assert f.exists() and not (folder / "Img").exists()


def test_name_conflicts_never_overwrite(folder):
    a, b = folder / "a.png", folder / "b.png"
    a.write_bytes(PNG)
    b.write_bytes(PNG)
    cfg = cfg_of(rule("same", [cond("ext", "equals", "png")],
                      [{"do": "rename", "template": "same.{ext}"}]))
    ops = plan_files([a, b], cfg.rules, folder)
    assert sorted(o.dst.name for o in ops) == ["same (1).png", "same.png"]


def test_existing_destination_is_not_overwritten(folder):
    (folder / "Img").mkdir()
    (folder / "Img" / "a.png").write_bytes(b"old")
    f = folder / "a.png"
    f.write_bytes(PNG)
    cfg = cfg_of(rule("img", [cond("type", "equals", "image")], [{"do": "move", "to": "Img"}]))
    ops = plan_files([f], cfg.rules, folder)
    assert ops[0].dst.name == "a (1).png"


def test_apply_then_undo_restores_everything(folder, ordo_home):
    f = folder / "a.png"
    f.write_bytes(PNG)
    cfg = cfg_of(rule("img", [cond("type", "equals", "image")], [{"do": "move", "to": "Img/{year}"}]))
    journal = Journal(ordo_home / "ordo.db")
    result = apply_plan(plan_files([f], cfg.rules, folder), journal)
    assert result.done == 1 and not f.exists()
    undo = undo_batch(journal)
    assert undo.restored == 1 and f.read_bytes() == PNG
    assert not (folder / "Img").exists()  # пустые созданные папки убраны
    assert undo_batch(journal) is None    # откатывать больше нечего


def test_undo_skips_instead_of_overwriting(folder, ordo_home):
    f = folder / "a.png"
    f.write_bytes(PNG)
    cfg = cfg_of(rule("img", [cond("type", "equals", "image")], [{"do": "move", "to": "Img"}]))
    journal = Journal(ordo_home / "ordo.db")
    apply_plan(plan_files([f], cfg.rules, folder), journal)
    f.write_bytes(b"new file in old place")
    undo = undo_batch(journal)
    assert undo.restored == 0 and len(undo.skipped) == 1
    assert f.read_bytes() == b"new file in old place"


def test_trash_is_recoverable(folder, ordo_home):
    f = folder / "setup.exe"
    f.write_bytes(b"MZ" + b"\x00" * 30)
    cfg = cfg_of(rule("old", [cond("type", "equals", "installer")], [{"do": "trash"}]))
    journal = Journal(ordo_home / "ordo.db")
    apply_plan(plan_files([f], cfg.rules, folder), journal)
    assert not f.exists()
    assert any((ordo_home / "trash").rglob("setup.exe"))
    undo_batch(journal)
    assert f.exists()


def test_chain_fix_extension_then_sort(folder, ordo_home):
    f = folder / "photo.txt"
    f.write_bytes(PNG)
    cfg = cfg_of(
        rule("fix", [cond("mismatch", "equals", True)],
             [{"do": "rename", "template": "{stem}.{real_ext}"}], stop=False),
        rule("img", [cond("type", "equals", "image")], [{"do": "move", "to": "Img"}]),
    )
    journal = Journal(ordo_home / "ordo.db")
    ops = plan_files([f], cfg.rules, folder)
    assert [o.kind for o in ops] == ["rename", "move"]
    assert {o.origin for o in ops} == {f}  # цепочка считается одним файлом
    result = apply_plan(ops, journal)
    assert result.done == 2 and (folder / "Img" / "photo.png").exists()
    undo_batch(journal)
    assert f.exists()  # откат цепочки возвращает исходное имя


def test_copy_keeps_original_and_undo_removes_copy(folder, ordo_home):
    f = folder / "a.png"
    f.write_bytes(PNG)
    cfg = cfg_of(rule("c", [cond("type", "equals", "image")], [{"do": "copy", "to": "Backup"}]))
    journal = Journal(ordo_home / "ordo.db")
    apply_plan(plan_files([f], cfg.rules, folder), journal)
    assert f.exists() and (folder / "Backup" / "a.png").exists()
    undo_batch(journal)
    assert f.exists() and not (folder / "Backup" / "a.png").exists()


def test_any_match_and_regex(folder):
    f = folder / "Договор аренды.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    cfg = cfg_of(rule("важное", [cond("name", "regex", "(чек|договор)"), cond("size", "gt", "1GB")],
                      [{"do": "move", "to": "Важное"}], match="any"))
    assert len(plan_files([f], cfg.rules, folder)) == 1


def test_size_and_age_conditions(folder):
    f = folder / "big.zip"
    f.write_bytes(b"PK\x03\x04" + b"0" * 2048)
    old = datetime(2020, 1, 1).timestamp()
    os.utime(f, (old, old))
    cfg = cfg_of(rule("old big", [cond("size", "gte", "1KB"), cond("age_days", "gt", 30)],
                      [{"do": "move", "to": "Old"}]))
    assert len(plan_files([f], cfg.rules, folder)) == 1


def test_disabled_rule_is_ignored(folder):
    f = folder / "a.png"
    f.write_bytes(PNG)
    cfg = cfg_of(rule("img", [cond("type", "equals", "image")], [{"do": "move", "to": "Img"}],
                      enabled=False))
    assert plan_files([f], cfg.rules, folder) == []


def test_scan_skips_temp_hidden_and_dirs(folder):
    (folder / "video.mp4.crdownload").write_bytes(b"x")
    (folder / ".hidden").write_bytes(b"x")
    (folder / "sub").mkdir()
    (folder / "ok.txt").write_bytes(b"x")
    assert [p.name for p in scan(folder)] == ["ok.txt"]


def test_parse_size():
    assert parse_size("1KB") == 1024
    assert parse_size("1,5 MB") == int(1.5 * 1024 ** 2)
    assert parse_size(300) == 300
    with pytest.raises(ConfigError):
        parse_size("много")


@pytest.mark.parametrize("bad", [
    rule("x", [cond("color", "equals", "red")], [{"do": "trash"}]),
    rule("x", [cond("name", "gt", "a")], [{"do": "trash"}]),
    rule("x", [cond("name", "regex", "(")], [{"do": "trash"}]),
    rule("x", [], [{"do": "trash"}]),
    rule("x", [cond("name", "equals", "a")], []),
    rule("x", [cond("name", "equals", "a")], [{"do": "explode"}]),
    rule("x", [cond("name", "equals", "a")], [{"do": "move", "to": "{nope}"}]),
    rule("x", [cond("name", "equals", "a")], [{"do": "trash"}, {"do": "move", "to": "A"}]),
])
def test_invalid_config_gives_readable_error(bad):
    with pytest.raises(ConfigError):
        cfg_of(bad)


def test_preset_is_valid():
    cfg = load_config(PRESET)
    assert len(cfg.rules) >= 10 and cfg.watch
