"""Радиальное меню: настройки, геометрия секторов, поведение виджета и подключение к окну."""
import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="ordo-test-xdg-"))

from ordo.config_io import default_config, save_raw  # noqa: E402
from ordo.errors import ConfigError  # noqa: E402
from ordo.radial import MAX_ITEMS, parse_radial, sector_at, sector_center_angle  # noqa: E402
from ordo.rules import parse_config  # noqa: E402


def test_default_radial_is_valid_and_in_default_config():
    r = parse_radial(None)
    assert r.enabled and r.hotkey == "Ctrl+Alt+Space" and len(r.items) <= MAX_ITEMS
    assert parse_config(default_config()).radial.items == r.items


@pytest.mark.parametrize("bad", [
    {"hotkey": "Space"}, {"hotkey": "Ctrl+Банан"}, {"items": "builtin:sort"}, {"items": [1]},
    {"items": ["builtin:nope"]}, {"items": ["scenario:"]}, {"items": ["что-то"]},
    {"items": ["builtin:sort", "builtin:sort"]}, {"items": [f"scenario:{i}" for i in range(9)]}, [],
])
def test_bad_radial_rejected(bad):
    with pytest.raises(ConfigError):
        parse_radial(bad)


def test_hotkey_is_normalized_and_conflict_with_scenario_detected():
    assert parse_radial({"hotkey": "alt+ctrl+space"}).hotkey == "Ctrl+Alt+Space"
    cfg = {"watch": [], "rules": [], "radial": {"hotkey": "Ctrl+Alt+K", "items": ["builtin:sort"]},
           "scenarios": [{"name": "A", "trigger": {"type": "hotkey", "keys": "ctrl+alt+k"},
                          "actions": [{"do": "notify", "text": "x"}]}]}
    with pytest.raises(ConfigError, match="занято"):
        parse_config(cfg)
    cfg["radial"]["enabled"] = False  # выключенное меню клавишу не занимает
    assert parse_config(cfg)


@pytest.mark.parametrize("n", [1, 2, 3, 5, 8])
def test_every_sector_is_found_at_its_own_center_and_dead_zones_are_empty(n):
    import math
    for i in range(n):
        a = math.radians(sector_center_angle(i, n))
        dx, dy = math.sin(a) * 100, -math.cos(a) * 100
        assert sector_at(dx, dy, n, 60, 150) == i
    assert sector_at(0, 0, n, 60, 150) is None          # центр
    assert sector_at(0, -400, n, 60, 150) is None       # далеко снаружи
    assert sector_at(5, 5, 0, 60, 150) is None


def test_sector_zero_is_up_and_order_is_clockwise():
    assert sector_at(0, -100, 4, 60, 150) == 0     # вверх
    assert sector_at(100, 0, 4, 60, 150) == 1      # вправо
    assert sector_at(0, 100, 4, 60, 150) == 2      # вниз
    assert sector_at(-100, 0, 4, 60, 150) == 3     # влево


# ---------- виджет и окно ----------

pytest.importorskip("PyQt5")
from PyQt5.QtCore import QPoint, Qt  # noqa: E402
from PyQt5.QtGui import QKeyEvent  # noqa: E402
from PyQt5.QtCore import QEvent  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from ordo.gui import theme  # noqa: E402
from ordo.gui.main_window import MainWindow  # noqa: E402
from ordo.gui.radial_menu import INNER, OUTER, RadialMenu  # noqa: E402
from ordo.gui.state import AppState  # noqa: E402

ITEMS = [{"id": f"builtin:{k}", "label": k, "icon": "bolt"} for k in ("sort", "undo", "watch", "open")]


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    theme.apply(app)
    return app


def _open(menu, qapp):
    menu.set_items(ITEMS)
    menu.popup(QPoint(400, 300))
    qapp.processEvents()


