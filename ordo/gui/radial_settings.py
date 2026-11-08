"""Карточка настроек радиального меню: включение, сочетание клавиш, какие пункты показывать."""
from __future__ import annotations

from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout

from ..radial import BUILTINS, MAX_ITEMS, default_radial
from .blocks import HotkeyEdit
from .rules_page import warn
from .state import AppState
from .widgets import Card, Toggle, button, label


class RadialCard(Card):
    def __init__(self, state: AppState):
        super().__init__(spacing=10)
        self.state = state
        head = QHBoxLayout()
        title = label("Радиальное меню", "h2")
        head.addWidget(title, 1)
        self.toggle = Toggle(True)
        head.addWidget(self.toggle)
        self.body.addLayout(head)
        self.body.addWidget(label(
            "Нажми сочетание в любой программе: у курсора раскроется круг. Выбери пункт мышью "
            "или цифрой 1-8, Esc закрывает.", "muted", wrap=True))

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(label("Сочетание клавиш", "muted"))
        self.keys = HotkeyEdit()
        self.keys.setFixedWidth(220)
        row.addWidget(self.keys)
        row.addWidget(button("Попробовать", "default", "scenario", self._try))
        row.addStretch(1)
        self.body.addLayout(row)

        self.body.addWidget(label("Пункты в круге (до восьми)", "caption"))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(6)
        self.body.addLayout(self.grid)
        self.hint = label("", "caption")
        self.body.addWidget(self.hint)

        self._boxes: List[QCheckBox] = []
        self._saving = False
        self.rebuild()
        state.config_changed.connect(self.rebuild)
        self.toggle.toggled.connect(lambda _on: self._save())
        self.keys.editingFinished.connect(self._save)
        self.keys.textChanged.connect(lambda _t: None)

    # ---- вид ----

    def rebuild(self) -> None:
        if self._saving:  # это мы сами сохранили: поля уже в нужном состоянии
            return
        cfg = self.state.raw.get("radial") or default_radial()
        self.toggle.set_checked_silent(bool(cfg.get("enabled", True)))
        self.keys.setText(cfg.get("hotkey", ""))
        chosen = set(cfg.get("items", []))
        for b in self._boxes:
            self.grid.removeWidget(b)
            b.setParent(None)
            b.deleteLater()
        self._boxes = []
        ids = [(f"builtin:{k}", v[0]) for k, v in BUILTINS.items()]
        ids += [(f"scenario:{s['name']}", f"Сценарий: {s['name']}") for s in self.state.scenarios]
        for i, (item_id, text) in enumerate(ids):
            box = QCheckBox(text)
            box.setProperty("item_id", item_id)
            box.setChecked(item_id in chosen)
            box.toggled.connect(lambda _on: self._save())
            self.grid.addWidget(box, i // 2, i % 2)
            self._boxes.append(box)
        self._sync_hint()

    def _selected(self) -> List[str]:
        return [b.property("item_id") for b in self._boxes if b.isChecked()]

    def _sync_hint(self) -> None:
        n = len(self._selected())
        self.hint.setText(f"Выбрано: {n} из {MAX_ITEMS}" if n else "Выбери хотя бы один пункт")

    # ---- сохранение ----

    def _save(self) -> None:
        self._sync_hint()
        new = {"enabled": self.toggle.isChecked(), "hotkey": self.keys.text().strip(),
               "items": self._selected()}
        if new == self.state.raw.get("radial"):
            return
        self._saving = True
        try:
            err = self.state.save({**self.state.raw, "radial": new})
        finally:
            self._saving = False
        if err:
            warn(self, err)
            self.rebuild()  # вернуть то, что реально сохранено

    def _try(self) -> None:
        win = self.window()
        if hasattr(win, "show_radial"):
            win.show_radial()
