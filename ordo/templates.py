"""Шаблоны имён и путей: "{year}-{month}/{stem}.{real_ext}"."""
from __future__ import annotations

import re
import string
from typing import Mapping

from .errors import ConfigError

PLACEHOLDERS = (
    "name", "stem", "ext", "real_ext", "type", "year", "month", "day", "size_mb",
)

_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(value: object) -> str:
    """Значение плейсхолдера не должно ломать путь (особенно на Windows)."""
    return _BAD_CHARS.sub("_", str(value)).strip().rstrip(".")


def validate(template: str, where: str) -> None:
    try:
        fields = [f for _, f, _, _ in string.Formatter().parse(template) if f]
    except ValueError as e:
        raise ConfigError(f"{where}: сломанный шаблон {template!r} ({e})")
    for f in fields:
        if f not in PLACEHOLDERS:
            raise ConfigError(
                f"{where}: неизвестный плейсхолдер {{{f}}}. "
                f"Доступны: {', '.join('{' + p + '}' for p in PLACEHOLDERS)}"
            )


def render(template: str, values: Mapping[str, object]) -> str:
    return template.format_map({k: sanitize(v) for k, v in values.items()})
