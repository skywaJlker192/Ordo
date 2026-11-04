"""Слежение за папками: событие ОС -> ждём, пока файл «осядет» -> применяем правила."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .engine import ApplyResult, PlannedOp, apply_plan, is_candidate_name, plan_files
from .journal import Journal
from .rules import Config, WatchSpec

Sig = Optional[Tuple[int, float]]  # (размер, mtime) для проверки, что файл больше не растёт


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "Watcher"):
        self._w = watcher

    def on_created(self, event):
        if not event.is_directory:
            self._w.touch(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._w.touch(event.src_path)

    def on_moved(self, event):
        # браузер качает в .crdownload и переименовывает по завершении
        if not event.is_directory:
            self._w.touch(event.dest_path)


class Watcher:
    def __init__(self, config: Config, journal: Journal, log: Callable[[str], None] = print,
                 poll: float = 0.5,
                 on_batch: Optional[Callable[[List[PlannedOp], ApplyResult], None]] = None):
        self.config = config
        self.journal = journal
        self.log = log
        self.poll = poll
        self.on_batch = on_batch  # вызывается после каждой обработки файла (для уведомлений)
        self._stop = threading.Event()
        self._folders: Dict[Path, WatchSpec] = {}
        self._pending: Dict[Path, Tuple[float, Sig]] = {}
        self._lock = threading.Lock()

    # вызывается из потока watchdog
    def touch(self, raw_path: str) -> None:
        p = Path(raw_path)
        try:
            folder = p.parent.resolve()
        except OSError:
            return
        if folder in self._folders and is_candidate_name(p):
            with self._lock:
                self._pending[p] = (time.time(), None)

    def stop(self) -> None:
        """Попросить run() завершиться (можно вызывать из другого потока)."""
        self._stop.set()

    def run(self) -> None:
        observer = Observer()
        handler = _Handler(self)
        for spec in self.config.watch:
            if not spec.folder.is_dir():
                self.log(f"! папки нет, пропускаю: {spec.folder}")
                continue
            self._folders[spec.folder.resolve()] = spec
            observer.schedule(handler, str(spec.folder), recursive=False)
            self.log(f"Слежу за: {spec.folder}")
        if not self._folders:
            self.log("Нечего отслеживать: проверь секцию watch в конфиге.")
            return
        observer.start()
        self.log("Работаю. Остановить: Ctrl+C")
        try:
            while not self._stop.wait(self.poll):
                self._tick()
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()
            self.log("Остановлено.")

    def _tick(self) -> None:
        now = time.time()
        with self._lock:
            items = list(self._pending.items())
        for path, (last_event, last_sig) in items:
            spec = self._folders.get(path.parent.resolve())
            if spec is None or now - last_event < spec.settle_seconds:
                continue
            try:
                st = path.stat()
            except OSError:  # файл исчез (например, его уже обработали)
                self._drop(path)
                continue
            sig: Sig = (st.st_size, st.st_mtime)
            if sig != last_sig:
                # первая проверка или файл ещё меняется: проверим ещё раз на следующем тике
                with self._lock:
                    self._pending[path] = (now if last_sig is not None else last_event, sig)
                continue
            self._drop(path)
            self._process(path, spec)

    def _drop(self, path: Path) -> None:
        with self._lock:
            self._pending.pop(path, None)

    def _process(self, path: Path, spec: WatchSpec) -> None:
        if not path.is_file():
            return
        ops = plan_files([path], self.config.rules, spec.folder)
        if not ops:
            return
        result = apply_plan(ops, self.journal, source="watch")
        stamp = time.strftime("%H:%M:%S")
        for op in ops:
            self.log(f"[{stamp}] {op.src.name} -> {op.dst}  [{op.rule}]")
        for op, err in result.errors:
            self.log(f"[{stamp}] ОШИБКА {op.src.name}: {err}")
        if self.on_batch:
            try:
                self.on_batch(ops, result)
            except Exception as e:  # ошибка в обработчике не должна ронять слежение
                self.log(f"! обработчик события: {e}")
