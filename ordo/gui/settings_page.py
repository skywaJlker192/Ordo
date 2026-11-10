"""Настройки: запуск, трей, уведомления, корзина Ordo, данные и сброс."""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QHBoxLayout, QSpinBox, QVBoxLayout, QWidget

from .. import __version__, autostart, paths
from ..cli import plural
from ..engine import empty_trash
from .radial_settings import RadialCard
from .rules_page import confirm, warn
from .state import AppState
from .widgets import Card, PageHeader, Toggle, button, divider, label


class _Option(QWidget):
    """Строка настройки: заголовок, пояснение, переключатель справа."""

    def __init__(self, title: str, hint: str, checked: bool, enabled: bool = True):
        super().__init__()
        self.setObjectName("Transparent")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(label(title, "h3"))
        col.addWidget(label(hint, "caption", wrap=True))
        row.addLayout(col, 1)
        self.toggle = Toggle(checked)
        self.toggle.setEnabled(enabled)
        row.addWidget(self.toggle)


class SettingsPage(QWidget):
    def __init__(self, state: AppState, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.state = state
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        root.addWidget(PageHeader("Настройки", "Поведение приложения"))

        # --- запуск ---
        card = Card(spacing=6)
        card.body.addWidget(label("Запуск и трей", "h2"))
        win = autostart.supported()
        self.autostart = _Option(
            "Запускать вместе с Windows",
            "Ordo стартует свёрнутым в трей и сразу следит за папками" if win
            else "Доступно только в Windows",
            win and autostart.is_enabled(), enabled=win)
        self.autostart.toggle.toggled.connect(self._set_autostart)
        self.start_watch = _Option("Включать слежение при запуске",
                                   "Иначе Ordo ждёт, пока ты сам нажмёшь «Включить слежение»",
                                   state.flag("autostart_watch", True))
        self.start_watch.toggle.toggled.connect(lambda on: state.set_flag("autostart_watch", on))
        self.to_tray = _Option("Закрытие окна сворачивает в трей",
                               "Ordo продолжает работать у часов. Выход: правый клик по значку",
                               state.flag("close_to_tray", True))
        self.to_tray.toggle.toggled.connect(lambda on: state.set_flag("close_to_tray", on))
        self.notify = _Option("Уведомления о разобранных файлах",
                              "Короткое сообщение из трея, когда слежение что-то навело в порядок",
                              state.flag("notifications", True))
        self.notify.toggle.toggled.connect(lambda on: state.set_flag("notifications", on))
        for i, opt in enumerate((self.autostart, self.start_watch, self.to_tray, self.notify)):
            if i:
                card.body.addWidget(divider())
            card.body.addWidget(opt)
        root.addWidget(card)
        root.addWidget(RadialCard(state))

        # --- корзина ---
        trash = Card(spacing=8)
        trash.body.addWidget(label("Корзина Ordo", "h2"))
        trash.body.addWidget(label(
            "Сюда попадают файлы, которые правила отправили «в корзину». Это не системная корзина: "
            "отсюда файл можно вернуть откатом, пока ты её не очистишь.", "muted", wrap=True))
        self.trash_info = label("", "caption")
        trash.body.addWidget(self.trash_info)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(label("Удалить навсегда файлы старше", "muted"))
        self.days = QSpinBox()
        self.days.setRange(0, 3650)
        self.days.setValue(30)
        self.days.setSuffix(" дн.")
        self.days.setFixedWidth(104)
        row.addWidget(self.days)
        row.addWidget(button("Очистить", "danger", "trash", self._empty))
        row.addWidget(button("Открыть папку", "default", "folder", lambda: self._open(paths.trash_dir())))
        row.addStretch(1)
        trash.body.addLayout(row)
        root.addWidget(trash)

        # --- данные ---
        data = Card(spacing=8)
        data.body.addWidget(label("Данные", "h2"))
        data.body.addWidget(label(str(paths.ordo_home()), "mono"))
        data.body.addWidget(label("Здесь лежат конфиг с правилами (config.json), его резервная копия и журнал.",
                                  "caption", wrap=True))
        r2 = QHBoxLayout()
        r2.setSpacing(8)
        r2.addWidget(button("Открыть папку данных", "default", "folder", lambda: self._open(paths.ordo_home())))
        r2.addWidget(button("Добавить новые правила из пресета", "default", "plus", self._add_missing,
                            "Допишет в конец недостающие правила (шрифты, дизайн, «Всё остальное»). Твои не тронет"))
        r2.addWidget(button("Вернуть правила из пресета", "danger", "rotate", self._reset))
        r2.addStretch(1)
        data.body.addLayout(r2)
        root.addWidget(data)

        about = label(f"Ordo {__version__}  ·  порядок в файлах", "caption")
        root.addWidget(about)
        root.addStretch(1)
        state.journal_changed.connect(self.refresh_trash)
        self.refresh_trash()

    def refresh_trash(self) -> None:
        count, size = self.state.trash_summary()
        self.trash_info.setText(
            f"Сейчас в корзине: {plural(count, 'файл', 'файла', 'файлов')} · {size}" if count else "Корзина пуста")

    def _open(self, path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _empty(self) -> None:
        days = self.days.value()
        text = ("Удалить навсегда ВСЁ из корзины Ordo? Вернуть будет нельзя." if days == 0
                else f"Удалить навсегда файлы корзины старше {days} дн.? Вернуть будет нельзя.")
        if confirm(self, "Очистить корзину", text, "Удалить навсегда", danger=True):
            removed = empty_trash(days)
            self.state.toast.emit(f"Удалено навсегда: {removed}", "success")
            self.refresh_trash()

    def _add_missing(self) -> None:
        count, err = self.state.add_missing_preset_rules()
        if err:
            warn(self, err)
        elif count:
            self.state.toast.emit(f"Добавлено правил: {count}. Они в конце списка", "success")
        else:
            self.state.toast.emit("Все правила пресета у тебя уже есть", "info")

    def _reset(self) -> None:
        if confirm(self, "Вернуть правила из пресета",
                   "Все твои правила заменятся стандартным набором для «Загрузок». "
                   "Прежний конфиг сохранится в config.json.bak.", "Заменить", danger=True):
            err = self.state.reset_to_preset()
            if err:
                warn(self, err)
            else:
                self.state.toast.emit("Правила возвращены к пресету", "success")

    def _set_autostart(self, on: bool) -> None:
        try:
            autostart.set_enabled(on)
        except OSError as e:
            warn(self, f"Не удалось изменить автозапуск: {e}")
            self.autostart.toggle.set_checked_silent(not on)
