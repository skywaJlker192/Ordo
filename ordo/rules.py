"""Правила и конфиг: загрузка и проверка JSON."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

from . import templates
from .conditions import Condition, FileContext
from .errors import ConfigError
from .paths import expand
from .radial import Radial, parse_radial
from .scenarios import Scenario, parse_scenario

ACTION_KINDS = ("move", "copy", "rename", "trash")


@dataclass
class Action:
    kind: str
    to: str = ""         # для move / copy
    template: str = ""   # для rename


@dataclass
class Rule:
    name: str
    conditions: List[Condition]
    actions: List[Action]
    match: str = "all"        # all = И, any = ИЛИ
    enabled: bool = True
    stop: bool = True         # остановиться после этого правила
    description: str = ""

    def matches(self, ctx: FileContext) -> bool:
        results = (c.test(ctx) for c in self.conditions)
        return all(results) if self.match == "all" else any(results)


@dataclass
class WatchSpec:
    folder: Path
    settle_seconds: float = 3.0  # сколько файл должен «полежать» без изменений


@dataclass
class Config:
    watch: List[WatchSpec] = field(default_factory=list)
    rules: List[Rule] = field(default_factory=list)
    scenarios: List[Scenario] = field(default_factory=list)
    radial: Radial = field(default_factory=Radial)


def _parse_action(raw: Any, where: str) -> Action:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: действие должно быть объектом")
    kind = raw.get("do")
    if kind not in ACTION_KINDS:
        raise ConfigError(
            f"{where}: неизвестное действие {kind!r}. Доступны: {', '.join(ACTION_KINDS)}"
        )
    if kind in ("move", "copy"):
        to = raw.get("to")
        if not to or not isinstance(to, str):
            raise ConfigError(f"{where}: для {kind} нужно поле to (куда)")
        templates.validate(to, where)
        return Action(kind, to=to)
    if kind == "rename":
        tpl = raw.get("template")
        if not tpl or not isinstance(tpl, str):
            raise ConfigError(f"{where}: для rename нужно поле template")
        templates.validate(tpl, where)
        return Action(kind, template=tpl)
    return Action(kind)


def _parse_rule(raw: Any, index: int) -> Rule:
    if not isinstance(raw, dict):
        raise ConfigError(f"правило №{index}: должно быть объектом")
    name = str(raw.get("name") or f"Правило {index}")
    where = f"правило «{name}»"

    match = raw.get("match", "all")
    if match not in ("all", "any"):
        raise ConfigError(f"{where}: match должен быть all или any")

    raw_conds = raw.get("conditions") or []
    if not raw_conds:
        raise ConfigError(f"{where}: нужно хотя бы одно условие (иначе оно сработает на все файлы)")
    conditions = [
        Condition.from_dict(c, f"{where}, условие {i}") for i, c in enumerate(raw_conds, 1)
    ]

    raw_actions = raw.get("actions") or []
    if not raw_actions:
        raise ConfigError(f"{where}: нужно хотя бы одно действие")
    actions = [
        _parse_action(a, f"{where}, действие {i}") for i, a in enumerate(raw_actions, 1)
    ]
    for a in actions[:-1]:
        if a.kind == "trash":
            raise ConfigError(f"{where}: trash должен быть последним действием")

    return Rule(
        name=name,
        conditions=conditions,
        actions=actions,
        match=match,
        enabled=bool(raw.get("enabled", True)),
        stop=bool(raw.get("stop", True)),
        description=str(raw.get("description", "")),
    )


def parse_config(data: Any) -> Config:
    if not isinstance(data, dict):
        raise ConfigError("конфиг должен быть JSON-объектом")
    watch = []
    for i, w in enumerate(data.get("watch") or [], 1):
        if not isinstance(w, dict) or not w.get("folder"):
            raise ConfigError(f"watch №{i}: нужно поле folder")
        watch.append(WatchSpec(expand(w["folder"]), float(w.get("settle_seconds", 3.0))))
    rules = [_parse_rule(r, i) for i, r in enumerate(data.get("rules") or [], 1)]
    scenarios = [parse_scenario(s, i) for i, s in enumerate(data.get("scenarios") or [], 1)]
    radial = parse_radial(data.get("radial"))
    if radial.enabled and radial.items:
        for sc in scenarios:
            if sc.enabled and sc.trigger["type"] == "hotkey" and sc.trigger["keys"] == radial.hotkey:
                raise ConfigError(f"сочетание {radial.hotkey} занято и радиальным меню, и сценарием «{sc.name}»")
    return Config(watch=watch, rules=rules, scenarios=scenarios, radial=radial)


def load_config(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(f"конфиг не найден: {path}. Создай его командой: ordo init")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: невалидный JSON (строка {e.lineno}, столбец {e.colno}): {e.msg}")
    return parse_config(data)
