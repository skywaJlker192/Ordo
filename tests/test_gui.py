"""Интерфейс без экрана (offscreen): окно строится, правки доходят до диска, слежение и откат работают."""
import json
import os
import tempfile
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="ordo-test-xdg-"))
pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from ordo.config_io import default_config, load_raw, save_raw, validate_rule  # noqa: E402
from ordo.describe import describe_rule  # noqa: E402
from ordo.gui import rules_page, theme  # noqa: E402
from ordo.gui.history_page import HistoryPage  # noqa: E402
from ordo.gui.main_window import MainWindow  # noqa: E402
from ordo.gui.rule_editor import RuleEditor  # noqa: E402
from ordo.gui.rules_page import RulesPage  # noqa: E402
from ordo.gui.state import AppState  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    theme.apply(app)
    return app


def wait_until(app, cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def env(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("ORDO_HOME", str(tmp_path / "home"))
    dl = tmp_path / "dl"
    dl.mkdir()
    cfg = {
        "watch": [{"folder": str(dl), "settle_seconds": 0.2}],
        "rules": [
            {"name": "Картинки", "conditions": [{"field": "type", "op": "equals", "value": "image"}],
             "actions": [{"do": "move", "to": "Img"}]},
            {"name": "Архивы", "conditions": [{"field": "type", "op": "equals", "value": "archive"}],
             "actions": [{"do": "move", "to": "Arc"}]},
        ],
    }
    path = tmp_path / "home" / "config.json"
    save_raw(path, cfg)
    state = AppState(path)
    yield state, dl, path
    state.shutdown()


# ---------- окно ----------

def test_window_builds_and_every_page_opens(env, qapp):
    state, _dl, _ = env
    win = MainWindow(state, tray_available=False)
    win.show()
    for i in range(len(win.pages)):
        win.go(i)
        qapp.processEvents()
        assert win.stack.currentIndex() == i and win.nav_buttons[i].isChecked()
    win.close()


def test_closing_window_with_tray_hides_instead_of_quitting(env, qapp):
    state, _dl, _ = env
    win = MainWindow(state, tray_available=True)
    win.show()
    win.close()
    assert not win.isVisible() and not win._quitting


# ---------- редактор правил ----------

def test_editor_roundtrip_keeps_every_preset_rule_intact(qapp):
    """Открыть и сохранить правило без правок не должно менять его смысл."""
    for rule in default_config()["rules"]:
        ed = RuleEditor(rule)
        out = ed._collect()
        assert out["conditions"] == rule["conditions"], rule["name"]
        assert out["actions"] == rule["actions"], rule["name"]
        assert out["stop"] == rule.get("stop", True)
        assert validate_rule(out) is None
        assert describe_rule(out) == describe_rule(rule)


def test_editor_builds_rule_from_scratch_and_validates(qapp):
    ed = RuleEditor(None)
    row = ed._cond_rows[0]
    row.field.setCurrentIndex(row.field.findData("size"))
    row.op.setCurrentIndex(row.op.findData("gt"))
    row.edit.setText("10MB")
    ed._act_rows[0].param.setText("Большие/{year}")
    ed.name.setText("Большие файлы")
    rule = ed._collect()
    assert rule["conditions"] == [{"field": "size", "op": "gt", "value": "10MB"}]
    assert rule["actions"] == [{"do": "move", "to": "Большие/{year}"}]
    assert validate_rule(rule) is None


def test_editor_blocks_save_on_invalid_rule(qapp):
    ed = RuleEditor(None)
    row = ed._cond_rows[0]
    row.field.setCurrentIndex(row.field.findData("size"))
    row.edit.setText("очень много")
    ed._save()
    assert ed.result_rule is None and not ed.error.isHidden()


def test_editor_comma_list_and_placeholder_chip(qapp):
    ed = RuleEditor(None)
    row = ed._cond_rows[0]
    row.field.setCurrentIndex(row.field.findData("name"))
    row.op.setCurrentIndex(row.op.findData("startswith"))
    row.edit.setText("img, фото ,")
    assert row.to_dict()["value"] == ["img", "фото"]
    ed._act_rows[0].param.setText("Папка/")
    ed._act_rows[0].param.setCursorPosition(len("Папка/"))
    ed._last_param = ed._act_rows[0].param
    ed._insert_placeholder("year")
    assert ed._act_rows[0].param.text() == "Папка/{year}"


# ---------- страница правил: всё сохраняется на диск ----------

def test_rules_page_actions_are_saved_to_disk(env, qapp, monkeypatch):
    state, _dl, path = env
    monkeypatch.setattr(rules_page, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(rules_page, "warn", lambda *a, **k: pytest.fail("не должно быть ошибок"))
    page = RulesPage(state)
    names = lambda: [r["name"] for r in load_raw(path)["rules"]]  # noqa: E731

    page._toggle(0, False)
    assert load_raw(path)["rules"][0]["enabled"] is False
    page._move(0, 1)
    assert names() == ["Архивы", "Картинки"]
    page._copy(0)
    assert names() == ["Архивы", "Архивы (копия)", "Картинки"]
    page._delete(1)
    assert names() == ["Архивы", "Картинки"]
    assert (path.with_name("config.json.bak")).exists()


def test_invalid_config_is_rejected_and_file_untouched(env):
    state, _dl, path = env
    before = path.read_text(encoding="utf-8")
    err = state.set_rules([{"name": "x", "conditions": [], "actions": []}])
    assert err and path.read_text(encoding="utf-8") == before
    assert len(state.rules) == 2  # в памяти тоже прежнее


def test_rules_import_export_shape(env, qapp, monkeypatch, tmp_path):
    state, _dl, path = env
    page = RulesPage(state)
    out = tmp_path / "share.json"
    monkeypatch.setattr(rules_page.QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    page._export()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [r["name"] for r in data["rules"]] == ["Картинки", "Архивы"]

    # импорт: одно хорошее и одно битое правило
    good = {"name": "Видео", "conditions": [{"field": "type", "op": "equals", "value": "video"}],
            "actions": [{"do": "move", "to": "Vid"}]}
    bad = {"name": "Плохое", "conditions": [], "actions": []}
    out.write_text(json.dumps({"rules": [good, bad]}), encoding="utf-8")
    warned = []
    monkeypatch.setattr(rules_page.QFileDialog, "getOpenFileName", lambda *a, **k: (str(out), ""))
    monkeypatch.setattr(rules_page, "warn", lambda _p, text: warned.append(text))
    page._import()
    assert [r["name"] for r in load_raw(path)["rules"]] == ["Картинки", "Архивы", "Видео"]
    assert warned and "Пропущено" in warned[0]


# ---------- разбор, откат, журнал ----------

def test_apply_then_undo_through_state(env, qapp):
    state, dl, _ = env
    (dl / "a.png").write_bytes(PNG)
    (dl / "b.zip").write_bytes(b"PK\x03\x04" + b"0" * 20)
    toasts = []
    state.toast.connect(lambda text, kind: toasts.append((text, kind)))

    plans = state.plan()
    assert sum(len(ops) for _f, ops, _t in plans) == 2
    state.apply(plans)
    assert wait_until(qapp, lambda: any("Готово" in t for t, _k in toasts))
    assert (dl / "Img" / "a.png").exists() and (dl / "Arc" / "b.zip").exists()

    state.undo()
    assert wait_until(qapp, lambda: any("отменён" in t for t, _k in toasts))
    assert (dl / "a.png").exists() and (dl / "b.zip").exists()


def test_history_page_lists_batches_and_loads_files_on_expand(env, qapp):
    state, dl, _ = env
    (dl / "a.png").write_bytes(PNG)
    state.apply(state.plan())
    assert wait_until(qapp, lambda: state.journal.last_active_batch() is not None)
    page = HistoryPage(state)
    assert page.tree.topLevelItemCount() == 1
    top = page.tree.topLevelItem(0)
    top.setExpanded(True)
    assert top.childCount() == 1 and "a.png" in top.child(0).text(0)


# ---------- слежение в фоне ----------

def test_background_watch_sorts_new_file_and_stops(env, qapp):
    state, dl, _ = env
    changes = []
    state.watch_changed.connect(changes.append)
    assert state.start_watch(silent=True) and state.watching
    time.sleep(0.3)
    (dl / "new.png").write_bytes(PNG)
    assert wait_until(qapp, lambda: (dl / "Img" / "new.png").exists())
    assert wait_until(qapp, lambda: state.journal.last_active_batch() is not None)
    state.stop_watch(silent=True)
    assert not state.watching and changes == [True, False]


def test_start_watch_without_any_folder_does_not_start(env, qapp):
    state, dl, _ = env
    state.set_watch_folders([{"folder": str(dl / "нет-такой"), "settle_seconds": 1}])
    toasts = []
    state.toast.connect(lambda text, kind: toasts.append(text))
    assert state.start_watch() is False and not state.watching
    assert toasts and "папок" in toasts[0].lower()


def test_saving_config_restarts_running_watcher_with_new_rules(env, qapp):
    state, dl, _ = env
    state.start_watch(silent=True)
    rules = [{"name": "Всё в Misc", "conditions": [{"field": "ext", "op": "equals", "value": "png"}],
              "actions": [{"do": "move", "to": "Misc"}]}]
    assert state.set_rules(rules) is None and state.watching
    time.sleep(0.3)
    (dl / "x.png").write_bytes(PNG)
    assert wait_until(qapp, lambda: (dl / "Misc" / "x.png").exists())
    state.stop_watch(silent=True)