def test_click_on_sector_emits_its_id_and_closes(qapp):
    m = RadialMenu()
    got = []
    m.chosen.connect(got.append)
    _open(m, qapp)
    c = m.center
    pos = QPoint(int(c.x() + (INNER + OUTER) / 2), int(c.y()))   # правый сектор = №1
    QTest.mouseMove(m, pos)
    m._sync_hover(pos)
    QTest.mouseClick(m, Qt.LeftButton, Qt.NoModifier, pos)
    assert got == ["builtin:undo"] and m._closing


def test_click_in_center_or_right_button_closes_without_choosing(qapp):
    m = RadialMenu()
    got = []
    m.chosen.connect(got.append)
    _open(m, qapp)
    QTest.mouseClick(m, Qt.LeftButton, Qt.NoModifier, QPoint(int(m.center.x()), int(m.center.y())))
    assert got == [] and m._closing


def test_number_keys_and_escape(qapp):
    m = RadialMenu()
    got = []
    m.chosen.connect(got.append)
    _open(m, qapp)
    m.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_9, Qt.NoModifier))   # такого пункта нет
    assert got == [] and not m._closing
    m.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_3, Qt.NoModifier))
    assert got == ["builtin:watch"]
    m2 = RadialMenu()
    _open(m2, qapp)
    m2.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    assert m2._closing


def test_hover_level_eases_toward_target_not_jumps(qapp):
    m = RadialMenu()
    _open(m, qapp)
    m._hover = 1
    m._step()
    first = m._level[1]
    assert 0 < first < 0.5
    for _ in range(60):
        m._step()
    assert m._level[1] > 0.99


def test_menu_stays_inside_screen_near_corner(qapp):
    m = RadialMenu()
    m.set_items(ITEMS)
    m.popup(QPoint(0, 0))
    area = QApplication.primaryScreen().availableGeometry()
    assert area.contains(m.geometry().topLeft()) and m.geometry().right() <= area.right() + 1


def test_empty_menu_does_not_show(qapp):
    m = RadialMenu()
    m.set_items([])
    m.popup(QPoint(100, 100))
    assert not m.isVisible()


@pytest.fixture
def win(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("ORDO_HOME", str(tmp_path / "home"))
    path = tmp_path / "home" / "config.json"
    cfg = default_config()
    cfg["watch"] = []
    cfg["scenarios"] = [{"name": "Привет", "trigger": {"type": "startup"},
                         "actions": [{"do": "notify", "text": "hi"}]}]
    cfg["radial"] = {"enabled": True, "hotkey": "Ctrl+Alt+Space",
                     "items": ["builtin:sort", "scenario:Привет", "scenario:Удалённый", "builtin:watch"]}
    save_raw(path, cfg)
    st = AppState(path)
    w = MainWindow(st, tray_available=False)
    yield w
    st.shutdown()


def test_window_builds_items_skipping_deleted_scenarios(win):
    ids = [i["id"] for i in win.radial_items()]
    assert ids == ["builtin:sort", "scenario:Привет", "builtin:watch"]
    assert win.radial_items()[2]["label"] == "Слежение"


def test_choosing_scenario_item_runs_it(win):
    calls = []
    win.automation.env.notify = calls.append
    win.run_radial("scenario:Привет")
    assert calls == ["hi"]


def test_settings_card_saves_selection_and_rejects_conflicts(win, monkeypatch):
    from ordo.gui import radial_settings as rs
    shown = []
    monkeypatch.setattr(rs, "warn", lambda _p, t: shown.append(t))
    card = win.settings_page.findChild(rs.RadialCard)
    for b in card._boxes:
        b.setChecked(b.property("item_id") == "builtin:undo")
    assert win.state.raw["radial"]["items"] == ["builtin:undo"]
    card.toggle.setChecked(False)
    assert win.state.raw["radial"]["enabled"] is False
    card.keys.setText("Ctrl")  # без основной клавиши
    card.keys.editingFinished.emit()
    assert shown and win.state.raw["radial"]["hotkey"] == "Ctrl+Alt+Space"
