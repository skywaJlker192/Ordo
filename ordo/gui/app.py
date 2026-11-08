"""Точка входа интерфейса: ordo gui  (или ordo-gui)."""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from ..errors import ConfigError
from . import icons, theme
from .main_window import MainWindow
from .state import AppState
from .tray import TrayController

_SERVER_NAME = f"ordo-gui-{getpass.getuser()}"


def _ping_running_instance() -> bool:
    """Если Ordo уже запущен, попросить его показать окно и выйти самим."""
    sock = QLocalSocket()
    sock.connectToServer(_SERVER_NAME)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def _listen_for_pings(window: MainWindow) -> QLocalServer:
    QLocalServer.removeServer(_SERVER_NAME)  # хвост от прошлого аварийного завершения
    server = QLocalServer(window)

    def on_connect() -> None:
        conn = server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(window.show_and_raise)
            conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_connect)
    server.listen(_SERVER_NAME)
    return server


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="ordo-gui")
    parser.add_argument("--minimized", action="store_true", help="запуститься свёрнутым в трей")
    parser.add_argument("--config", help="путь к config.json")
    args = parser.parse_args(argv)

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    try:  # дробные масштабы Windows (125%, 150%) без размытия
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except AttributeError:
        pass
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Ordo")
    app.setOrganizationName("Ordo")
    app.setWindowIcon(icons.app_icon())
    app.setQuitOnLastWindowClosed(False)

    if _ping_running_instance():
        return 0
    theme.apply(app)

    try:
        state = AppState(Path(args.config) if args.config else None)
    except ConfigError as e:
        box = QMessageBox()
        box.setWindowTitle("Ordo: ошибка конфига")
        box.setText(f"{e}\n\nИсправь файл вручную или удали его: Ordo создаст новый из пресета.")
        box.exec_()
        return 2

    tray_ok = QSystemTrayIcon.isSystemTrayAvailable()
    window = MainWindow(state, tray_available=tray_ok)
    _server = _listen_for_pings(window)  # noqa: F841 (держим ссылку, пока работает приложение)
    if tray_ok:
        TrayController(window, state)

    if state.flag("autostart_watch", True):
        state.start_watch(silent=True)
    window.automation.start()
    if not (args.minimized and tray_ok):
        window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
