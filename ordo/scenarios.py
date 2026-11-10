"""Сценарии: «когда [триггер] → сделать [цепочку действий]». Чистая логика без Qt, всё проверяется тестами."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import ConfigError
from .hotkeys import normalize
from .paths import expand as expand_path

TRIGGER_TYPES = ("hotkey", "schedule", "clipboard", "startup")
ACTION_TYPES = ("sort", "open", "notify", "copy_text", "clip_transform")
SCHEDULE_MODES = ("every", "daily", "weekdays")
CLIP_MATCH = ("contains", "regex")
CLIP_MODES = ("trim", "single_line", "lower", "upper", "strip_utm")
SAFE_SCHEMES = ("http", "https", "mailto")
SCHEDULE_WINDOW = timedelta(minutes=2)  # насколько можно опоздать с запуском «в 09:00»


@dataclass
class Scenario:
    name: str
    trigger: Dict[str, Any]
    actions: List[Dict[str, Any]]
    enabled: bool = True


# ---------- проверка конфига ----------

def _time(value: Any, where: str) -> str:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ConfigError(f"{where}: время нужно в формате ЧЧ:ММ, например 09:30")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def validate_trigger(t: Any, where: str) -> Dict[str, Any]:
    if not isinstance(t, dict):
        raise ConfigError(f"{where}: у сценария нет триггера (когда запускать)")
    kind = t.get("type")
    if kind not in TRIGGER_TYPES:
        raise ConfigError(f"{where}: неизвестный триггер {kind!r}. Доступны: {', '.join(TRIGGER_TYPES)}")
    out: Dict[str, Any] = {"type": kind}
    if kind == "hotkey":
        try:
            out["keys"] = normalize(str(t.get("keys", "")))
        except ValueError as e:
            raise ConfigError(f"{where}: {e}")
    elif kind == "schedule":
        mode = t.get("mode")
        if mode not in SCHEDULE_MODES:
            raise ConfigError(f"{where}: расписание: mode должен быть {', '.join(SCHEDULE_MODES)}")
        out["mode"] = mode
        if mode == "every":
            try:
                minutes = int(t.get("minutes"))
            except (TypeError, ValueError):
                raise ConfigError(f"{where}: «каждые N минут»: N должно быть числом")
            if not 1 <= minutes <= 1440:
                raise ConfigError(f"{where}: «каждые N минут»: N от 1 до 1440")
            out["minutes"] = minutes
        else:
            out["at"] = _time(t.get("at"), where)
    elif kind == "clipboard":
        match = t.get("match", "contains")
        if match not in CLIP_MATCH:
            raise ConfigError(f"{where}: буфер: match должен быть contains или regex")
        text = str(t.get("text", ""))
        if match == "regex" and text:
            try:
                re.compile(text)
            except re.error as e:
                raise ConfigError(f"{where}: сломанное регулярное выражение в буфере ({e})")
        out.update(match=match, text=text)
    return out


def validate_action(a: Any, where: str) -> Dict[str, Any]:
    if not isinstance(a, dict):
        raise ConfigError(f"{where}: действие должно быть объектом")
    kind = a.get("do")
    if kind not in ACTION_TYPES:
        raise ConfigError(f"{where}: неизвестное действие {kind!r}. Доступны: {', '.join(ACTION_TYPES)}")
    out: Dict[str, Any] = {"do": kind}
    if kind == "sort":
        out["folder"] = str(a.get("folder", ""))
    elif kind == "open":
        target = str(a.get("target", "")).strip()
        if not target:
            raise ConfigError(f"{where}: «открыть»: укажи путь, программу или ссылку")
        out["target"] = target
    elif kind in ("notify", "copy_text"):
        text = str(a.get("text", ""))
        if not text.strip():
            raise ConfigError(f"{where}: «{'уведомление' if kind == 'notify' else 'скопировать'}»: нужен текст")
        out["text"] = text
    else:  # clip_transform
        if a.get("mode") not in CLIP_MODES:
            raise ConfigError(f"{where}: обработка буфера: mode должен быть {', '.join(CLIP_MODES)}")
        out["mode"] = a["mode"]
    return out


def parse_scenario(raw: Any, index: int = 1) -> Scenario:
    if not isinstance(raw, dict):
        raise ConfigError(f"сценарий №{index}: должен быть объектом")
    name = str(raw.get("name") or f"Сценарий {index}")
    where = f"сценарий «{name}»"
    trigger = validate_trigger(raw.get("trigger"), where)
    raw_actions = raw.get("actions") or []
    if not raw_actions:
        raise ConfigError(f"{where}: добавь хотя бы одно действие")
    actions = [validate_action(a, f"{where}, действие {i}") for i, a in enumerate(raw_actions, 1)]
    return Scenario(name, trigger, actions, bool(raw.get("enabled", True)))


# ---------- когда запускать ----------

def is_due(trigger: Dict[str, Any], last_run: Optional[datetime], now: datetime) -> bool:
    """Пора ли запускать сценарий по расписанию. last_run: когда он запускался в прошлый раз."""
    if trigger.get("type") != "schedule":
        return False
    mode = trigger.get("mode")
    if mode == "every":
        return last_run is not None and now - last_run >= timedelta(minutes=int(trigger["minutes"]))
    h, m = map(int, trigger["at"].split(":"))
    target = datetime.combine(now.date(), dtime(h, m))
    if mode == "weekdays" and now.weekday() >= 5:
        return False
    in_window = target <= now < target + SCHEDULE_WINDOW
    return in_window and (last_run is None or last_run < target)


def match_clipboard(trigger: Dict[str, Any], text: str) -> bool:
    if trigger.get("type") != "clipboard" or not text.strip():
        return False
    pattern = trigger.get("text", "")
    if not pattern:
        return True
    if trigger.get("match") == "regex":
        return re.search(pattern, text, re.IGNORECASE) is not None
    return pattern.lower() in text.lower()


# ---------- что делать ----------

_PLACEHOLDER = re.compile(r"\{(clipboard|date|time)\}")
_TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|yclid|dclid|msclkid|mc_cid|mc_eid|_hsenc|_hsmi|igshid|ref_src)$", re.I)
_URL = re.compile(r"https?://[^\s<>\"']+")


def expand(text: str, get_clipboard: Callable[[], str], now: datetime) -> str:
    """Подставляет {clipboard}, {date}, {time}. Буфер читается, только если он нужен."""
    def repl(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key == "clipboard":
            return get_clipboard()
        return now.strftime("%d.%m.%Y" if key == "date" else "%H:%M")
    return _PLACEHOLDER.sub(repl, text)


def _strip_url(m: "re.Match[str]") -> str:
    url = m.group(0)
    tail = ""
    while url and url[-1] in ".,;:!?)»":
        tail = url[-1] + tail
        url = url[:-1]
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k)]
    return urlunsplit(parts._replace(query=urlencode(query))) + tail


def transform_clipboard(mode: str, text: str) -> str:
    if mode == "trim":
        return text.strip()
    if mode == "single_line":
        return " ".join(text.split())
    if mode == "lower":
        return text.lower()
    if mode == "upper":
        return text.upper()
    if mode == "strip_utm":
        return _URL.sub(_strip_url, text)
    raise ValueError(f"неизвестный режим {mode!r}")


def resolve_open_target(target: str) -> str:
    """Что можно открывать: http/https/mailto и существующие пути. Остальные схемы (ms-msdt:, file: …) нет."""
    t = target.strip()
    if not t:
        raise ValueError("нечего открывать: пусто")
    if "\n" in t or "\r" in t:
        raise ValueError("в пути или ссылке не должно быть переводов строки")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", t) and not re.match(r"^[A-Za-z]:[\\/]", t):
        scheme = t.split(":", 1)[0].lower()
        if scheme not in SAFE_SCHEMES:
            raise ValueError(f"схема «{scheme}:» запрещена, открываю только http, https и mailto")
        return t
    path = expand_path(t)
    if not path.exists():
        raise ValueError(f"не найдено: {t}")
    return str(path)


@dataclass
class Env:
    """Всё, что сценарий делает во внешнем мире. Окно подставляет настоящие функции, тесты свои."""
    notify: Callable[[str], None]
    open_target: Callable[[str], None]
    get_clipboard: Callable[[], str]
    set_clipboard: Callable[[str], None]
    sort: Callable[[str], None]


@dataclass
class RunResult:
    done: int = 0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def run_actions(actions: List[Dict[str, Any]], env: Env, now: Optional[datetime] = None) -> RunResult:
    """Выполняет действия по порядку. На первой ошибке останавливается: следующие шаги могли на неё опираться."""
    now = now or datetime.now()
    result = RunResult()
    for i, a in enumerate(actions, 1):
        try:
            _do(a, env, now)
        except Exception as e:  # noqa: BLE001: показываем причину пользователю
            result.error = f"действие {i} ({a.get('do')}): {e}"
            break
        result.done += 1
    return result


def _do(a: Dict[str, Any], env: Env, now: datetime) -> None:
    kind = a.get("do")
    ex = lambda text: expand(text, env.get_clipboard, now)  # noqa: E731
    if kind == "sort":
        env.sort(ex(a.get("folder", "")))
    elif kind == "open":
        env.open_target(resolve_open_target(ex(a["target"])))
    elif kind == "notify":
        env.notify(ex(a["text"]))
    elif kind == "copy_text":
        env.set_clipboard(ex(a["text"]))
    elif kind == "clip_transform":
        env.set_clipboard(transform_clipboard(a["mode"], env.get_clipboard()))
    else:
        raise ValueError(f"неизвестное действие {kind!r}")


# ---------- готовые шаблоны ----------

def templates() -> List[Dict[str, Any]]:
    return [
        {"name": "Чистая ссылка", "enabled": True,
         "description": "Скопировал ссылку, нажал Ctrl+Alt+L, и из неё пропали utm_ и прочий трекинг",
         "trigger": {"type": "hotkey", "keys": "Ctrl+Alt+L"},
         "actions": [{"do": "clip_transform", "mode": "strip_utm"},
                     {"do": "notify", "text": "Ссылка очищена от трекинга"}]},
        {"name": "Текст в одну строку", "enabled": True,
         "description": "Склеивает скопированный многострочный текст в одну строку",
         "trigger": {"type": "hotkey", "keys": "Ctrl+Alt+J"},
         "actions": [{"do": "clip_transform", "mode": "single_line"},
                     {"do": "notify", "text": "Текст в буфере теперь в одну строку"}]},
        {"name": "Ссылка из буфера в браузер", "enabled": True,
         "description": "Открывает в браузере ссылку, которая лежит в буфере обмена",
         "trigger": {"type": "hotkey", "keys": "Ctrl+Alt+B"},
         "actions": [{"do": "open", "target": "{clipboard}"}]},
        {"name": "Утренняя уборка", "enabled": True,
         "description": "По будням в 09:00 разбирает все папки под присмотром",
         "trigger": {"type": "schedule", "mode": "weekdays", "at": "09:00"},
         "actions": [{"do": "sort", "folder": ""},
                     {"do": "notify", "text": "Папки разобраны"}]},
        {"name": "Уборка каждый час", "enabled": True,
         "description": "Раз в час проверяет папки, даже если слежение выключено",
         "trigger": {"type": "schedule", "mode": "every", "minutes": 60},
         "actions": [{"do": "sort", "folder": ""}]},
        {"name": "Открыть Загрузки", "enabled": True,
         "description": "Быстро открывает папку «Загрузки» в проводнике",
         "trigger": {"type": "hotkey", "keys": "Ctrl+Alt+D"},
         "actions": [{"do": "open", "target": "~/Downloads"}]},
    ]
