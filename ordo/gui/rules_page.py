"""Правила: карточки по порядку (сверху вниз), включение, порядок, редактирование, импорт и экспорт."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget,
)

from ..config_io import validate_rule
from ..describe import describe_rule
from . import icons
from .dashboard import clear_layout
from .rule_editor import NEW_RULE, RuleEditor
from .state import AppState
from .theme import C
from .widgets import Card, EmptyState, PageHeader, Toggle, button, label, pill


def confirm(parent: QWidget, title: str, text: str, ok: str = "Да", danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.NoIcon)
    yes = box.addButton(ok, QMessageBox.AcceptRole)
    no = box.addButton("Отмена", QMessageBox.RejectRole)
    yes.setProperty("variant", "danger" if danger else "primary")
    yes.setCursor(Qt.PointingHandCursor)
    no.setCursor(Qt.PointingHandCursor)
    box.setDefaultButton(no)
    box.exec_()
    return box.clickedButton() is yes


def warn(parent: QWidget, text: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle("Ordo")
    box.setIcon(QMessageBox.NoIcon)
    box.setText(text)
    box.addButton("Понятно", QMessageBox.AcceptRole).setCursor(Qt.PointingHandCursor)
    box.exec_()


def _tag(text: str) -> QLabel:
    t = QLabel(text)
    t.setProperty("chip", "true")
    t.setFixedWidth(56)
    t.setAlignment(Qt.AlignCenter)
    return t


class RuleCard(Card):
    def __init__(self, index: int, rule: Dict[str, Any], total: int, h: Dict[str, Callable]):
        super().__init__(padding=14, spacing=0)
        enabled = bool(rule.get("enabled", True))
        row = QHBoxLayout()
        row.setSpacing(14)
        self.body.addLayout(row)

        badge = QLabel(str(index + 1))
        badge.setFixedSize(32, 32)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background: {C['surface2']}; border-radius: 16px; color: {C['muted']}; font-weight: 600;")
        row.addWidget(badge, 0, Qt.AlignTop)

        text = QWidget()
        text.setObjectName("Transparent")
        col = QVBoxLayout(text)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(label(rule.get("name", "Без названия"), "h2"))
        if not enabled:
            head.addWidget(pill("выключено", "muted"))
        if not rule.get("stop", True):
            head.addWidget(pill("проверяет дальше", "accent"))
        head.addStretch(1)
        col.addLayout(head)
        cond, act = describe_rule(rule)
        for tag, line in (("ЕСЛИ", cond), ("ТО", act)):
            r = QHBoxLayout()
            r.setSpacing(10)
            r.addWidget(_tag(tag), 0, Qt.AlignTop)
            lb = label(line, "muted", wrap=True)
            r.addWidget(lb, 1)
            col.addLayout(r)
        if rule.get("description"):
            col.addWidget(label(rule["description"], "caption", wrap=True))
        if not enabled:
            fade = QGraphicsOpacityEffect(text)
            fade.setOpacity(0.5)
            text.setGraphicsEffect(fade)
        row.addWidget(text, 1)

        controls = QHBoxLayout()
        controls.setSpacing(2)
        toggle = Toggle(enabled)
        toggle.setToolTip("Включить или выключить правило")
        toggle.toggled.connect(lambda on: h["toggle"](index, on))
        controls.addWidget(toggle)
        controls.addSpacing(8)
        up = button("", "icon", "up", lambda: h["move"](index, -1), "Выше (проверяется раньше)")
        down = button("", "icon", "down", lambda: h["move"](index, 1), "Ниже (проверяется позже)")
        up.setEnabled(index > 0)
        down.setEnabled(index < total - 1)
        controls.addWidget(up)
        controls.addWidget(down)
        controls.addWidget(button("", "icon", "edit", lambda: h["edit"](index), "Изменить"))
        controls.addWidget(button("", "icon", "copy", lambda: h["copy"](index), "Дублировать"))
        controls.addWidget(button("", "icon-danger", "trash", lambda: h["delete"](index), "Удалить"))
        row.addLayout(controls)


class RulesPage(QWidget):
    def __init__(self, state: AppState, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.state = state
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        header = PageHeader("Правила", "Файл проверяется сверху вниз, срабатывает первое подходящее правило")
        header.add_action(button("Импорт", "default", "import", self._import))
        header.add_action(button("Экспорт", "default", "export", self._export))
        header.add_action(button("Новое правило", "primary", "plus", self._add))
        root.addWidget(header)

        self.box = QVBoxLayout()
        self.box.setSpacing(10)
        root.addLayout(self.box)
        root.addStretch(1)
        state.config_changed.connect(self.rebuild)
        self.rebuild()

    def rebuild(self) -> None:
        clear_layout(self.box)
        rules = self.state.rules
        if not rules:
            empty = EmptyState("rules", "Правил пока нет",
                               "Добавь первое: например, «картинки → папка Изображения»")
            self.box.addWidget(empty)
            return
        handlers = {
            "toggle": self._toggle, "move": self._move, "edit": self._edit,
            "copy": self._copy, "delete": self._delete,
        }
        for i, rule in enumerate(rules):
            self.box.addWidget(RuleCard(i, rule, len(rules), handlers))

    # ---- изменения: всё через state.set_rules, он проверяет и пишет на диск ----

    def _apply(self, rules: List[Dict[str, Any]]) -> bool:
        err = self.state.set_rules(rules)
        if err:
            warn(self, err)
            self.rebuild()  # вернуть интерфейс к тому, что реально сохранено
            return False
        return True

    def _toggle(self, i: int, on: bool) -> None:
        rules = copy.deepcopy(self.state.rules)
        rules[i]["enabled"] = on
        self._apply(rules)

    def _move(self, i: int, delta: int) -> None:
        rules = copy.deepcopy(self.state.rules)
        j = i + delta
        if 0 <= j < len(rules):
            rules[i], rules[j] = rules[j], rules[i]
            self._apply(rules)

    def _edit(self, i: int) -> None:
        dlg = RuleEditor(self.state.rules[i], self.window())
        if dlg.exec_() and dlg.result_rule:
            rules = copy.deepcopy(self.state.rules)
            rules[i] = dlg.result_rule
            self._apply(rules)

    def _add(self) -> None:
        dlg = RuleEditor(None, self.window())
        if dlg.exec_() and dlg.result_rule:
            self._apply(copy.deepcopy(self.state.rules) + [dlg.result_rule])

    def _copy(self, i: int) -> None:
        rules = copy.deepcopy(self.state.rules)
        dup = copy.deepcopy(rules[i])
        dup["name"] = f"{dup.get('name', 'Правило')} (копия)"
        rules.insert(i + 1, dup)
        self._apply(rules)

    def _delete(self, i: int) -> None:
        name = self.state.rules[i].get("name", "без названия")
        if confirm(self, "Удалить правило", f"Удалить правило «{name}»?", "Удалить", danger=True):
            rules = copy.deepcopy(self.state.rules)
            del rules[i]
            self._apply(rules)

    # ---- обмен правилами ----

    def _export(self) -> None:
        if not self.state.rules:
            warn(self, "Экспортировать пока нечего: правил нет.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт правил", "ordo-rules.json", "Правила Ordo (*.json)")
        if not path:
            return
        data = {"ordo_rules": 1, "rules": self.state.rules}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.state.toast.emit(f"Правил в файле: {len(self.state.rules)}", "success")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Импорт правил", "", "Правила Ordo (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            warn(self, f"Не удалось прочитать файл: {e}")
            return
        incoming = data.get("rules") if isinstance(data, dict) and "rules" in data else data
        if isinstance(incoming, dict):  # один файл = одно правило
            incoming = [incoming]
        if not isinstance(incoming, list):
            warn(self, "В файле нет правил: ожидал список rules.")
            return
        good, bad = [], []
        for r in incoming:
            err = validate_rule(r) if isinstance(r, dict) else "это не правило"
            (bad if err else good).append((r, err))
        if good:
            self._apply(copy.deepcopy(self.state.rules) + [r for r, _ in good])
        if bad:
            lines = "\n".join(f"• {err}" for _r, err in bad[:5])
            warn(self, f"Импортировано: {len(good)}. Пропущено из-за ошибок: {len(bad)}\n\n{lines}")
        elif good:
            self.state.toast.emit(f"Импортировано правил: {len(good)}", "success")
