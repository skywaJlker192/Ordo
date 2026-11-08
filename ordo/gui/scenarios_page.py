"""Сценарии: карточки «когда → то», включение, запуск, редактирование, шаблоны, импорт и экспорт."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget,
)

from .. import scenarios as sc_mod
from ..config_io import validate_scenario
from ..describe import describe_scenario
from .dashboard import clear_layout
from .rules_page import confirm, warn
from .scenario_editor import ScenarioEditor
from .state import AppState
from .widgets import Card, EmptyState, PageHeader, Toggle, button, label, pill


def _tag(text: str) -> QLabel:
    t = QLabel(text)
    t.setProperty("chip", "true")
    t.setFixedWidth(64)
    t.setAlignment(Qt.AlignCenter)
    return t


class ScenarioCard(Card):
    def __init__(self, index: int, sc: Dict[str, Any], h: Dict[str, Callable]):
        super().__init__(padding=14, spacing=0)
        enabled = bool(sc.get("enabled", True))
        row = QHBoxLayout()
        row.setSpacing(14)
        self.body.addLayout(row)

        text = QWidget()
        text.setObjectName("Transparent")
        col = QVBoxLayout(text)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(label(sc.get("name", "Без названия"), "h2"))
        if not enabled:
            head.addWidget(pill("выключено", "muted"))
        head.addStretch(1)
        col.addLayout(head)
        when, then = describe_scenario(sc)
        for tag, line in (("КОГДА", when), ("ТО", then)):
            r = QHBoxLayout()
            r.setSpacing(10)
            r.addWidget(_tag(tag), 0, Qt.AlignTop)
            r.addWidget(label(line, "muted", wrap=True), 1)
            col.addLayout(r)
        if sc.get("description"):
            col.addWidget(label(sc["description"], "caption", wrap=True))
        if not enabled:
            fade = QGraphicsOpacityEffect(text)
            fade.setOpacity(0.5)
            text.setGraphicsEffect(fade)
        row.addWidget(text, 1)

        controls = QHBoxLayout()
        controls.setSpacing(2)
        toggle = Toggle(enabled)
        toggle.setToolTip("Включить или выключить сценарий")
        toggle.toggled.connect(lambda on: h["toggle"](index, on))
        controls.addWidget(toggle)
        controls.addSpacing(8)
        controls.addWidget(button("", "icon", "scenario", lambda: h["run"](index), "Выполнить сейчас"))
        controls.addWidget(button("", "icon", "edit", lambda: h["edit"](index), "Изменить"))
        controls.addWidget(button("", "icon", "copy", lambda: h["copy"](index), "Дублировать"))
        controls.addWidget(button("", "icon-danger", "trash", lambda: h["delete"](index), "Удалить"))
        row.addLayout(controls)


class ScenariosPage(QWidget):
    def __init__(self, state: AppState, automation, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.state = state
        self.automation = automation
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        header = PageHeader("Сценарии", "Клавиша, время или буфер запускают цепочку действий")
        self.templates_btn = button("Шаблоны", "default", "scenario", self._templates_menu)
        header.add_action(self.templates_btn)
        header.add_action(button("Импорт", "default", "import", self._import))
        header.add_action(button("Экспорт", "default", "export", self._export))
        header.add_action(button("Новый сценарий", "primary", "plus", self._add))
        root.addWidget(header)

        self.box = QVBoxLayout()
        self.box.setSpacing(10)
        root.addLayout(self.box)
        root.addStretch(1)
        state.config_changed.connect(self.rebuild)
        self.rebuild()

    def rebuild(self) -> None:
        clear_layout(self.box)
        items = self.state.scenarios
        if not items:
            self.box.addWidget(EmptyState(
                "scenario", "Сценариев пока нет",
                "Возьми готовый из «Шаблонов» или собери свой из блоков"))
            return
        handlers = {"toggle": self._toggle, "run": self._run, "edit": self._edit,
                    "copy": self._copy, "delete": self._delete}
        for i, sc in enumerate(items):
            self.box.addWidget(ScenarioCard(i, sc, handlers))

    def _apply(self, items: List[Dict[str, Any]]) -> bool:
        err = self.state.set_scenarios(items)
        if err:
            warn(self, err)
            self.rebuild()
            return False
        return True

    def _toggle(self, i: int, on: bool) -> None:
        items = copy.deepcopy(self.state.scenarios)
        items[i]["enabled"] = on
        self._apply(items)

    def _run(self, i: int) -> None:
        self.automation.run(self.state.scenarios[i], announce=True)

    def _edit(self, i: int) -> None:
        dlg = ScenarioEditor(self.state.scenarios[i], self.window(), self.automation)
        if dlg.exec_() and dlg.result_scenario:
            items = copy.deepcopy(self.state.scenarios)
            items[i] = dlg.result_scenario
            self._apply(items)

    def _add(self) -> None:
        dlg = ScenarioEditor(None, self.window(), self.automation)
        if dlg.exec_() and dlg.result_scenario:
            self._apply(copy.deepcopy(self.state.scenarios) + [dlg.result_scenario])

    def _copy(self, i: int) -> None:
        items = copy.deepcopy(self.state.scenarios)
        dup = copy.deepcopy(items[i])
        dup["name"] = f"{dup.get('name', 'Сценарий')} (копия)"
        items.insert(i + 1, dup)
        self._apply(items)

    def _delete(self, i: int) -> None:
        name = self.state.scenarios[i].get("name", "без названия")
        if confirm(self, "Удалить сценарий", f"Удалить сценарий «{name}»?", "Удалить", danger=True):
            items = copy.deepcopy(self.state.scenarios)
            del items[i]
            self._apply(items)

    # ---- шаблоны ----

    def _templates_menu(self) -> None:
        menu = QMenu(self)
        for tpl in sc_mod.templates():
            act = menu.addAction(tpl["name"])
            act.setToolTip(tpl.get("description", ""))
            act.triggered.connect(lambda _=False, t=tpl: self._add_template(t))
        menu.exec_(self.templates_btn.mapToGlobal(self.templates_btn.rect().bottomLeft()))

    def _add_template(self, tpl: Dict[str, Any]) -> None:
        if self._apply(copy.deepcopy(self.state.scenarios) + [copy.deepcopy(tpl)]):
            self.state.toast.emit(f"Добавлен сценарий «{tpl['name']}»", "success")

    # ---- обмен ----

    def _export(self) -> None:
        if not self.state.scenarios:
            warn(self, "Экспортировать пока нечего: сценариев нет.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт сценариев", "ordo-scenarios.json",
                                              "Сценарии Ordo (*.json)")
        if not path:
            return
        data = {"ordo_scenarios": 1, "scenarios": self.state.scenarios}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.state.toast.emit(f"Сценариев в файле: {len(self.state.scenarios)}", "success")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Импорт сценариев", "", "Сценарии Ordo (*.json)")
        if path:
            self.import_file(Path(path))

    def import_file(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            warn(self, f"Не удалось прочитать файл: {e}")
            return
        incoming = data.get("scenarios") if isinstance(data, dict) and "scenarios" in data else data
        if isinstance(incoming, dict):
            incoming = [incoming]
        if not isinstance(incoming, list):
            warn(self, "В файле нет сценариев: ожидал список scenarios.")
            return
        good, bad = [], []
        for s in incoming:
            err = validate_scenario(s) if isinstance(s, dict) else "это не сценарий"
            if err:
                bad.append(err)
            else:
                good.append({**copy.deepcopy(s), "enabled": False})  # чужое не запускаем само
        if good:
            targets = [a.get("target") for s in good for a in s["actions"] if a.get("do") == "open"]
            if targets:
                lines = "\n".join(f"• {t}" for t in targets[:8])
                if not confirm(self, "Импорт сценариев",
                               f"Эти сценарии умеют открывать:\n{lines}\n\n"
                               "Они добавятся выключенными. Проверь и включи сам. Добавить?", "Добавить"):
                    return
            self._apply(copy.deepcopy(self.state.scenarios) + good)
        if bad:
            lines = "\n".join(f"• {e}" for e in bad[:5])
            warn(self, f"Добавлено: {len(good)}. Пропущено из-за ошибок: {len(bad)}\n\n{lines}")
        elif good:
            self.state.toast.emit(f"Добавлено выключенных сценариев: {len(good)}. Включи нужные", "success")
