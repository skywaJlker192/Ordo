"""Состояние приложения: конфиг, журнал, потоки слежения и разбора. Страницы только слушают сигналы."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QObject, QSettings, QThread, QTimer, pyqtSignal

from .. import paths
from ..cli import human_size, plural
from ..config_io import default_config, ensure_config, save_raw
from ..engine import PlannedOp, apply_plan, plan_files, scan, undo_batch
from ..errors import ConfigError
from ..journal import Journal
from ..rules import Config, parse_config
from ..watcher import Watcher

Plan = Tuple[Path, List[PlannedOp], int]  # папка, операции, сколько файлов в папке


class _Task(QThread):
    """Выполнить функцию в фоне, чтобы окно не зависало на больших переносах."""

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable[[], Any], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except Exception as e:  # noqa: BLE001: показываем пользователю любую причину
            self.failed.emit(str(e))


class _WatchThread(QThread):
    batch = pyqtSignal(object, object)  # ops, ApplyResult
    message = pyqtSignal(str)

    def __init__(self, config: Config, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._watcher = Watcher(config, None, log=self.message.emit, on_batch=self.batch.emit)  # type: ignore[arg-type]

    def run(self) -> None:
        journal = Journal(paths.db_path())  # у потока своё соединение с БД
        self._watcher.journal = journal
        try:
            self._watcher.run()
        finally:
            journal.close()

    def stop(self) -> None:
        self._watcher.stop()
        self.wait(5000)


class AppState(QObject):
    config_changed = pyqtSignal()
    journal_changed = pyqtSignal()
    watch_changed = pyqtSignal(bool)
    files_moved = pyqtSignal(int)        # сколько файлов разобрало слежение (для уведомления)
    toast = pyqtSignal(str, str)         # текст, вид: success / danger / info

    def __init__(self, config_path: Optional[Path] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.path = config_path or paths.config_path()
        self.settings = QSettings("Ordo", "Ordo")
        self.raw: Dict[str, Any] = ensure_config(self.path)
        self.journal = Journal(paths.db_path())
        self._worker: Optional[_WatchThread] = None
        self._tasks: Set[_Task] = set()
        self._unreported = 0
        self._notify_timer = QTimer(self)
        self._notify_timer.setSingleShot(True)
        self._notify_timer.setInterval(1500)
        self._notify_timer.timeout.connect(self._flush_notification)

    # ---------- настройки интерфейса ----------

    def flag(self, key: str, default: bool = True) -> bool:
        return bool(self.settings.value(key, default, type=bool))

    def set_flag(self, key: str, value: bool) -> None:
        self.settings.setValue(key, value)

    # ---------- конфиг ----------

    @property
    def rules(self) -> List[Dict[str, Any]]:
        return self.raw.get("rules", [])

    @property
    def watch_folders(self) -> List[Dict[str, Any]]:
        return self.raw.get("watch", [])

    def parsed(self) -> Config:
        return parse_config(self.raw)

    def save(self, new_raw: Dict[str, Any]) -> Optional[str]:
        """Сохраняет конфиг. Возвращает текст ошибки или None. Старый конфиг при ошибке цел."""
        try:
            save_raw(self.path, new_raw)
        except ConfigError as e:
            return str(e)
        except OSError as e:
            return f"Не удалось записать {self.path}: {e}"
        self.raw = new_raw
        if self.watching:
            self.stop_watch(silent=True)
            self.start_watch(silent=True)
        self.config_changed.emit()
        return None

    def set_rules(self, rules: List[Dict[str, Any]]) -> Optional[str]:
        return self.save({**self.raw, "rules": rules})

    def set_watch_folders(self, folders: List[Dict[str, Any]]) -> Optional[str]:
        return self.save({**self.raw, "watch": folders})

    def reset_to_preset(self) -> Optional[str]:
        return self.save({**self.raw, "rules": default_config()["rules"]})

    # ---------- слежение ----------

    @property
    def watching(self) -> bool:
        return self._worker is not None

    def start_watch(self, silent: bool = False) -> bool:
        if self._worker:
            return True
        try:
            cfg = self.parsed()
        except ConfigError as e:
            self.toast.emit(str(e), "danger")
            return False
        if not any(w.folder.is_dir() for w in cfg.watch):
            if not silent:
                self.toast.emit("Нет папок для слежения. Добавь их на вкладке «Папки»", "danger")
            return False
        worker = _WatchThread(cfg, self)
        worker.batch.connect(self._on_batch)
        worker.finished.connect(lambda w=worker: self._on_watch_finished(w))
        self._worker = worker
        worker.start()
        self.watch_changed.emit(True)
        if not silent:
            self.toast.emit("Слежение включено", "success")
        return True

    def stop_watch(self, silent: bool = False) -> None:
        worker, self._worker = self._worker, None
        if worker:
            worker.stop()
            self.watch_changed.emit(False)
            if not silent:
                self.toast.emit("Слежение на паузе", "info")

    def toggle_watch(self) -> None:
        self.stop_watch() if self.watching else self.start_watch()

    def _on_watch_finished(self, worker: _WatchThread) -> None:
        if self._worker is worker:  # поток завершился сам, а не по нашей просьбе
            self._worker = None
            self.watch_changed.emit(False)
            self.toast.emit("Слежение остановилось: нет доступных папок", "danger")

    def _on_batch(self, _ops, result) -> None:
        self._unreported += result.done
        self.journal_changed.emit()
        self._notify_timer.start()

    def _flush_notification(self) -> None:
        if self._unreported:
            self.files_moved.emit(self._unreported)
            self._unreported = 0

    def shutdown(self) -> None:
        self.stop_watch(silent=True)
        for t in list(self._tasks):
            t.wait(3000)
        self.journal.close()

    # ---------- разбор и откат ----------

    def plan(self, only: Optional[Path] = None) -> List[Plan]:
        cfg = self.parsed()
        folders = [only] if only else [w.folder for w in cfg.watch]
        plans: List[Plan] = []
        for folder in folders:
            if folder.is_dir():
                files = scan(folder)
                plans.append((folder, plan_files(files, cfg.rules, folder), len(files)))
        return plans

    def apply(self, plans: List[Plan], source: str = "run") -> None:
        def work() -> Tuple[int, int]:
            journal = Journal(paths.db_path())
            done = errors = 0
            try:
                for _folder, ops, _total in plans:
                    if ops:
                        res = apply_plan(ops, journal, source)
                        done += res.done
                        errors += len(res.errors)
            finally:
                journal.close()
            return done, errors

        task = _Task(work, self)
        task.done.connect(self._applied)
        task.failed.connect(lambda msg: self.toast.emit(f"Ошибка: {msg}", "danger"))
        task.finished.connect(lambda t=task: self._tasks.discard(t))
        self._tasks.add(task)
        task.start()

    def _applied(self, result: Tuple[int, int]) -> None:
        done, errors = result
        text = f"Готово: {plural(done, 'операция', 'операции', 'операций')}"
        if errors:
            text += f", с ошибками: {errors}"
        self.toast.emit(text, "danger" if errors and not done else "success")
        self.journal_changed.emit()

    def undo(self, batch_id: Optional[int] = None) -> None:
        result = undo_batch(self.journal, batch_id)
        if result is None:
            self.toast.emit("Откатывать нечего", "info")
            return
        text = f"Пакет #{result.batch_id} отменён: вернул {plural(result.restored, 'файл', 'файла', 'файлов')}"
        if result.skipped:
            text += f", пропущено: {len(result.skipped)}"
        self.toast.emit(text, "success")
        self.journal_changed.emit()

    def trash_summary(self) -> Tuple[int, str]:
        root = paths.trash_dir()
        files = [f for f in root.rglob("*") if f.is_file()] if root.is_dir() else []
        return len(files), human_size(sum(f.stat().st_size for f in files))
