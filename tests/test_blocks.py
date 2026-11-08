"""Блоки-пазлы, редактор сценариев, страница и движок автоматизации (offscreen, WinAPI подменён)."""
import json
import os
import tempfile
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="ordo-test-xdg-"))
pytest.importorskip("PyQt5")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtGui import QKeyEvent  # noqa: E402
from PyQt5.QtCore import QEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from ordo import hotkeys  # noqa: E402
from ordo.config_io import save_raw, validate_scenario  # noqa: E402
from ordo.gui import theme  # noqa: E402
from ordo.gui.automation import AutomationEngine  # noqa: E402
from ordo.gui.blocks import HotkeyEdit, make_block  # noqa: E402
from ordo.gui.scenario_editor import ScenarioEditor  # noqa: E402
from ordo.gui.scenarios_page import ScenariosPage  # noqa: E402
from ordo.gui.state import AppState  # noqa: E402
from ordo.scenarios import templates  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    theme.apply(app)
    return app


@pytest.fixture
def state(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("ORDO_HOME", str(tmp_path / "home"))
    path = tmp_path / "home" / "config.json"
    save_raw(path, {"watch": [], "rules": [], "scenarios": []})
    st = AppState(path)
    yield st
    st.shutdown()


@pytest.mark.parametrize("tpl", templates(), ids=lambda t: t["name"])
def test_every_template_roundtrips_through_the_editor(qapp, tpl):
    ed = ScenarioEditor(tpl)
    out = ed.build()
    assert out["trigger"] == tpl["trigger"]
    assert out["actions"] == tpl["actions"]
    assert out["name"] == tpl["name"] and out["description"] == tpl["description"]
    assert validate_scenario(out) is None


def test_editor_refuses_empty_and_invalid_scenarios(qapp):
    ed = ScenarioEditor({"name": "x", "trigger": {"type": "startup"}, "actions": []})
    ed._save()
    assert ed.result_scenario is None and "Делать" in ed.error.text()
    ed = ScenarioEditor({"name": "x", "trigger": {"type": "hotkey", "keys": "L"},
                         "actions": [{"do": "notify", "text": "a"}]})
    ed._save()
    assert ed.result_scenario is None and ed.error.text()


def test_stack_add_move_remove_keep_order(qapp):
    ed = ScenarioEditor({"name": "x", "trigger": {"type": "startup"}, "actions": [
        {"do": "notify", "text": "1"}, {"do": "notify", "text": "2"}, {"do": "notify", "text": "3"}]})
    texts = lambda: [a["text"] for a in ed.stack.to_actions()]  # noqa: E731
    ed.stack.move_block(ed.stack.blocks[0], 3)  # в конец
    assert texts() == ["2", "3", "1"]
    ed.stack.move_block(ed.stack.blocks[2], 0)  # в начало
    assert texts() == ["1", "2", "3"]
    ed.stack.remove_block(ed.stack.blocks[1])
    assert texts() == ["1", "3"]
    ed._from_palette("action", "open")
    assert ed.stack.to_actions()[-1]["do"] == "open"


def test_new_trigger_replaces_old_one(qapp):
    ed = ScenarioEditor(None)
    ed._from_palette("trigger", "startup")
    assert ed.stack.trigger() == {"type": "startup"}


def test_hotkey_edit_captures_real_key_press(qapp):
    e = HotkeyEdit()
    e.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_L, Qt.ControlModifier | Qt.AltModifier))
    assert e.text() == "Ctrl+Alt+L"
    e.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Control, Qt.ControlModifier))
    assert e.text() == "Ctrl+Alt+L"  # одни модификаторы ничего не меняют
    e.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_L, Qt.NoModifier))
    assert e.property("invalid") is True
    e.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_F5, Qt.NoModifier))
    assert e.text() == "F5" and not e.property("invalid")


def test_unknown_block_data_is_ignored(qapp):
    assert make_block({"do": "format_c"}) is None and make_block({"type": "nope"}) is None


# ---------- страница ----------

def test_page_actions_write_config_and_import_is_disabled_and_validated(state, qapp, tmp_path, monkeypatch):
    from ordo.gui import scenarios_page as sp
    monkeypatch.setattr(sp, "confirm", lambda *a, **k: True)
    page = ScenariosPage(state, AutomationEngine(state))
    page._add_template(templates()[0])
    assert len(json.loads(state.path.read_text("utf-8"))["scenarios"]) == 1
    page._copy(0)
    assert [s["name"] for s in state.scenarios][1].endswith("(копия)")
    page._toggle(0, False)
    assert state.scenarios[0]["enabled"] is False
    page._delete(1)
    assert len(state.scenarios) == 1

    f = tmp_path / "in.json"
    f.write_text(json.dumps({"scenarios": [
        {"name": "Чужой", "enabled": True, "trigger": {"type": "startup"},
         "actions": [{"do": "open", "target": "https://example.com"}]},
        {"name": "Битый", "trigger": {"type": "hotkey", "keys": "L"}, "actions": []}]}), "utf-8")
    shown = []
    monkeypatch.setattr(sp, "warn", lambda _p, t: shown.append(t))
    page.import_file(f)
    imported = [s for s in state.scenarios if s["name"] == "Чужой"]
    assert imported and imported[0]["enabled"] is False  # чужое не включается само
    assert not any(s["name"] == "Битый" for s in state.scenarios) and shown


