"""Логика сценариев: проверка конфига, расписание, буфер, безопасность открытия, запуск цепочки."""
from datetime import datetime

import pytest

from ordo.config_io import default_config, save_raw, validate_scenario
from ordo.describe import describe_scenario, describe_step, describe_trigger
from ordo.errors import ConfigError
from ordo.hotkeys import HotkeyListener, MOD_CONTROL, MOD_ALT, MOD_NOREPEAT, WM_HOTKEY, normalize, parse_hotkey
from ordo.rules import parse_config
from ordo.scenarios import (
    Env, expand, is_due, match_clipboard, parse_scenario, resolve_open_target, run_actions,
    templates, transform_clipboard,
)


def sc(trigger, *actions, name="тест"):
    return {"name": name, "trigger": trigger, "actions": list(actions) or [{"do": "notify", "text": "ок"}]}


# ---------- горячие клавиши ----------

@pytest.mark.parametrize("raw, canon", [
    ("ctrl+alt+l", "Ctrl+Alt+L"), ("Alt + Ctrl + L", "Ctrl+Alt+L"), ("win+shift+f8", "Shift+Win+F8"),
    ("CTRL+Space", "Ctrl+Space"), ("meta+1", "Win+1"), ("F12", "F12"), ("ctrl+del", "Ctrl+Delete"),
])
def test_normalize_hotkey(raw, canon):
    assert normalize(raw) == canon


def test_parse_hotkey_gives_windows_codes():
    assert parse_hotkey("Ctrl+Alt+L") == (MOD_CONTROL | MOD_ALT, ord("L"))
    assert parse_hotkey("F8") == (0, 0x77)


@pytest.mark.parametrize("bad", ["", "L", "Ctrl", "Ctrl+Alt", "Ctrl+Банан", "Foo+L", "Ctrl+Ж"])
def test_bad_hotkeys_rejected_with_readable_text(bad):
    with pytest.raises(ValueError) as e:
        parse_hotkey(bad)
    assert str(e.value)


class FakeListener(HotkeyListener):
    """WinAPI заменён очередью: проверяем только логику регистрации и цикла."""

    def __init__(self, *a, busy=(), **k):
        super().__init__(*a, **k)
        import queue
        self.q, self.busy, self.reg, self.unreg = queue.Queue(), set(busy), [], []

    def _api_setup(self): pass
    def _api_register(self, hid, mods, vk):
        if hid in self.busy:
            return False
        self.reg.append((hid, mods, vk))
        return True
    def _api_unregister(self, hid): self.unreg.append(hid)
    def _api_wait_message(self): return self.q.get(timeout=3)
    def _api_post_quit(self): self.q.put(None)


def test_listener_registers_dispatches_reports_busy_and_cleans_up():
    pressed, failed = [], []
    lst = FakeListener({1: "Ctrl+Alt+L", 2: "Ctrl+Alt+K", 3: "хрень"}, pressed.append,
                       lambda hid, keys: failed.append(hid), busy={2})
    lst.start()
    lst._ready.wait(2)
    lst.q.put((WM_HOTKEY, 1))
    lst.q.put((WM_HOTKEY, 2))   # не зарегистрирован: игнорируем
    lst.q.put((0x0111, 1))      # не WM_HOTKEY: игнорируем
    lst.stop()
    assert pressed == [1] and sorted(failed) == [2, 3]
    assert lst.reg == [(1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("L"))]
    assert lst.unreg == [1] and not lst.is_alive()


# ---------- проверка конфига ----------

def test_valid_scenarios_of_every_kind_parse():
    for t in templates():
        assert validate_scenario(t) is None, t["name"]
    assert parse_scenario(sc({"type": "startup"})).trigger == {"type": "startup"}
    assert parse_scenario(sc({"type": "clipboard", "match": "regex", "text": r"^\d+$"})).trigger["match"] == "regex"


@pytest.mark.parametrize("bad, part", [
    (sc({"type": "teleport"}), "триггер"),
    (sc({"type": "hotkey", "keys": "L"}), "модификатор"),
    (sc({"type": "schedule", "mode": "every", "minutes": 0}), "от 1 до 1440"),
    (sc({"type": "schedule", "mode": "every", "minutes": "много"}), "числом"),
    (sc({"type": "schedule", "mode": "daily", "at": "25:99"}), "ЧЧ:ММ"),
    (sc({"type": "schedule", "mode": "monthly"}), "mode"),
    (sc({"type": "clipboard", "match": "regex", "text": "("}), "регулярное"),
    (sc({"type": "startup"}, {"do": "open", "target": " "}), "укажи путь"),
    (sc({"type": "startup"}, {"do": "notify", "text": ""}), "нужен текст"),
    (sc({"type": "startup"}, {"do": "clip_transform", "mode": "x"}), "mode"),
    (sc({"type": "startup"}, {"do": "format_c"}), "неизвестное действие"),
    ({"name": "пусто", "trigger": {"type": "startup"}, "actions": []}, "хотя бы одно действие"),
    ({"name": "без триггера", "actions": [{"do": "notify", "text": "a"}]}, "триггера"),
])
def test_invalid_scenarios_have_readable_errors(bad, part):
    err = validate_scenario(bad)
    assert err is not None and part in err


