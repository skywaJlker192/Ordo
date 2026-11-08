"""Радиальное меню: настройки, список пунктов и геометрия секторов (без Qt, чтобы проверять тестами)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .errors import ConfigError
from .hotkeys import normalize

MAX_ITEMS = 8
DEFAULT_HOTKEY = "Ctrl+Alt+Space"

# встроенные пункты: id -> (подпись, иконка)
BUILTINS: Dict[str, Tuple[str, str]] = {
    "sort": ("Разобрать", "layers"),
    "undo": ("Откатить", "undo"),
    "watch": ("Слежение", "pause"),
    "downloads": ("Загрузки", "folder"),
    "open": ("Открыть Ordo", "home"),
}
DEFAULT_ITEMS = ["builtin:sort", "builtin:undo", "builtin:watch", "builtin:downloads", "builtin:open"]


@dataclass
class Radial:
    enabled: bool = True
    hotkey: str = DEFAULT_HOTKEY
    items: List[str] = field(default_factory=lambda: list(DEFAULT_ITEMS))


def default_radial() -> Dict[str, Any]:
    return {"enabled": True, "hotkey": DEFAULT_HOTKEY, "items": list(DEFAULT_ITEMS)}


def parse_radial(raw: Any) -> Radial:
    """Проверка блока radial из конфига. Пустой или отсутствующий блок = значения по умолчанию."""
    if raw is None:
        return Radial()
    if not isinstance(raw, dict):
        raise ConfigError("radial: ожидал объект")
    hotkey = raw.get("hotkey", DEFAULT_HOTKEY)
    try:
        hotkey = normalize(str(hotkey))
    except ValueError as e:
        raise ConfigError(f"radial: {e}")
    items = raw.get("items", DEFAULT_ITEMS)
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        raise ConfigError("radial: items должен быть списком строк")
    if len(items) > MAX_ITEMS:
        raise ConfigError(f"radial: не больше {MAX_ITEMS} пунктов")
    if len(set(items)) != len(items):
        raise ConfigError("radial: пункты не должны повторяться")
    for it in items:
        kind, _, name = it.partition(":")
        if kind == "builtin":
            if name not in BUILTINS:
                raise ConfigError(f"radial: нет встроенного пункта «{name}»")
        elif kind != "scenario" or not name:
            raise ConfigError(f"radial: непонятный пункт «{it}» (нужно builtin:… или scenario:…)")
    return Radial(bool(raw.get("enabled", True)), hotkey, list(items))


def sector_at(dx: float, dy: float, count: int, inner: float, outer: float) -> Optional[int]:
    """Номер сектора под точкой (dx, dy от центра) или None. Сектор 0 смотрит вверх, дальше по часовой."""
    if count <= 0:
        return None
    r = math.hypot(dx, dy)
    if r < inner or r > outer:
        return None
    angle = math.degrees(math.atan2(dx, -dy)) % 360.0  # 0° = вверх, по часовой
    step = 360.0 / count
    return int(((angle + step / 2) % 360.0) // step)


def sector_center_angle(index: int, count: int) -> float:
    """Угол середины сектора в градусах (0° = вверх, по часовой)."""
    return index * 360.0 / count
