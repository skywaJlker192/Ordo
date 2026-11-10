"""Редактор правила: условия и действия формой, без JSON. Внизу живое описание словами."""
from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLineEdit,
    QScrollArea, QVBoxLayout, QWidget,
)

from ..config_io import validate_rule
from ..describe import (
    ACTION_LABELS, FIELD_LABELS, FIELDS, OP_LABELS, PLACEHOLDER_HELP, TYPE_LABELS, describe_rule,
    ops_for,
)
from . import icons
from .theme import C, set_prop
from .widgets import Card, button, label

NEW_RULE: Dict[str, Any] = {
    "name": "Новое правило",
    "conditions": [{"field": "type", "op": "equals", "value": "image"}],
    "actions": [{"do": "move", "to": "Изображения/{year}"}],
}

_PLACEHOLDERS = {
    "size": "например, 10MB или 500KB",
    "age_days": "число дней, например 30",
}


class ParamEdit(QLineEdit):
    focused = pyqtSignal(object)

    def focusInEvent(self, e) -> None:
        super().focusInEvent(e)
        self.focused.emit(self)


class ConditionRow(QFrame):
    changed = pyqtSignal()
    removed = pyqtSignal(object)

    def __init__(self, cond: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("CardInner")
        self._loading = True
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 8, 8)
        row.setSpacing(8)

        self.field = QComboBox()
        for f in FIELDS:
            self.field.addItem(FIELD_LABELS[f], f)
        self.op = QComboBox()
        for combo, chars in ((self.field, 20), (self.op, 16)):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(chars)
        self.edit = QLineEdit()
        self.choice = QComboBox()
        self.remove_btn = button("", "icon-danger", "x", tooltip="Убрать условие")

        row.addWidget(self.field, 3)
        row.addWidget(self.op, 2)
        row.addWidget(self.edit, 4)
        row.addWidget(self.choice, 4)
        row.addWidget(self.remove_btn)

        self.field.currentIndexChanged.connect(self._on_field)
        self.op.currentIndexChanged.connect(self._on_op)
        self.edit.textChanged.connect(self._emit)
        self.choice.currentIndexChanged.connect(self._emit)
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self))

        self._load(cond or NEW_RULE["conditions"][0])
        self._loading = False

    # ---- загрузка / выгрузка ----

    def _fill_ops(self, field: str, keep: Optional[str] = None) -> None:
        self.op.blockSignals(True)
        self.op.clear()
        for op in ops_for(field):
            self.op.addItem(OP_LABELS[op], op)
        idx = self.op.findData(keep) if keep else 0
        self.op.setCurrentIndex(max(0, idx))
        self.op.blockSignals(False)

    def _fill_choice(self, field: str) -> None:
        self.choice.blockSignals(True)
        self.choice.clear()
        if field == "type":
            for key, text in TYPE_LABELS.items():
                self.choice.addItem(text.capitalize(), key)
        else:  # mismatch
            self.choice.addItem("да", True)
            self.choice.addItem("нет", False)
        self.choice.blockSignals(False)

    def _sync_widgets(self) -> None:
        field = self.field.currentData()
        use_choice = field in ("type", "mismatch")
        self.choice.setVisible(use_choice)
        self.edit.setVisible(not use_choice)
        self.op.setVisible(field != "mismatch")
        if not use_choice:
            if self.op.currentData() == "regex":
                self.edit.setPlaceholderText("регулярное выражение, например (чек|договор)")
            else:
                self.edit.setPlaceholderText(
                    _PLACEHOLDERS.get(field, "значение; несколько через запятую = любое из них"))

    def _load(self, cond: Dict[str, Any]) -> None:
        field = cond.get("field") if cond.get("field") in FIELDS else "type"
        op, value = cond.get("op"), cond.get("value")
        self.field.setCurrentIndex(self.field.findData(field))
        self._fill_ops(field, op)
        if field in ("type", "mismatch"):
            self._fill_choice(field)
            if field == "mismatch":
                flag = bool(value) if op != "not_equals" else not bool(value)
                self.choice.setCurrentIndex(self.choice.findData(flag))
            else:
                idx = self.choice.findData(value) if isinstance(value, str) else -1
                if idx < 0:  # несколько типов сразу или неизвестный: оставляем как есть
                    items = value if isinstance(value, list) else [value]
                    shown = ", ".join(TYPE_LABELS.get(str(v), str(v)) for v in items)
                    self.choice.addItem(shown, value)
                    idx = self.choice.count() - 1
                self.choice.setCurrentIndex(idx)
        else:
            self.edit.setText(", ".join(map(str, value)) if isinstance(value, list) else
                              "" if value is None else str(value))
        self._sync_widgets()

    def to_dict(self) -> Dict[str, Any]:
        field = self.field.currentData()
        if field == "mismatch":
            return {"field": field, "op": "equals", "value": bool(self.choice.currentData())}
        op = self.op.currentData()
        if field == "type":
            return {"field": field, "op": op, "value": self.choice.currentData()}
        text = self.edit.text().strip()
        if field == "age_days":
            try:
                num = float(text.replace(",", "."))
                return {"field": field, "op": op, "value": int(num) if num.is_integer() else num}
            except ValueError:
                return {"field": field, "op": op, "value": text}
        if field == "size" or op == "regex":
            return {"field": field, "op": op, "value": text}
        parts = [p.strip() for p in text.split(",") if p.strip()]
        value: Any = parts[0] if len(parts) == 1 else parts if parts else ""
        return {"field": field, "op": op, "value": value}

    # ---- реакции ----

    def _on_field(self, *_args) -> None:
        field = self.field.currentData()
        self._fill_ops(field)
        if field in ("type", "mismatch"):
            self._fill_choice(field)
        self._sync_widgets()
        self._emit()

    def _on_op(self, *_args) -> None:
        self._sync_widgets()
        self._emit()

    def _emit(self, *_args) -> None:
        if not self._loading:
            self.changed.emit()


