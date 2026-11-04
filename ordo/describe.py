"""Правила человеческим языком: подписи для интерфейса и справочники для редактора."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

FIELDS = ["type", "name", "stem", "ext", "real_ext", "size", "age_days", "mismatch", "path"]

FIELD_LABELS = {
    "type": "Тип файла",
    "name": "Имя",
    "stem": "Имя без расширения",
    "ext": "Расширение",
    "real_ext": "Настоящее расширение",
    "size": "Размер",
    "age_days": "Возраст (дней)",
    "mismatch": "Расширение не совпадает с содержимым",
    "path": "Полный путь",
}

TYPE_LABELS = {
    "image": "картинка",
    "video": "видео",
    "audio": "аудио",
    "document": "документ",
    "archive": "архив",
    "installer": "установщик",
    "code": "код и данные",
    "other": "другое",
}

STRING_OPS = [
    "equals", "contains", "startswith", "endswith", "regex",
    "not_equals", "not_contains", "in", "not_in",
]
NUMERIC_OPS = ["gt", "gte", "lt", "lte", "equals", "not_equals"]
BOOL_OPS = ["equals", "not_equals"]

# подписи в выпадающем списке редактора
OP_LABELS = {
    "equals": "равно",
    "not_equals": "не равно",
    "in": "равно одному из",
    "not_in": "не равно ни одному из",
    "contains": "содержит",
    "not_contains": "не содержит",
    "startswith": "начинается с",
    "endswith": "заканчивается на",
    "regex": "подходит под регулярку",
    "gt": "больше",
    "gte": "не меньше",
    "lt": "меньше",
    "lte": "не больше",
}

ACTION_LABELS = {
    "move": "Переместить в папку",
    "copy": "Скопировать в папку",
    "rename": "Переименовать по шаблону",
    "trash": "В корзину Ordo",
}

PLACEHOLDER_HELP = {
    "name": "полное имя файла",
    "stem": "имя без расширения",
    "ext": "расширение",
    "real_ext": "настоящее расширение по содержимому",
    "type": "тип файла (image, video…)",
    "year": "год изменения файла",
    "month": "месяц (01–12)",
    "day": "день (01–31)",
    "size_mb": "размер в МБ",
}

SOURCE_LABELS = {"run": "Ручной запуск", "watch": "Слежение", "sweep": "Первичная уборка"}


def ops_for(field: str) -> List[str]:
    if field in ("size", "age_days"):
        return NUMERIC_OPS
    if field == "mismatch":
        return BOOL_OPS
    return STRING_OPS


def _quote_values(value: Any) -> str:
    items = value if isinstance(value, list) else [value]
    return ", ".join(f"«{v}»" for v in items)


def describe_condition(c: Dict[str, Any]) -> str:
    field = c.get("field", "?")
    op = c.get("op", "?")
    value = c.get("value")

    if field == "mismatch":
        want = bool(value) if op == "equals" else not bool(value)
        return ("расширение не совпадает с содержимым" if want
                else "расширение совпадает с содержимым")
    label = FIELD_LABELS.get(field, str(field)).lower()
    phrase = OP_LABELS.get(op, str(op))
    if field == "type":
        items = value if isinstance(value, list) else [value]
        shown = ", ".join(TYPE_LABELS.get(str(v), str(v)) for v in items)
        return f"тип {phrase} {shown}"
    if field == "age_days":
        return f"возраст {phrase} {value} дн."
    if field == "size":
        return f"размер {phrase} {value}"
    return f"{label} {phrase} {_quote_values(value)}"


def describe_action(a: Dict[str, Any]) -> str:
    kind = a.get("do")
    if kind == "move":
        return f"переместить в «{a.get('to', '')}»"
    if kind == "copy":
        return f"скопировать в «{a.get('to', '')}»"
    if kind == "rename":
        return f"переименовать в «{a.get('template', '')}»"
    if kind == "trash":
        return "отправить в корзину Ordo"
    return str(kind)


def describe_rule(rule: Dict[str, Any]) -> Tuple[str, str]:
    """(«если …», «то …») для карточки правила."""
    joiner = " и " if rule.get("match", "all") == "all" else " или "
    conds = [describe_condition(c) for c in rule.get("conditions", []) if isinstance(c, dict)]
    acts = [describe_action(a) for a in rule.get("actions", []) if isinstance(a, dict)]
    return (joiner.join(conds) or "условий пока нет", ", затем ".join(acts) or "действий пока нет")
