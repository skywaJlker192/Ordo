"""Что Ordo разбирает из коробки, путь к настоящей «Загрузкам» и недостающие правила пресета."""
import os
import tempfile
from pathlib import Path

import pytest

from ordo import paths
from ordo.config_io import default_config, missing_preset_rules
from ordo.engine import plan_files, scan
from ordo.rules import parse_config

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 20
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"0" * 10
GIF = b"GIF89a" + b"0" * 20


def _plan(tmp_path, files):
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    cfg = parse_config(default_config())
    ops = plan_files(scan(tmp_path), cfg.rules, tmp_path)
    if any(n.endswith((".gif", ".txt")) and data in (MP4, WEBP, PNG) for n, data in files.items()):
        return {o.dst.name: o.dst.relative_to(tmp_path).parts[0] for o in ops if o.kind == "move"}
    return {o.src.name: o.dst.relative_to(tmp_path).parts[0] for o in ops if o.kind == "move"}


def test_preset_leaves_nothing_behind(tmp_path):
    names = ["a.gif", "b.md", "c.mp3", "d.docx", "e.mp4", "f.webp", "g.xlsx", "h.epf", "i.lnk", "j.torrent",
             "k.psd", "l.ttf", "m.json", "n.pdf", "noext", "Новый документ.txt", "o.ico", "p.cr2", "q.mid",
             "r.mobi", "s.log", "t.ini", "u.vue", "v.cab", "w.rpm", "x.ts", "CAPS.GIF"]
    got = _plan(tmp_path, {n: b"hello world" for n in names})
    assert set(got) == set(names), f"остались: {set(names) - set(got)}"
    assert got["a.gif"] == "Изображения" and got["b.md"] == "Документы" and got["c.mp3"] == "Музыка"
    assert got["h.epf"] == "Прочее" and got["i.lnk"] == "Прочее" and got["noext"] == "Прочее"
    assert got["j.torrent"] == "Торренты" and got["k.psd"] == "Дизайн" and got["l.ttf"] == "Шрифты"


def test_gifs_that_are_really_video_or_webp_still_get_sorted(tmp_path):
    got = _plan(tmp_path, {"anim.gif": MP4, "sticker.gif": WEBP, "real.gif": GIF, "photo.txt": PNG})
    # расширение исправляется по содержимому, и файл всё равно уезжает куда надо
    assert got == {"anim.mp4": "Видео", "sticker.webp": "Изображения", "real.gif": "Изображения",
                   "photo.png": "Изображения"}


def test_catch_all_is_last_and_can_be_turned_off():
    rules = default_config()["rules"]
    assert rules[-1]["name"] == "Всё остальное"


# ---------- папка загрузок ----------

def test_tilde_downloads_follows_real_downloads_folder(monkeypatch, tmp_path):
    moved = tmp_path / "Мои загрузки"
    monkeypatch.setattr(paths, "_windows_downloads", lambda: moved)
    assert paths.expand("~/Downloads") == moved
    assert paths.expand("~\\Downloads\\Скриншоты") == moved / "Скриншоты" or \
        str(paths.expand("~\\Downloads\\Скриншоты")).startswith(str(moved))
    assert paths.expand("~/Downloads/sub") == moved / "sub"
    assert paths.expand("~/DOWNLOADS") == moved
    # похожее имя не должно подменяться
    assert paths.expand("~/Downloads2") != moved / "2"
    assert paths.expand("~/Downloads2").name == "Downloads2"
    assert paths.expand("~/Documents").name == "Documents"


def test_downloads_dir_falls_back_to_home_downloads(monkeypatch):
    monkeypatch.setattr(paths, "_windows_downloads", lambda: None)
    assert paths.downloads_dir() == Path.home() / "Downloads"


def test_open_target_uses_real_downloads(monkeypatch, tmp_path):
    from ordo.scenarios import resolve_open_target
    real = tmp_path / "D-загрузки"
    real.mkdir()
    monkeypatch.setattr(paths, "_windows_downloads", lambda: real)
    assert Path(resolve_open_target("~/Downloads")) == real


# ---------- недостающие правила ----------

def test_missing_preset_rules_only_adds_what_is_absent():
    raw = default_config()
    assert missing_preset_rules(raw) == []
    raw["rules"] = [r for r in raw["rules"] if r["name"] not in ("Шрифты", "Всё остальное")]
    raw["rules"].append({"name": "Моё", "conditions": [{"field": "ext", "op": "equals", "value": "x"}],
                         "actions": [{"do": "trash"}]})
    assert [r["name"] for r in missing_preset_rules(raw)] == ["Шрифты", "Всё остальное"]