class ActionRow(QFrame):
    changed = pyqtSignal()
    removed = pyqtSignal(object)
    param_focused = pyqtSignal(object)

    def __init__(self, action: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("CardInner")
        self._loading = True
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 8, 8)
        row.setSpacing(8)
        self.kind = QComboBox()
        for k, text in ACTION_LABELS.items():
            self.kind.addItem(text, k)
        self.kind.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.kind.setMinimumContentsLength(20)
        self.param = ParamEdit()
        self.browse = button("Обзор", "default", "folder", tooltip="Выбрать папку на диске")
        self.remove_btn = button("", "icon-danger", "x", tooltip="Убрать действие")
        row.addWidget(self.kind)
        row.addWidget(self.param, 1)
        row.addWidget(self.browse)
        row.addWidget(self.remove_btn)

        self.kind.currentIndexChanged.connect(self._on_kind)
        self.param.textChanged.connect(self._emit)
        self.param.focused.connect(self._on_param_focus)
        self.browse.clicked.connect(self._browse)
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self))

        action = action or NEW_RULE["actions"][0]
        kind = action.get("do") if action.get("do") in ACTION_LABELS else "move"
        self.kind.setCurrentIndex(self.kind.findData(kind))
        self.param.setText(str(action.get("template" if kind == "rename" else "to", "")))
        self._sync()
        self._loading = False

    def _sync(self) -> None:
        kind = self.kind.currentData()
        self.param.setVisible(kind != "trash")
        self.browse.setVisible(kind in ("move", "copy"))
        self.param.setPlaceholderText(
            "{stem}.{real_ext}" if kind == "rename" else "Папка: Изображения/{year} или D:\\Фото")

    def _on_kind(self, *_a) -> None:
        self._sync()
        self._emit()

    def _on_param_focus(self, widget=None) -> None:
        self.param_focused.emit(widget if widget is not None else self.param)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Куда класть файлы")
        if folder:
            self.param.setText(folder)

    def _emit(self, *_a) -> None:
        if not self._loading:
            self.changed.emit()

    def to_dict(self) -> Dict[str, Any]:
        kind = self.kind.currentData()
        if kind == "trash":
            return {"do": "trash"}
        text = self.param.text().strip()
        return {"do": kind, "template": text} if kind == "rename" else {"do": kind, "to": text}


