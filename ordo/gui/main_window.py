"""Главное окно: боковая панель, страницы, всплывающие уведомления."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PyQt5.QtCore import QByteArray, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QScrollArea, QShortcut, QStackedWidget, QVBoxLayout, QWidget,
)
from PyQt5.QtGui import QDesktopServices, QKeySequence

from .. import __version__, radial
from ..cli import plural
from ..errors import ConfigError
from . import icons
from .dashboard import DashboardPage
from .automation import AutomationEngine
from .folders_page import FoldersPage
from .history_page import HistoryPage
from .preview import PreviewDialog
from .radial_menu import RadialMenu
from .rules_page import RulesPage, warn
from .scenarios_page import ScenariosPage
from .settings_page import SettingsPage
from .state import AppState
from .theme import C, set_prop
from .widgets import Toggle, label

NAV = [("home", "Главная"), ("rules", "Правила"), ("scenario", "Сценарии"), ("history", "Журнал"),
       ("folder", "Папки"), ("settings", "Настройки")]

_TOAST_COLORS = {"success": C["success"], "danger": C["danger"], "info": C["accent_text"]}


class Toast(QLabel):
    """Короткое сообщение внизу окна. Исчезает само."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWordWrap(True)
        self.setMaximumWidth(560)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text: str, kind: str = "info") -> None:
        color = _TOAST_COLORS.get(kind, C["accent_text"])
        self.setStyleSheet(
            f"background: {C['surface3']}; color: {C['text']}; border: 1px solid {C['border2']};"
            f"border-left: 4px solid {color}; border-radius: 10px; padding: 11px 16px; font-weight: 500;")
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(3600 if kind != "danger" else 6000)

    def reposition(self) -> None:
        p = self.parentWidget()
        if p:
            self.move((p.width() - self.width()) // 2, p.height() - self.height() - 28)


def _scroll_page(page: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    inner = QWidget()
    inner.setObjectName("Page")
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(36, 30, 36, 30)
    lay.addWidget(page)
    scroll.setWidget(inner)
    return scroll


class MainWindow(QMainWindow):
    hidden_to_tray = pyqtSignal()

    def __init__(self, state: AppState, tray_available: bool = False):
        super().__init__()
        self.state = state
        self._tray_ok = tray_available
        self._quitting = False
        self.setWindowTitle("Ordo")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(1000, 660)
        self.resize(1180, 760)

        central = QWidget()
        self.setCentralWidget(central)
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage(state, self.run_now)
        self.rules = RulesPage(state)
        self.automation = AutomationEngine(state, self)
        self.scenarios = ScenariosPage(state, self.automation)
        self.history = HistoryPage(state)
        self.folders = FoldersPage(state, self.run_now)
        self.settings_page = SettingsPage(state)
        self.pages: List[QWidget] = [self.dashboard, self.rules, self.scenarios, self.history, self.folders, self.settings_page]
        for p in self.pages:
            self.stack.addWidget(_scroll_page(p))
        row.addWidget(self.stack, 1)

        self.radial_menu = RadialMenu()
        self.radial_menu.chosen.connect(self.run_radial)
        self.automation.radial_requested.connect(self.show_radial)

        self.toast = Toast(central)
        state.toast.connect(self.toast.show_message)
        state.watch_changed.connect(self._sync_watch)
        self._sync_watch(state.watching)

        for i in range(len(NAV)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda k=i: self.go(k))
        self.go(0)

        geo = state.settings.value("geometry")
        if isinstance(geo, QByteArray):
            self.restoreGeometry(geo)

    # ---------- боковая панель ----------

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(236)
        col = QVBoxLayout(side)
        col.setContentsMargins(16, 22, 16, 16)
        col.setSpacing(4)

        brand = QHBoxLayout()
        brand.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(icons.logo_pixmap(38))
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("Ordo", "brand"))
        names.addWidget(label("порядок в файлах", "caption"))
        brand.addLayout(names)
        brand.addStretch(1)
        col.addLayout(brand)
        col.addSpacing(22)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: List[QPushButton] = []
        for i, (icon_name, text) in enumerate(NAV):
            b = QPushButton(text)
            b.setProperty("nav", "true")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(icons.icon(icon_name, C["muted"], C["accent_text"], size=18))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(f"Ctrl+{i + 1}")
            b.clicked.connect(lambda _=False, k=i: self.go(k))
            self.nav_group.addButton(b)
            self.nav_buttons.append(b)
            col.addWidget(b)
        col.addStretch(1)

        status = QFrame()
        status.setObjectName("CardInner")
        sl = QHBoxLayout(status)
        sl.setContentsMargins(14, 12, 12, 12)
        sl.setSpacing(10)
        self.dot = QLabel()
        self.dot.setFixedSize(9, 9)
        sl.addWidget(self.dot)
        txt = QVBoxLayout()
        txt.setSpacing(0)
        self.status_title = label("Слежение", "h3")
        self.status_sub = label("", "caption")
        txt.addWidget(self.status_title)
        txt.addWidget(self.status_sub)
        sl.addLayout(txt, 1)
        self.side_toggle = Toggle(False)
        self.side_toggle.setToolTip("Включить или приостановить слежение")
        self.side_toggle.clicked.connect(self.state.toggle_watch)
        sl.addWidget(self.side_toggle)
        col.addWidget(status)
        col.addSpacing(6)
        col.addWidget(label(f"версия {__version__}", "caption"), 0, Qt.AlignHCenter)
        return side

    def _sync_watch(self, on: bool) -> None:
        self.side_toggle.set_checked_silent(on)
        color = C["success"] if on else C["muted2"]
        self.dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        self.status_sub.setText("включено" if on else "на паузе")

    # ---------- навигация ----------

    def go(self, index: int) -> None:
        self.nav_buttons[index].setChecked(True)
        self.stack.setCurrentIndex(index)
        page = self.pages[index]
        if hasattr(page, "refresh"):
            page.refresh()  # перерисовать «5 мин назад» и свежие цифры

    # ---------- действия ----------

    def run_now(self, folder: Optional[Path] = None) -> None:
        try:
            plans = self.state.plan(folder)
        except ConfigError as e:
            warn(self, str(e))
            return
        if not plans:
            self.state.toast.emit("Нет доступных папок. Добавь их на вкладке «Папки»", "danger")
            return
        if sum(len(ops) for _f, ops, _t in plans) == 0:
            self.state.toast.emit("Нечего разбирать: всё уже на своих местах", "success")
            return
        dlg = PreviewDialog(plans, self)
        if dlg.exec_() == QDialog.Accepted:
            self.state.apply(plans, "run")

    # ---------- радиальное меню ----------

    def radial_items(self) -> List[dict]:
        """Пункты круга по настройкам; удалённые сценарии пропускаются."""
        try:
            cfg = self.state.parsed()
        except ConfigError:
            return []
        names = {sc.name for sc in cfg.scenarios}
        out = []
        for it in cfg.radial.items:
            kind, _, name = it.partition(":")
            if kind == "builtin":
                label_, icon_ = radial.BUILTINS[name]
                if name == "watch":
                    label_, icon_ = ("Пауза", "pause") if self.state.watching else ("Слежение", "play")
                out.append({"id": it, "label": label_, "icon": icon_})
            elif name in names:
                out.append({"id": it, "label": name, "icon": "scenario"})
        return out

    def show_radial(self) -> None:
        items = self.radial_items()
        if items:
            self.radial_menu.set_items(items)
            self.radial_menu.popup()

    def run_radial(self, item_id: str) -> None:
        kind, _, name = item_id.partition(":")
        if kind == "scenario":
            for sc in self.state.scenarios:
                if sc.get("name") == name:
                    self.automation.run(sc, announce=True)
                    return
        elif name == "sort":
            self.show_and_raise()
            self.run_now()
        elif name == "undo":
            self.state.undo()
        elif name == "watch":
            self.state.toggle_watch()
        elif name == "downloads":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path.home() / "Downloads")))
        elif name == "open":
            self.show_and_raise()

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True
        self.state.settings.setValue("geometry", self.saveGeometry())
        self.automation.stop()
        self.state.shutdown()
        QApplication.quit()

    # ---------- события окна ----------

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.toast.reposition()

    def closeEvent(self, e) -> None:
        if self._tray_ok and self.state.flag("close_to_tray", True) and not self._quitting:
            e.ignore()
            self.state.settings.setValue("geometry", self.saveGeometry())
            self.hide()
            self.hidden_to_tray.emit()
        else:
            self.quit_app()
            e.accept()
