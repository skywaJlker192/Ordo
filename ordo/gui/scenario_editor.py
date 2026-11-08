"""Редактор сценария из блоков-пазлов: слева палитра, справа столбик «когда → делать»."""
from __future__ import annotations

from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QFrame, QHBoxLayout, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from ..config_io import validate_scenario
from . import icons
from .blocks import BlockStack, Palette, make_block
from .theme import C
from .widgets import button, label

NEW_SCENARIO: Dict[str, Any] = {
    "name": "Новый сценарий",
    "trigger": {"type": "hotkey", "keys": "Ctrl+Alt+K"},
    "actions": [{"do": "notify", "text": "Привет из Ordo"}],
}


class ScenarioEditor(QDialog):
    def __init__(self, scenario: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None,
                 automation=None):
        super().__init__(parent)
        self._original = dict(scenario) if scenario else dict(NEW_SCENARIO)
        self._is_new = scenario is None
        self._automation = automation
        self.result_scenario: Optional[Dict[str, Any]] = None

        self.setWindowTitle("Новый сценарий" if self._is_new else "Редактирование сценария")
        self.setWindowIcon(icons.app_icon())
        self.resize(980, 720)
        self.setMinimumSize(760, 520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(28, 24, 28, 10)
        tl.setSpacing(10)
        tl.addWidget(label("Новый сценарий" if self._is_new else "Сценарий", "title"))
        self.name = QLineEdit(self._original.get("name", ""))
        self.name.setPlaceholderText("Название, например «Чистая ссылка»")
        tl.addWidget(self.name)
        outer.addWidget(top)

        mid = QHBoxLayout()
        mid.setContentsMargins(28, 6, 28, 12)
        mid.setSpacing(22)
        self.palette = Palette()
        self.palette.setFixedWidth(210)
        self.palette.activated.connect(self._from_palette)
        mid.addWidget(self.palette)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setObjectName("Transparent")
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 4, 8, 4)
        self.stack = BlockStack()
        self.stack.changed.connect(self._clear_error)
        hl.addWidget(self.stack)
        hl.addStretch(1)
        scroll.setWidget(holder)
        mid.addWidget(scroll, 1)
        outer.addLayout(mid, 1)

        footer = QWidget()
        footer.setObjectName("Sidebar")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(28, 12, 28, 14)
        fl.setSpacing(8)
        self.error = label("", wrap=True)
        self.error.setStyleSheet(f"color: {C['danger']};")
        self.error.hide()
        fl.addWidget(self.error)
        btns = QHBoxLayout()
        self.test_btn = button("Проверить", "default", "scenario", self._test,
                               "Выполнить сценарий прямо сейчас")
        btns.addWidget(self.test_btn)
        btns.addStretch(1)
        btns.addWidget(button("Отмена", on_click=self.reject))
        btns.addWidget(button("Сохранить сценарий", "primary", "check", self._save))
        fl.addLayout(btns)
        outer.addWidget(footer)

        self._load()

    # ---- заполнение ----

    def _load(self) -> None:
        trig = self._original.get("trigger") or {}
        hat = make_block(trig) if trig else None
        if hat is not None:
            self.stack.set_hat(hat)
        for a in self._original.get("actions") or []:
            block = make_block(a) if isinstance(a, dict) else None
            if block is not None:
                self.stack.add_block(block)

    def _from_palette(self, kind: str, type_id: str) -> None:
        if kind == "trigger":
            block = make_block({"type": type_id})
            if block:
                self.stack.set_hat(block)
        else:
            block = make_block({"do": type_id})
            if block:
                self.stack.add_block(block)

    # ---- сборка и проверка ----

    def build(self) -> Dict[str, Any]:
        sc = dict(self._original)  # description, enabled и прочие ключи сохраняем
        sc["name"] = self.name.text().strip()
        sc["trigger"] = self.stack.trigger()
        sc["actions"] = self.stack.to_actions()
        sc.setdefault("enabled", True)
        return sc

    def _problem(self, sc: Dict[str, Any]) -> Optional[str]:
        if not sc["trigger"]:
            return "Добавь блок «Когда»: что запускает сценарий"
        if not sc["actions"]:
            return "Добавь хотя бы один блок «Делать»"
        return validate_scenario(sc)

    def _show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.show()

    def _clear_error(self) -> None:
        self.error.hide()

    def _test(self) -> None:
        sc = self.build()
        sc.setdefault("name", "Проверка")
        sc["name"] = sc["name"] or "Проверка"
        err = self._problem(sc)
        if err:
            self._show_error(err)
            return
        if self._automation is not None:
            self._automation.run(sc, announce=True)

    def _save(self) -> None:
        sc = self.build()
        err = self._problem(sc)
        if err:
            self._show_error(err)
            return
        self.result_scenario = sc
        self.accept()
