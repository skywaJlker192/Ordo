"""Движок автоматизации в окне: горячие клавиши, расписание, слежение за буфером, запуск «сейчас»."""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Union

from PyQt5.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QApplication

from .. import hotkeys
from ..errors import ConfigError
from ..paths import expand
from ..scenarios import Env, RunResult, Scenario, is_due, match_clipboard, parse_scenario, run_actions
from .state import AppState

TICK_MS = 15_000   # как часто проверяем расписание
RADIAL_ID = 1000
MUTE_SECONDS = 0.8  # после своего запуска не реагируем на буфер: сценарий сам его менял


class AutomationEngine(QObject):
    ran = pyqtSignal(str, bool, str)       # имя сценария, успех, текст ошибки
    _hotkey_pressed = pyqtSignal(int)      # приходит из потока Windows, в основной поток переезжает очередью
    _hotkey_failed = pyqtSignal(int, str)
    radial_requested = pyqtSignal()        # нажата клавиша радиального меню

    listener_cls = hotkeys.HotkeyListener  # в тестах подменяется заглушкой

    def __init__(self, state: AppState, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.state = state
        self._scenarios: List[Scenario] = []
        self._hotkeys: Dict[int, Scenario] = {}
        self._listener: Optional[hotkeys.HotkeyListener] = None
        self._last_run: Dict[str, datetime] = {}
        self._mute_until = 0.0
        self._running = False
        self._clipboard = QApplication.clipboard()
        self.env = Env(
            notify=self._notify, open_target=self._open, get_clipboard=self._clipboard.text,
            set_clipboard=self._clipboard.setText, sort=self._sort,
        )
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self.tick)
        self._clipboard.dataChanged.connect(self._on_clipboard)
        self._hotkey_pressed.connect(self._on_hotkey)
        self._hotkey_failed.connect(self._on_hotkey_failed)
        state.config_changed.connect(self.reload)

    # ---------- жизненный цикл ----------

    def start(self) -> None:
        self.reload()
        self._timer.start()
        for sc in self._scenarios:
            if sc.enabled and sc.trigger["type"] == "startup":
                self.run(sc)

    def stop(self) -> None:
        self._timer.stop()
        self._stop_listener()

    def reload(self) -> None:
        """Перечитать сценарии из конфига и заново занять горячие клавиши."""
        self._stop_listener()
        radial = None
        try:
            cfg = self.state.parsed()
            self._scenarios, radial = cfg.scenarios, cfg.radial
        except ConfigError:
            self._scenarios = []
        self._hotkeys = {}
        now = datetime.now()
        for i, sc in enumerate(self._scenarios):
            if not sc.enabled:
                continue
            t = sc.trigger
            if t["type"] == "hotkey":
                self._hotkeys[len(self._hotkeys) + 1] = sc
            elif t["type"] == "schedule" and t["mode"] == "every":
                self._last_run.setdefault(self._key(i, sc), now)  # первый запуск через N минут, не сразу
        bindings = {hid: sc.trigger["keys"] for hid, sc in self._hotkeys.items()}
        if radial and radial.enabled and radial.items:
            bindings[RADIAL_ID] = radial.hotkey
        if bindings and hotkeys.supported():
            self._listener = self.listener_cls(
                bindings,
                self._hotkey_pressed.emit, self._hotkey_failed.emit)
            self._listener.start()

    def _stop_listener(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    @staticmethod
    def _key(index: int, sc: Scenario) -> str:
        return f"{index}:{sc.name}"

    # ---------- запуск ----------

    def run(self, scenario: Union[Scenario, dict], announce: bool = False) -> Optional[RunResult]:
        """Выполнить сценарий (объект или «сырой» словарь из редактора)."""
        if isinstance(scenario, dict):
            try:
                scenario = parse_scenario(scenario)
            except ConfigError as e:
                self.state.toast.emit(str(e), "danger")
                return None
        self._running = True
        try:
            result = run_actions(scenario.actions, self.env)
        finally:
            self._running = False
            self._mute_until = time.monotonic() + MUTE_SECONDS
        self.ran.emit(scenario.name, result.ok, result.error or "")
        if not result.ok:
            self.state.toast.emit(f"Сценарий «{scenario.name}»: {result.error}", "danger")
        elif announce:
            self.state.toast.emit(f"Сценарий «{scenario.name}» выполнен", "success")
        return result

    def tick(self, now: Optional[datetime] = None) -> None:
        now = now or datetime.now()
        for i, sc in enumerate(self._scenarios):
            if not sc.enabled or sc.trigger["type"] != "schedule":
                continue
            key = self._key(i, sc)
            if is_due(sc.trigger, self._last_run.get(key), now):
                self._last_run[key] = now
                self.run(sc)

    # ---------- события ----------

    def _on_hotkey(self, hid: int) -> None:
        if hid == RADIAL_ID:
            self.radial_requested.emit()
            return
        sc = self._hotkeys.get(hid)
        if sc:
            self.run(sc)

    def _on_hotkey_failed(self, _hid: int, keys: str) -> None:
        self.state.toast.emit(
            f"Не удалось занять {keys}: сочетание уже использует другая программа. Выбери другое", "danger")

    def _on_clipboard(self) -> None:
        if self._running or time.monotonic() < self._mute_until:
            return
        text = self._clipboard.text()
        for sc in self._scenarios:
            if sc.enabled and sc.trigger["type"] == "clipboard" and match_clipboard(sc.trigger, text):
                self.run(sc)

    # ---------- что сценарий делает во внешнем мире ----------

    def _notify(self, text: str) -> None:
        self.state.toast.emit(text, "info")
        self.state.notice.emit(text)

    def _open(self, target: str) -> None:
        url = QUrl(target) if re.match(r"(?i)^(https?|mailto):", target) else QUrl.fromLocalFile(target)
        if not QDesktopServices.openUrl(url):
            raise OSError("система не смогла это открыть")

    def _sort(self, folder: str) -> None:
        only = None
        if folder.strip():
            only = expand(folder)
            if not only.is_dir():
                raise ValueError(f"папки нет: {folder}")
        plans = self.state.plan(only)
        if any(ops for _f, ops, _t in plans):
            self.state.apply(plans, "scenario")
