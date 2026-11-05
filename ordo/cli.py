"""Командная строка: ordo init | preview | run | watch | undo | history | stats | empty-trash."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import __version__
from .config_io import default_config
from .engine import PlannedOp, apply_plan, empty_trash, plan_files, scan, undo_batch
from .errors import ConfigError
from .journal import Journal
from .paths import config_path, db_path, expand, trash_dir
from .rules import Config, WatchSpec, load_config
from .watcher import Watcher

_VERBS = {"move": "переместить", "copy": "скопировать", "rename": "переименовать", "trash": "в корзину"}


def plural(n: int, one: str, few: str, many: str) -> str:
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        word = one
    elif 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        word = few
    else:
        word = many
    return f"{n} {word}"


def human_size(n: float) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} Б"


def _rel(p: Path, base: Path) -> str:
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(p)


def _targets(cfg: Config, folder: Optional[str]) -> List[WatchSpec]:
    if folder:
        return [WatchSpec(expand(folder))]
    if not cfg.watch:
        raise ConfigError("в конфиге нет папок для слежения (секция watch)")
    return cfg.watch


def _print_plan(ops: List[PlannedOp], base: Path, total_files: int) -> None:
    touched = len({op.origin for op in ops})
    print(
        f"{base}: {plural(total_files, 'файл', 'файла', 'файлов')}, "
        f"к обработке {touched}, без правил {total_files - touched}"
    )
    by_rule: dict = {}
    for op in ops:
        by_rule.setdefault(op.rule, []).append(op)
    for rule, rule_ops in by_rule.items():
        print(f"  [{rule}]")
        for op in rule_ops:
            if op.kind == "rename":
                print(f"    {_VERBS[op.kind]:<12} {op.src.name} -> {op.dst.name}")
            else:
                print(f"    {_VERBS[op.kind]:<12} {op.src.name} -> {_rel(op.dst, base)}")


def _journal() -> Journal:
    return Journal(db_path())


# ---------- команды ----------

def cmd_init(args) -> int:
    target = config_path()
    if target.exists() and not args.force:
        print(f"Конфиг уже есть: {target}\nЧтобы перезаписать, добавь --force.")
        return 1
    data = default_config()
    if args.folder:
        data["watch"][0]["folder"] = args.folder
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Готово: {target}")
    print("Дальше: ordo preview  (посмотреть, что будет),  ordo run  (применить),  ordo watch  (следить)")
    return 0


def cmd_preview(args, cfg: Config) -> int:
    for spec in _targets(cfg, args.folder):
        if not spec.folder.is_dir():
            print(f"! папки нет: {spec.folder}")
            continue
        files = scan(spec.folder)
        ops = plan_files(files, cfg.rules, spec.folder)
        _print_plan(ops, spec.folder, len(files))
    print("\nЭто только предпросмотр, файлы не тронуты.")
    return 0


def cmd_run(args, cfg: Config) -> int:
    journal = _journal()
    total_done = 0
    for spec in _targets(cfg, args.folder):
        if not spec.folder.is_dir():
            print(f"! папки нет: {spec.folder}")
            continue
        files = scan(spec.folder)
        ops = plan_files(files, cfg.rules, spec.folder)
        if not ops:
            print(f"{spec.folder}: нечего делать")
            continue
        _print_plan(ops, spec.folder, len(files))
        if not args.yes:
            answer = input("\nПрименить? [y/N] ").strip().lower()
            if answer not in ("y", "yes", "д", "да"):
                print("Пропускаю.")
                continue
        result = apply_plan(ops, journal, source="run")
        total_done += result.done
        for op, err in result.errors:
            print(f"  ОШИБКА {op.src.name}: {err}")
        if result.batch_id:
            print(f"Готово: {plural(result.done, 'операция', 'операции', 'операций')}. "
                  f"Отменить: ordo undo (пакет #{result.batch_id})")
    return 0


def cmd_watch(args, cfg: Config) -> int:
    journal = _journal()
    cfg = Config(watch=_targets(cfg, args.folder), rules=cfg.rules)
    if args.sweep:
        for spec in cfg.watch:
            if spec.folder.is_dir():
                ops = plan_files(scan(spec.folder), cfg.rules, spec.folder)
                result = apply_plan(ops, journal, source="sweep")
                print(f"Первичная уборка {spec.folder}: {plural(result.done, 'операция', 'операции', 'операций')}")
    Watcher(cfg, journal).run()
    return 0


def cmd_undo(args) -> int:
    journal = _journal()
    if args.batch is not None and not journal.batch_exists(args.batch):
        print(f"Пакета #{args.batch} нет в журнале.")
        return 1
    result = undo_batch(journal, args.batch)
    if result is None:
        print("Откатывать нечего.")
        return 0
    print(f"Пакет #{result.batch_id} отменён: возвращено {plural(result.restored, 'файл', 'файла', 'файлов')}.")
    for path, reason in result.skipped:
        print(f"  пропущено: {path} ({reason})")
    return 0


def cmd_history(args) -> int:
    rows = _journal().history(args.n)
    if not rows:
        print("Журнал пуст.")
        return 0
    for r in rows:
        when = datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M")
        mark = "  (отменён)" if r["undone"] else ""
        print(f"#{r['id']:<4} {when}  {r['source']:<6} {plural(r['n'], 'операция', 'операции', 'операций')}{mark}")
    return 0


def cmd_stats(args) -> int:
    s = _journal().stats()
    if not s["ops"]:
        print("Пока ничего не сделано.")
        return 0
    print(f"Операций: {s['ops']} в {plural(s['batches'], 'пакете', 'пакетах', 'пакетах')}")
    print(f"Разобрано данных: {human_size(s['bytes'])}")
    if s["undone"]:
        print(f"Отменённых пакетов: {s['undone']}")
    print("Чаще всего срабатывали:")
    for rule, n in s["top_rules"]:
        print(f"  {n:>4}  {rule}")
    return 0


def cmd_empty_trash(args) -> int:
    removed = empty_trash(args.older_than)
    print(f"Удалено навсегда: {plural(removed, 'файл', 'файла', 'файлов')} (старше {args.older_than} дн.)")
    return 0


def cmd_gui(args) -> int:
    try:
        import PyQt5  # noqa: F401
    except ImportError:
        print("Для окна нужен PyQt5. Поставь: pip install PyQt5", file=sys.stderr)
        return 1
    from .gui.app import main as gui_main
    gui_args = (["--minimized"] if args.minimized else []) + (["--config", args.config] if args.config else [])
    return gui_main(gui_args)


# ---------- вход ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ordo", description="Ordo: порядок в файлах по правилам.")
    p.add_argument("--config", help="путь к config.json (по умолчанию ~/.ordo/config.json)")
    p.add_argument("--version", action="version", version=f"ordo {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="создать конфиг из готового пресета для «Загрузок»")
    s.add_argument("--folder", help="какую папку разбирать (по умолчанию ~/Downloads)")
    s.add_argument("--force", action="store_true", help="перезаписать существующий конфиг")

    for name, text in (("preview", "показать, что будет сделано (ничего не меняет)"),
                       ("run", "разобрать папки один раз")):
        s = sub.add_parser(name, help=text)
        s.add_argument("--folder", help="разобрать другую папку вместо указанных в конфиге")
        if name == "run":
            s.add_argument("-y", "--yes", action="store_true", help="не спрашивать подтверждение")

    s = sub.add_parser("watch", help="следить за папками и разбирать новые файлы сразу")
    s.add_argument("--folder")
    s.add_argument("--sweep", action="store_true", help="сначала разобрать то, что уже лежит")

    s = sub.add_parser("undo", help="отменить последний пакет операций")
    s.add_argument("--batch", type=int, help="номер пакета из ordo history")

    s = sub.add_parser("history", help="журнал операций")
    s.add_argument("-n", type=int, default=10)

    sub.add_parser("stats", help="статистика")

    s = sub.add_parser("gui", help="открыть окно приложения (нужен PyQt5)")
    s.add_argument("--minimized", action="store_true", help="запуститься свёрнутым в трей")

    s = sub.add_parser("empty-trash", help="очистить корзину Ordo")
    s.add_argument("--older-than", type=int, default=30, metavar="ДНЕЙ")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        if args.command == "gui":
            return cmd_gui(args)
        if args.command == "init":
            return cmd_init(args)
        if args.command == "undo":
            return cmd_undo(args)
        if args.command == "history":
            return cmd_history(args)
        if args.command == "stats":
            return cmd_stats(args)
        if args.command == "empty-trash":
            return cmd_empty_trash(args)
        cfg = load_config(Path(args.config) if args.config else config_path())
        return {"preview": cmd_preview, "run": cmd_run, "watch": cmd_watch}[args.command](args, cfg)
    except ConfigError as e:
        print(f"Ошибка конфига: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Ошибка файловой системы: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
