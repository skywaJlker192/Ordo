"""Условия «если»: поле + операция + значение."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .filetypes import detect, same_ext

STRING_FIELDS = {"name", "stem", "ext", "real_ext", "type", "path"}
NUMERIC_FIELDS = {"size", "age_days"}
BOOL_FIELDS = {"mismatch"}

STRING_OPS = {
    "equals", "not_equals", "in", "not_in", "contains", "not_contains",
    "startswith", "endswith", "regex",
}
NUMERIC_OPS = {"equals", "not_equals", "gt", "gte", "lt", "lte"}
BOOL_OPS = {"equals", "not_equals"}

_NUM_FUNCS = {
    "equals": lambda a, b: a == b,
    "not_equals": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
}

_SIZE_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(b|kb|mb|gb)?\s*$", re.I)
_UNITS = {None: 1, "b": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}


def parse_size(value: Any) -> int:
    """500 | "500KB" | "10 MB" | "1.5GB" -> байты."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    m = _SIZE_RE.match(str(value))
    if not m:
        raise ConfigError(f"не понимаю размер {value!r} (пример: 500KB, 10MB, 1GB)")
    unit = m.group(2).lower() if m.group(2) else None
    return int(float(m.group(1).replace(",", ".")) * _UNITS[unit])


@dataclass
class FileContext:
    """Всё, что известно о файле, пока правила решают его судьбу."""

    path: Path
    name: str
    stem: str
    ext: str
    real_ext: str
    type: str
    size: int
    mtime: float
    age_days: float
    mismatch: bool  # содержимое не соответствует расширению

    @classmethod
    def from_path(cls, path: Path, now: float) -> "FileContext":
        st = path.stat()
        info = detect(path)
        ext = path.suffix.lower().lstrip(".")
        return cls(
            path=path,
            name=path.name,
            stem=path.stem,
            ext=ext,
            real_ext=info.real_ext,
            type=info.kind,
            size=st.st_size,
            mtime=st.st_mtime,
            age_days=max(0.0, (now - st.st_mtime) / 86400),
            mismatch=info.by_content and not same_ext(info.real_ext, ext),
        )

    def get(self, field: str) -> Any:
        return str(self.path) if field == "path" else getattr(self, field)


@dataclass
class Condition:
    field: str
    op: str
    value: Any  # уже нормализовано при загрузке

    @classmethod
    def from_dict(cls, raw: Any, where: str) -> "Condition":
        if not isinstance(raw, dict):
            raise ConfigError(f"{where}: условие должно быть объектом")
        field, op = raw.get("field"), raw.get("op")
        if "value" not in raw:
            raise ConfigError(f"{where}: у условия нет поля value")
        value = raw["value"]

        if field in NUMERIC_FIELDS:
            allowed = NUMERIC_OPS
        elif field in BOOL_FIELDS:
            allowed = BOOL_OPS
        elif field in STRING_FIELDS:
            allowed = STRING_OPS
        else:
            known = sorted(STRING_FIELDS | NUMERIC_FIELDS | BOOL_FIELDS)
            raise ConfigError(
                f"{where}: неизвестное поле {field!r}. Доступны: {', '.join(known)}"
            )
        if op not in allowed:
            raise ConfigError(
                f"{where}: операция {op!r} не подходит для поля {field!r}. "
                f"Доступны: {', '.join(sorted(allowed))}"
            )

        if field == "size":
            try:
                value = parse_size(value)
            except ConfigError as e:
                raise ConfigError(f"{where}: {e}")
        elif field in NUMERIC_FIELDS:
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ConfigError(f"{where}: для {field} нужно число, а не {value!r}")
        elif field in BOOL_FIELDS:
            if not isinstance(value, bool):
                raise ConfigError(f"{where}: для {field} нужно true или false")
        elif op == "regex":
            try:
                value = re.compile(str(value), re.IGNORECASE)
            except re.error as e:
                raise ConfigError(f"{where}: сломанное регулярное выражение ({e})")
        else:
            items = value if isinstance(value, list) else [value]
            value = [
                str(v).lower().lstrip(".") if field in ("ext", "real_ext") else str(v).lower()
                for v in items
            ]
        return cls(field, op, value)

    def test(self, ctx: FileContext) -> bool:
        actual = ctx.get(self.field)
        op = self.op
        if self.field in NUMERIC_FIELDS:
            return _NUM_FUNCS[op](actual, self.value)
        if self.field in BOOL_FIELDS:
            same = bool(actual) == self.value
            return same if op == "equals" else not same
        if op == "regex":
            return bool(self.value.search(str(actual)))
        s = str(actual).lower()
        vals = self.value
        if op in ("equals", "in"):
            return s in vals
        if op in ("not_equals", "not_in"):
            return s not in vals
        if op == "contains":
            return any(v in s for v in vals)
        if op == "not_contains":
            return all(v not in s for v in vals)
        if op == "startswith":
            return any(s.startswith(v) for v in vals)
        return any(s.endswith(v) for v in vals)  # endswith
