"""Значок в трее: меню, индикатор состояния, уведомления."""
from __future__ import annotations

from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QAction, QMenu, QSystemTrayIcon

from ..cli import plural
from . import icons
from .main_window import MainWindow
from .state import AppState
from .theme import C


class TrayController(QObject):
    def __init__(self, window: MainWindow, state: AppState):
        super().__init__(window)
        self.window = window
        self.state = state
        self.tray = QSystemTrayIcon(icons.app_icon(), window)

        self.menu = QMenu()
        self.act_open = QAction("Открыть Ordo", self.menu)
        self.act_toggle = QAction("", self.menu)
        self.act_run = QAction("Разобрать сейчас…", self.menu)
        self.act_quit = QAction("Выход", self.menu)
        self.act_open.triggered.connect(window.show_and_raise)
        self.act_toggle.triggered.connect(state.toggle_watch)
        self.act_run.triggered.connect(self._run)
        self.act_quit.triggered.connect(window.quit_app)
        for a in (self.act_open, None, self.act_toggle, self.act_run, None, self.act_quit):
            self.menu.addSeparator() if a is None else self.menu.addAction(a)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)

        state.watch_changed.connect(self._sync)
        state.files_moved.connect(self._notify)
        window.hidden_to_tray.connect(self._hint)
        self._sync(state.watching)
        self.tray.show()

    def _sync(self, on: bool) -> None:
        self.tray.setIcon(icons.app_icon(C["success"] if on else C["muted2"]))
        self.tray.setToolTip("Ordo: слежение включено" if on else "Ordo: слежение на паузе")
        self.act_toggle.setText("Приостановить слежение" if on else "Включить слежение")

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.window.show_and_raise()

    def _run(self) -> None:
        self.window.show_and_raise()
        self.window.run_now()

    def _notify(self, count: int) -> None:
        if self.state.flag("notifications", True):
            self.tray.showMessage("Ordo", f"Разобрано: {plural(count, 'файл', 'файла', 'файлов')}",
                                  icons.app_icon(), 4000)

    def _hint(self) -> None:
        if not self.state.flag("tray_hint_shown", False):
            self.state.set_flag("tray_hint_shown", True)
            self.tray.showMessage("Ordo работает в трее",
                                  "Закрыть совсем: правый клик по значку, пункт «Выход».",
                                  icons.app_icon(), 5000)