def test_scenarios_saved_with_config_and_bad_ones_block_saving(tmp_path):
    path = tmp_path / "config.json"
    cfg = default_config()
    cfg["scenarios"] = templates()
    save_raw(path, cfg)
    assert len(parse_config(cfg).scenarios) == len(templates())
    cfg["scenarios"] = [sc({"type": "hotkey", "keys": "oops"})]
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ConfigError):
        save_raw(path, cfg)
    assert path.read_text(encoding="utf-8") == before


# ---------- расписание ----------

def dt(h, m, d=3, s=0):  # 2026-11-03 вторник; 2026-11-07 суббота
    return datetime(2026, 11, d, h, m, s)


def test_every_n_minutes_needs_baseline_and_interval():
    t = {"type": "schedule", "mode": "every", "minutes": 30}
    assert is_due(t, None, dt(10, 0)) is False                # без точки отсчёта не стреляем
    assert is_due(t, dt(10, 0), dt(10, 29)) is False
    assert is_due(t, dt(10, 0), dt(10, 30)) is True


def test_daily_runs_once_inside_window_and_does_not_catch_up():
    t = {"type": "schedule", "mode": "daily", "at": "09:00"}
    assert is_due(t, None, dt(8, 59)) is False
    assert is_due(t, None, dt(9, 0)) is True
    assert is_due(t, None, dt(9, 1, s=59)) is True
    assert is_due(t, dt(9, 0), dt(9, 1)) is False             # уже запускали сегодня
    assert is_due(t, None, dt(9, 2)) is False                 # проспали окно: догонять не будем
    assert is_due(t, None, dt(15, 0)) is False
    assert is_due(t, dt(9, 0, d=2), dt(9, 0)) is True         # вчерашний запуск не мешает


def test_weekdays_skip_weekend():
    t = {"type": "schedule", "mode": "weekdays", "at": "09:00"}
    assert is_due(t, None, dt(9, 0, d=6)) is True             # пятница
    assert is_due(t, None, dt(9, 0, d=7)) is False            # суббота
    assert is_due(t, None, dt(9, 0, d=8)) is False            # воскресенье
    assert is_due({"type": "hotkey", "keys": "Ctrl+L"}, None, dt(9, 0)) is False


# ---------- буфер ----------

def test_clipboard_matching():
    any_text = {"type": "clipboard", "match": "contains", "text": ""}
    assert match_clipboard(any_text, "что угодно") and not match_clipboard(any_text, "   ")
    contains = {"type": "clipboard", "match": "contains", "text": "HTTP"}
    assert match_clipboard(contains, "see https://x.io") and not match_clipboard(contains, "ничего")
    rx = {"type": "clipboard", "match": "regex", "text": r"^\d{4}$"}
    assert match_clipboard(rx, "2026") and not match_clipboard(rx, "20266")


def test_strip_tracking_from_links_keeps_real_params_and_punctuation():
    text = ("Смотри https://shop.ru/item?id=5&utm_source=tg&utm_medium=x&fbclid=AB&color=red#top, "
            "и ещё (https://a.io/p?gclid=1).")
    out = transform_clipboard("strip_utm", text)
    assert out == "Смотри https://shop.ru/item?id=5&color=red#top, и ещё (https://a.io/p)."
    assert transform_clipboard("strip_utm", "https://a.io/") == "https://a.io/"


def test_other_clipboard_transforms():
    assert transform_clipboard("trim", "  a b \n") == "a b"
    assert transform_clipboard("single_line", "a\n  b\r\n\tc") == "a b c"
    assert transform_clipboard("lower", "АБв") == "абв" and transform_clipboard("upper", "абВ") == "АБВ"


def test_expand_placeholders_and_lazy_clipboard():
    calls = []
    def clip():
        calls.append(1)
        return "БУФЕР"
    now = datetime(2026, 11, 3, 9, 5)
    assert expand("{date} {time}: нет подстановок буфера", clip, now) == "03.11.2026 09:05: нет подстановок буфера"
    assert calls == []                                       # буфер не читали зря
    assert expand("[{clipboard}]", clip, now) == "[БУФЕР]" and calls == [1]
    assert expand("{unknown} {{x}}", clip, now) == "{unknown} {{x}}"