class RuleEditor(QDialog):
    def __init__(self, rule: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._original = dict(rule) if rule else dict(NEW_RULE)
        self._is_new = rule is None
        self._cond_rows: List[ConditionRow] = []
        self._act_rows: List[ActionRow] = []
        self._last_param: Optional[ParamEdit] = None
        self.result_rule: Optional[Dict[str, Any]] = None

        self.setWindowTitle("Новое правило" if self._is_new else "Редактирование правила")
        self.setWindowIcon(icons.app_icon())
        self.resize(940, 800)
        self.setMinimumSize(720, 560)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("Page")
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        col = QVBoxLayout(body)
        col.setContentsMargins(28, 24, 28, 16)
        col.setSpacing(14)

        col.addWidget(label("Новое правило" if self._is_new else "Правило", "title"))

        self.name = QLineEdit(self._original.get("name", ""))
        self.name.setPlaceholderText("Название, например «Скриншоты»")
        self.desc = QLineEdit(self._original.get("description", ""))
        self.desc.setPlaceholderText("Заметка для себя (необязательно)")
        col.addWidget(self.name)
        col.addWidget(self.desc)

        # живое описание
        self.preview_card = Card(padding=14, spacing=6)
        self.preview_card.body.addWidget(label("ORDO ПРОЧИТАЕТ ТАК", "caption"))
        self.preview = label("", wrap=True)
        self.preview.setTextFormat(Qt.RichText)
        self.preview_card.body.addWidget(self.preview)
        col.addWidget(self.preview_card)

        # условия
        head = QHBoxLayout()
        head.addWidget(label("Если файл…", "h2"), 1)
        self.match = QComboBox()
        self.match.addItem("подходят все условия", "all")
        self.match.addItem("подходит любое из условий", "any")
        self.match.setCurrentIndex(self.match.findData(self._original.get("match", "all")))
        self.match.currentIndexChanged.connect(self._refresh)
        head.addWidget(self.match)
        col.addLayout(head)
        self.cond_box = QVBoxLayout()
        self.cond_box.setSpacing(8)
        col.addLayout(self.cond_box)
        col.addWidget(button("Условие", "ghost", "plus", lambda: self._add_condition(None)),
                      0, Qt.AlignLeft)

        # действия
        col.addSpacing(4)
        col.addWidget(label("То сделать (по порядку)", "h2"))
        self.act_box = QVBoxLayout()
        self.act_box.setSpacing(8)
        col.addLayout(self.act_box)
        col.addWidget(button("Действие", "ghost", "plus", lambda: self._add_action(None)),
                      0, Qt.AlignLeft)

        # подстановки
        chips = Card(padding=14, spacing=8)
        chips.body.addWidget(label("Подстановки для путей и имён: клик вставляет в поле", "caption"))
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (name, help_text) in enumerate(PLACEHOLDER_HELP.items()):
            b = button("{" + name + "}", "default", tooltip=help_text)
            b.setStyleSheet(f"padding: 4px 10px; color: {C['accent_text']}; font-size: 12px;")
            b.clicked.connect(lambda _=False, n=name: self._insert_placeholder(n))
            grid.addWidget(b, i // 5, i % 5)
        grid.setColumnStretch(5, 1)
        chips.body.addLayout(grid)
        col.addWidget(chips)

        self.stop = QCheckBox("После этого правила остановиться и не проверять правила ниже")
        self.stop.setChecked(bool(self._original.get("stop", True)))
        self.stop.toggled.connect(self._refresh)
        col.addWidget(self.stop)
        col.addStretch(1)

        # низ окна
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
        btns.addStretch(1)
        btns.addWidget(button("Отмена", on_click=self.reject))
        self.save_btn = button("Сохранить правило", "primary", "check", self._save)
        btns.addWidget(self.save_btn)
        fl.addLayout(btns)
        outer.addWidget(footer)

        for c in self._original.get("conditions") or [None]:
            self._add_condition(c)
        for a in self._original.get("actions") or [None]:
            self._add_action(a)
        self._refresh()

    # ---- строки ----

    def _add_condition(self, cond: Optional[Dict[str, Any]]) -> None:
        row = ConditionRow(cond)
        row.changed.connect(self._refresh)
        row.removed.connect(self._remove_condition)
        self._cond_rows.append(row)
        self.cond_box.addWidget(row)
        self._refresh()

    def _remove_condition(self, row: ConditionRow) -> None:
        self._cond_rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._refresh()

    def _remember_param(self, widget=None) -> None:
        if widget is not None:
            self._last_param = widget

    def _add_action(self, act: Optional[Dict[str, Any]]) -> None:
        row = ActionRow(act)
        row.changed.connect(self._refresh)
        row.removed.connect(self._remove_action)
        row.param_focused.connect(self._remember_param)
        self._act_rows.append(row)
        self.act_box.addWidget(row)
        self._refresh()

    def _remove_action(self, row: ActionRow) -> None:
        self._act_rows.remove(row)
        if self._last_param is row.param:
            self._last_param = None
        row.setParent(None)
        row.deleteLater()
        self._refresh()

    def _insert_placeholder(self, name: str) -> None:
        target = self._last_param
        if target is None or not target.isVisibleTo(self):
            target = next((r.param for r in self._act_rows if r.param.isVisibleTo(self)), None)
        if target is not None:
            target.insert("{" + name + "}")
            target.setFocus()

    # ---- сбор и проверка ----

    def _collect(self) -> Dict[str, Any]:
        rule = dict(self._original)
        rule["name"] = self.name.text().strip() or "Новое правило"
        desc = self.desc.text().strip()
        if desc:
            rule["description"] = desc
        else:
            rule.pop("description", None)
        rule["match"] = self.match.currentData()
        rule["stop"] = self.stop.isChecked()
        rule["conditions"] = [r.to_dict() for r in self._cond_rows]
        rule["actions"] = [r.to_dict() for r in self._act_rows]
        return rule

    def _refresh(self, *_a) -> None:
        rule = self._collect()
        cond, act = describe_rule(rule)
        tail = "" if rule["stop"] else " <span style='color:%s'>Дальше проверит и остальные правила.</span>" % C["muted"]
        self.preview.setText(
            f"<span style='color:{C['accent_text']};font-weight:600'>Если</span> {html.escape(cond)}, "
            f"<span style='color:{C['accent_text']};font-weight:600'>то</span> {html.escape(act)}.{tail}")
        if self.error.isVisible():
            self._show_error(validate_rule(rule))

    def _show_error(self, text: Optional[str]) -> None:
        self.error.setVisible(bool(text))
        self.error.setText(text or "")

    def _save(self) -> None:
        rule = self._collect()
        err = validate_rule(rule)
        if err:
            self._show_error(err)
            return
        self.result_rule = rule
        self.accept()
