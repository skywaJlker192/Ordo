"""Всё, на чём стоит интерфейс: сохранение конфига, описания правил, данные для графиков, остановка слежения."""
import json
import threading
import time
from datetime import date

import pytest

from ordo.config_io import default_config, ensure_config, load_raw, save_raw, validate_rule
from ordo.describe import describe_action, describe_condition, describe_rule
from ordo.engine import apply_plan, plan_files
from ordo.errors import ConfigError
from ordo.journal import Journal
from ordo.rules import parse_config
from ordo.watcher import Watcher

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32

IMG_RULE = {
    "name": "img",
    "conditions": [{"field": "type", "op": "equals", "value": "image"}],
    "actions": [{"do": "move", "to": "Img"}],
}


# ---------- config_io ----------

def test_ensure_config_creates_file_from_preset(tmp_path):
    path = tmp_path / "cfg" / "config.json"
    data = ensure_config(path)
    assert path.exists() and data["rules"] == default_config()["rules"]


def test_save_raw_rejects_bad_config_and_keeps_old_file(tmp_path):
    path = tmp_path / "config.json"
    save_raw(path, {"watch": [], "rules": [IMG_RULE]})
    before = path.read_text(encoding="utf-8")
    bad = {"watch": [], "rules": [{"name": "x", "conditions": [], "actions": []}]}
    with pytest.raises(ConfigError):
        save_raw(path, bad)
    assert path.read_text(encoding="utf-8") == before


def test_save_raw_makes_backup_and_no_tmp_left(tmp_path):
    path = tmp_path / "config.json"
    save_raw(path, {"watch": [], "rules": [IMG_RULE]})
    save_raw(path, {"watch": [], "rules": []})
    backup = json.loads((tmp_path / "config.json.bak").read_text(encoding="utf-8"))
    assert backup["rules"][0]["name"] == "img"
    assert not (tmp_path / "config.json.tmp").exists()


def test_load_raw_reports_broken_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ oops", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_raw(path)


def test_validate_rule():
    assert validate_rule(IMG_RULE) is None
    assert "условие" in validate_rule({"name": "x", "conditions": [], "actions": []})


# ---------- describe ----------

def test_describe_rule_in_plain_russian():
    rule = {
        "name": "Скриншоты",
        "conditions": [
            {"field": "type", "op": "equals", "value": "image"},
            {"field": "name", "op": "startswith", "value": ["screenshot", "снимок"]},
        ],
        "actions": [{"do": "move", "to": "Скриншоты/{year}"}],
    }
    cond, act = describe_rule(rule)
    assert cond == "тип равно картинка и имя начинается с «screenshot», «снимок»"
    assert act == "переместить в «Скриншоты/{year}»"


def test_describe_special_cases():
    assert describe_condition({"field": "mismatch", "op": "equals", "value": True}) == \
        "расширение не совпадает с содержимым"
    assert describe_condition({"field": "mismatch", "op": "not_equals", "value": True}) == \
        "расширение совпадает с содержимым"
    assert describe_condition({"field": "age_days", "op": "gt", "value": 7}) == "возраст больше 7 дн."
    assert describe_action({"do": "trash"}) == "отправить в корзину Ordo"


def test_describe_survives_half_filled_rule():
    cond, act = describe_rule({"name": "новое"})
    assert cond and act  # не падает, пока правило ещё не заполнено
    assert describe_condition({}) and describe_action({})


def test_every_preset_rule_can_be_described():
    for rule in default_config()["rules"]:
        cond, act = describe_rule(rule)
        assert cond and act and "None" not in cond + act


# ---------- журнал для графиков ----------

def _journal_with_one_move(tmp_path):
    folder = tmp_path / "d"
    folder.mkdir()
    f = folder / "a.png"
    f.write_bytes(PNG)
    cfg = parse_config({"watch": [], "rules": [IMG_RULE]})
    journal = Journal(tmp_path / "j.db")
    result = apply_plan(plan_files([f], cfg.rules, folder), journal)
    return journal, result


def test_recent_ops_and_daily_counts(tmp_path):
    journal, result = _journal_with_one_move(tmp_path)
    rows = journal.recent_ops(5)
    assert len(rows) == 1 and rows[0]["rule"] == "img" and rows[0]["undone"] == 0
    days = journal.daily_counts(14)
    assert len(days) == 14 and days[-1] == (date.today(), 1)
    assert sum(n for _, n in days[:-1]) == 0


def test_daily_counts_ignore_undone_batches(tmp_path):
    from ordo.engine import undo_batch
    journal, _ = _journal_with_one_move(tmp_path)
    undo_batch(journal)
    assert journal.daily_counts(7)[-1][1] == 0


# ---------- наблюдатель: остановка и колбэк ----------

def test_watcher_calls_back_and_stops(tmp_path):
    folder = tmp_path / "w"
    folder.mkdir()
    cfg = parse_config({
        "watch": [{"folder": str(folder), "settle_seconds": 0.2}],
        "rules": [IMG_RULE],
    })
    journal = Journal(tmp_path / "j.db")
    seen = []
    w = Watcher(cfg, journal, log=lambda s: None, poll=0.05,
                on_batch=lambda ops, res: seen.append((len(ops), res.done)))
    t = threading.Thread(target=w.run, daemon=True)
    t.start()
    time.sleep(0.4)
    (folder / "a.png").write_bytes(PNG)

    deadline = time.time() + 6
    while not seen and time.time() < deadline:
        time.sleep(0.05)
    w.stop()
    t.join(timeout=3)

    assert seen == [(1, 1)]
    assert (folder / "Img" / "a.png").exists()
    assert not t.is_alive()  # stop() реально останавливает цикл