def test_import_declined_adds_nothing(state, qapp, tmp_path, monkeypatch):
    from ordo.gui import scenarios_page as sp
    monkeypatch.setattr(sp, "confirm", lambda *a, **k: False)
    page = ScenariosPage(state, AutomationEngine(state))
    f = tmp_path / "in.json"
    f.write_text(json.dumps([{"name": "A", "trigger": {"type": "startup"},
                              "actions": [{"do": "open", "target": "https://example.com"}]}]), "utf-8")
    page.import_file(f)
    assert state.scenarios == []


# ---------- движок ----------

class FakeListener:
    instances = []

    def __init__(self, keys, on_press, on_fail):
        self.keys, self.on_press, self.on_fail, self.stopped = keys, on_press, on_fail, False
        FakeListener.instances.append(self)

    def start(self): pass
    def stop(self): self.stopped = True


def _engine(state, monkeypatch, scenarios):
    monkeypatch.setattr(hotkeys, "supported", lambda: True)
    FakeListener.instances = []
    AutomationEngine.listener_cls = FakeListener
    assert state.save({**state.raw, "scenarios": scenarios}) is None
    eng = AutomationEngine(state)
    eng.reload()
    calls = []
    eng.env.notify = lambda t: calls.append(("notify", t))
    eng.env.open_target = lambda t: calls.append(("open", t))
    return eng, calls


def test_hotkey_press_runs_scenario_and_reload_releases_keys(state, monkeypatch):
    sc = {"name": "N", "trigger": {"type": "hotkey", "keys": "Ctrl+Alt+N"},
          "actions": [{"do": "notify", "text": "привет"}]}
    eng, calls = _engine(state, monkeypatch, [sc])
    first = FakeListener.instances[-1]
    assert first.keys[1] == "Ctrl+Alt+N" and 1000 in first.keys  # 1000: радиальное меню
    first.on_press(1)
    assert calls == [("notify", "привет")]
    eng.reload()
    assert first.stopped and FakeListener.instances[-1] is not first


def test_disabled_scenario_does_not_grab_hotkey(state, monkeypatch):
    sc = {"name": "N", "enabled": False, "trigger": {"type": "hotkey", "keys": "Ctrl+Alt+N"},
          "actions": [{"do": "notify", "text": "x"}]}
    _engine(state, monkeypatch, [sc])
    assert list(FakeListener.instances[-1].keys) == [1000]  # занята только клавиша радиального меню


def test_schedule_fires_once_per_minute_window(state, monkeypatch):
    sc = {"name": "S", "trigger": {"type": "schedule", "mode": "daily", "at": "09:00"},
          "actions": [{"do": "notify", "text": "утро"}]}
    eng, calls = _engine(state, monkeypatch, [sc])
    t = datetime(2026, 11, 9, 9, 0, 20)
    eng.tick(t)
    eng.tick(t + timedelta(seconds=15))
    assert calls == [("notify", "утро")]
    eng.tick(datetime(2026, 11, 9, 14, 0))
    assert len(calls) == 1


def test_clipboard_trigger_runs_and_does_not_loop(state, monkeypatch, qapp):
    sc = {"name": "C", "trigger": {"type": "clipboard", "match": "contains", "text": "utm_"},
          "actions": [{"do": "clip_transform", "mode": "strip_utm"}, {"do": "notify", "text": "ok"}]}
    eng, calls = _engine(state, monkeypatch, [sc])
    store = {"t": ""}
    eng.env.get_clipboard = lambda: store["t"]
    eng.env.set_clipboard = lambda v: store.update(t=v)
    eng._clipboard = type("C", (), {"text": lambda self: store["t"]})()
    store["t"] = "https://a.com/?utm_source=x&id=1"
    eng._on_clipboard()
    assert store["t"] == "https://a.com/?id=1" and calls == [("notify", "ok")]
    eng._on_clipboard()  # сразу после своего запуска: тишина
    assert calls == [("notify", "ok")]


def test_failing_step_stops_chain_and_reports(state, monkeypatch):
    sc = {"name": "F", "trigger": {"type": "startup"},
          "actions": [{"do": "sort", "folder": "/нет/такой/папки"}, {"do": "notify", "text": "не дойдёт"}]}
    eng, calls = _engine(state, monkeypatch, [sc])
    toasts = []
    state.toast.connect(lambda t, k: toasts.append((t, k)))
    res = eng.run(state.scenarios[0])
    assert not res.ok and calls == [] and toasts and toasts[-1][1] == "danger"


def test_dangerous_open_target_is_refused(state, monkeypatch):
    sc = {"name": "D", "trigger": {"type": "startup"},
          "actions": [{"do": "open", "target": "ms-msdt:/id PCWDiagnostic"}]}
    eng, calls = _engine(state, monkeypatch, [sc])
    res = eng.run(state.scenarios[0])
    assert not res.ok and calls == []
