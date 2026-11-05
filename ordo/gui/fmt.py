"""Подписи для интерфейса: время «назад», числа, короткие пути."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

VERBS_PAST = {"move": "Перемещён", "copy": "Скопирован", "rename": "Переименован", "trash": "В корзину"}


def ago(ts: float) -> str:
    delta = time.time() - ts
    if delta < 60:
        return "только что"
    if delta < 3600:
        return f"{int(delta // 60)} мин назад"
    dt, now = datetime.fromtimestamp(ts), datetime.now()
    if dt.date() == now.date():
        return f"сегодня, {dt:%H:%M}"
    if (now.date() - dt.date()).days == 1:
        return f"вчера, {dt:%H:%M}"
    return f"{dt:%d.%m.%Y, %H:%M}"


def number(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def tail(path, parts: int = 2) -> str:
    """Последние N частей пути: «Скриншоты/2026-11»."""
    p = Path(str(path))
    return "/".join(p.parts[-parts:]) if len(p.parts) > parts else str(p)
