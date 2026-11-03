"""Движок: из файлов и правил строит план, применяет его и умеет откатывать."""
from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .conditions import FileContext
from .journal import Journal
from .paths import expand, trash_dir
from .rules import Rule
from .templates import render

TEMP_EXTS = {"crdownload", "part", "tmp", "download", "opdownload", "partial"}
IGNORED_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}


@dataclass
class PlannedOp:
    kind: str       # move / copy / rename / trash
    src: Path
    dst: Path
    rule: str
    size: int
    origin: Path    # исходный файл, с которого началась цепочка действий


@dataclass
class ApplyResult:
    batch_id: Optional[int] = None
    done: int = 0
    errors: List[Tuple[PlannedOp, str]] = field(default_factory=list)


@dataclass
class UndoResult:
    batch_id: int
    restored: int = 0
    skipped: List[Tuple[str, str]] = field(default_factory=list)


# ---------- поиск файлов ----------

def is_candidate_name(path: Path) -> bool:
    """Годится ли имя: не скрытый, не временный (недокачанный) файл."""
    name = path.name.lower()
    if name.startswith(".") or name.startswith("~$") or name in IGNORED_NAMES:
        return False
    return path.suffix.lower().lstrip(".") not in TEMP_EXTS


def scan(folder: Path) -> List[Path]:
    """Файлы прямо в папке (без вложенных), которые стоит обрабатывать."""
    return sorted(
        p for p in folder.iterdir()
        if is_candidate_name(p) and p.is_file() and not p.is_symlink()
    )


# ---------- планирование ----------

def _values(ctx: FileContext) -> Dict[str, object]:
    dt = datetime.fromtimestamp(ctx.mtime)
    return {
        "name": ctx.name,
        "stem": ctx.stem,
        "ext": ctx.ext,
        "real_ext": ctx.real_ext,
        "type": ctx.type,
        "year": f"{dt.year}",
        "month": f"{dt.month:02d}",
        "day": f"{dt.day:02d}",
        "size_mb": f"{ctx.size / 1048576:.1f}",
    }


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _unique(dst: Path, reserved: Set[Path], current: Path) -> Path:
    """Никогда не затираем чужие файлы: занято -> «имя (1).ext»."""

    def taken(p: Path) -> bool:
        return p in reserved or (p.exists() and not _same_file(p, current))

    if not taken(dst):
        return dst
    n = 1
    while True:
        cand = dst.with_name(f"{dst.stem} ({n}){dst.suffix}")
        if not taken(cand):
            return cand
        n += 1


def _dest_dir(text: str, base: Path) -> Path:
    p = expand(text)
    return p if p.is_absolute() else base / p


def _plan_rule(
    rule: Rule, ctx: FileContext, current: Path, origin: Path, base: Path,
    reserved: Set[Path], now: float,
) -> Tuple[List[PlannedOp], Path]:
    ops: List[PlannedOp] = []
    vals = _values(ctx)
    for act in rule.actions:
        if act.kind in ("move", "copy"):
            dst = _dest_dir(render(act.to, vals), base) / current.name
            if dst == current:
                continue
            dst = _unique(dst, reserved, current)
        elif act.kind == "rename":
            new_name = render(act.template, vals)
            if not new_name or new_name == current.name:
                continue
            dst = current.with_name(new_name)
            if dst == current:
                continue
            dst = _unique(dst, reserved, current)
        else:  # trash: файл уезжает в корзину Ordo (откат возможен)
            day = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
            dst = _unique(trash_dir() / day / current.name, reserved, current)
        reserved.add(dst)
        ops.append(PlannedOp(act.kind, current, dst, rule.name, ctx.size, origin))
        if act.kind != "copy":
            current = dst
    return ops, current


def plan_files(
    files: Iterable[Path],
    rules: List[Rule],
    base: Path,
    now: Optional[float] = None,
    reserved: Optional[Set[Path]] = None,
) -> List[PlannedOp]:
    """Предпросмотр: ничего не трогает на диске, только возвращает список операций."""
    now = time.time() if now is None else now
    reserved = set() if reserved is None else reserved
    ops: List[PlannedOp] = []
    for f in files:
        try:
            ctx = FileContext.from_path(f, now)
        except OSError:
            continue
        current = f
        for rule in rules:
            if not rule.enabled or not rule.matches(ctx):
                continue
            new_ops, current = _plan_rule(rule, ctx, current, f, base, reserved, now)
            ops.extend(new_ops)
            if rule.stop:
                break
            if current != ctx.path:  # файл переименован/перемещён, но правила идут дальше
                ctx = replace(
                    ctx, path=current, name=current.name, stem=current.stem,
                    ext=current.suffix.lower().lstrip("."), mismatch=False,
                )
    return ops


# ---------- применение и откат ----------

def apply_plan(ops: List[PlannedOp], journal: Journal, source: str = "run") -> ApplyResult:
    result = ApplyResult()
    for op in ops:
        try:
            op.dst.parent.mkdir(parents=True, exist_ok=True)
            if op.kind == "copy":
                shutil.copy2(op.src, op.dst)
            else:
                shutil.move(str(op.src), str(op.dst))
        except OSError as e:
            result.errors.append((op, str(e)))
            continue
        if result.batch_id is None:
            result.batch_id = journal.begin_batch(source)
        journal.record(result.batch_id, op.kind, op.src, op.dst, op.rule, op.size)
        result.done += 1
    return result


def _remove_empty_dirs(start: Path, stop_at: Path) -> None:
    """Убирает пустые папки, созданные самим Ordo, снизу вверх, не выходя за stop_at."""
    cur = start
    while cur != stop_at and stop_at in cur.parents:
        try:
            cur.rmdir()  # не пустая папка не удалится, так что чужое не заденем
        except OSError:
            return
        cur = cur.parent


def undo_batch(journal: Journal, batch_id: Optional[int] = None) -> Optional[UndoResult]:
    """Откатывает пакет (по умолчанию последний). Ничего не затирает."""
    if batch_id is None:
        batch_id = journal.last_active_batch()
        if batch_id is None:
            return None
    result = UndoResult(batch_id)
    for row in reversed(journal.ops(batch_id)):
        src, dst = Path(row["src"]), Path(row["dst"])
        if row["kind"] == "copy":
            if dst.exists():
                dst.unlink()
                result.restored += 1
            else:
                result.skipped.append((str(dst), "копии уже нет"))
            continue
        if not dst.exists():
            result.skipped.append((str(dst), "файл уже перемещён или удалён"))
        elif src.exists():
            result.skipped.append((str(src), "на старом месте уже лежит другой файл"))
        else:
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
            result.restored += 1
            _remove_empty_dirs(dst.parent, stop_at=src.parent)
    journal.mark_undone(batch_id)
    return result