# ---------- безопасность открытия ----------

@pytest.mark.parametrize("target", [
    "ms-msdt:/id PCWDiagnostic", "file:///C:/Windows/System32/calc.exe", "javascript:alert(1)",
    "ftp://x.io/a", "vscode://x", "shell:startup",
])
def test_dangerous_schemes_are_refused(target):
    with pytest.raises(ValueError, match="запрещена"):
        resolve_open_target(target)


def test_open_allows_web_and_existing_paths_only(tmp_path):
    assert resolve_open_target("https://example.com/a?b=1") == "https://example.com/a?b=1"
    assert resolve_open_target("mailto:a@b.c") == "mailto:a@b.c"
    f = tmp_path / "doc.txt"
    f.write_text("x")
    assert resolve_open_target(str(f)) == str(f)
    with pytest.raises(ValueError, match="не найдено"):
        resolve_open_target(str(tmp_path / "нет.txt"))
    with pytest.raises(ValueError, match="перевод"):
        resolve_open_target("https://a.io\nhttps://b.io")
    with pytest.raises(ValueError):
        resolve_open_target("   ")


def test_windows_drive_letter_is_not_a_scheme(monkeypatch):
    # «C:\Users» не должен ловиться как схема «c:»; путь просто не найден в Linux
    with pytest.raises(ValueError, match="не найдено"):
        resolve_open_target(r"C:\Users\Архип\Downloads")


# ---------- запуск цепочки ----------

class Rec:
    def __init__(self, clip=""):
        self.clip, self.log = clip, []
        self.env = Env(notify=lambda t: self.log.append(("notify", t)),
                       open_target=lambda t: self.log.append(("open", t)),
                       get_clipboard=lambda: self.clip,
                       set_clipboard=self._set,
                       sort=lambda f: self.log.append(("sort", f)))

    def _set(self, text):
        self.clip = text
        self.log.append(("clip", text))


def test_chain_runs_in_order_with_shared_clipboard():
    rec = Rec("https://a.io/?utm_source=x")
    s = parse_scenario(sc({"type": "startup"},
                          {"do": "clip_transform", "mode": "strip_utm"},
                          {"do": "notify", "text": "Готово: {clipboard}"},
                          {"do": "sort", "folder": "~/Downloads"}))
    res = run_actions(s.actions, rec.env, datetime(2026, 11, 3, 9, 0))
    assert res.ok and res.done == 3
    assert rec.log == [("clip", "https://a.io/"), ("notify", "Готово: https://a.io/"), ("sort", "~/Downloads")]


def test_chain_stops_at_first_error_and_reports_which_step():
    rec = Rec("javascript:alert(1)")
    s = parse_scenario(sc({"type": "startup"},
                          {"do": "notify", "text": "до"},
                          {"do": "open", "target": "{clipboard}"},
                          {"do": "notify", "text": "после"}))
    res = run_actions(s.actions, rec.env)
    assert res.done == 1 and not res.ok
    assert "действие 2" in res.error and "запрещена" in res.error
    assert rec.log == [("notify", "до")]                      # «после» не выполнилось


def test_open_action_passes_resolved_target(tmp_path):
    rec = Rec()
    (tmp_path / "x.txt").write_text("1")
    res = run_actions([{"do": "open", "target": str(tmp_path / "x.txt")}], rec.env)
    assert res.ok and rec.log == [("open", str(tmp_path / "x.txt"))]


# ---------- описания ----------

def test_descriptions_in_plain_russian():
    assert describe_trigger({"type": "hotkey", "keys": "Ctrl+Alt+L"}) == "нажато Ctrl+Alt+L"
    assert describe_trigger({"type": "schedule", "mode": "every", "minutes": 15}) == "каждые 15 мин"
    assert describe_trigger({"type": "schedule", "mode": "weekdays", "at": "09:00"}) == "по будням в 09:00"
    assert describe_trigger({"type": "clipboard", "match": "contains", "text": ""}) == "скопирован любой текст"
    assert describe_step({"do": "sort", "folder": ""}) == "разобрать все папки"
    when, what = describe_scenario(templates()[0])
    assert when == "нажато Ctrl+Alt+L" and what.count("→") == 1
    for t in templates():  # ничего не падает и нет «None»
        assert "None" not in " ".join(describe_scenario(t))
    assert describe_scenario({"name": "пустой"})  # не падает на недозаполненном
