"""Чтение и безопасное сохранение конфига. Интерфейс работает с «сырым» JSON-словарём."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import ConfigError
from .rules import parse_config

PRESET = Path(__file__).parent / "presets" / "downloads.json"


def default_config() -> Dict[str, Any]:
    return json.loads(PRESET.read_text(encoding="utf-8"))


def load_raw(path: Path) -> Dict[str, Any]:
    """Конфиг как словарь. Если файла ещё нет, вернёт пресет (на диск не пишет)."""
    if not path.exists():
        return default_config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: невалидный JSON (строка {e.lineno}): {e.msg}")
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: конфиг должен быть JSON-объектом")
    data.setdefault("watch", [])
    data.setdefault("rules", [])
    data.setdefault("scenarios", [])
    return data


def save_raw(path: Path, data: Dict[str, Any]) -> None:
    """Проверяет конфиг, делает .bak и пишет атомарно (при сбое старый файл цел)."""
    parse_config(data)  # бросит ConfigError с понятным текстом
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def ensure_config(path: Path) -> Dict[str, Any]:
    """При первом запуске создаёт конфиг из пресета."""
    if not path.exists():
        save_raw(path, default_config())
    return load_raw(path)


def validate_scenario(raw: Dict[str, Any]) -> Optional[str]:
    """Текст ошибки или None, если сценарий корректен."""
    try:
        parse_config({"watch": [], "rules": [], "scenarios": [raw]})
    except ConfigError as e:
        return str(e)
    return None


def validate_rule(raw: Dict[str, Any]) -> Optional[str]:
    """Текст ошибки или None, если правило корректно."""
    try:
        parse_config({"watch": [], "rules": [raw]})
    except ConfigError as e:
        return str(e)
    return None
