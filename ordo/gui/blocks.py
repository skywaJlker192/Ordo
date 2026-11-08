"""Блоки-пазлы как в Scratch: цветные детали с вырезом сверху и выступом снизу, перетаскиваются мышью."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Type

from PyQt5.QtCore import QMimeData, QPoint, QRectF, QTime, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QDrag, QKeySequence, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QFileDialog, QFrame, QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QSpinBox, QTimeEdit, QVBoxLayout,
    QWidget,
)

from ..describe import CLIP_MODE_LABELS
from ..hotkeys import normalize
from . import theme
from .theme import C, set_prop

MIME = "application/x-ordo-block"
TAB = 7  # высота выступа; соседние блоки перекрываются на эту величину, и пазлы «защёлкиваются»

COLORS = {
    "trigger": "#D4880F",
    "files": "#5B6CFF",
    "system": "#16A394",
    "clipboard": "#CF4B8C",
    "notify": "#8B5CF6",
}


def _block_qss() -> str:
    return f"""
    QLabel {{ color: #FFFFFF; font-weight: 600; background: transparent; }}
    QLineEdit, QComboBox, QSpinBox, QTimeEdit {{
        background: rgba(255, 255, 255, 48); border: none; border-radius: 11px;
        padding: 4px 11px; color: #FFFFFF; min-height: 20px;
        selection-background-color: rgba(0, 0, 0, 90);
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTimeEdit:focus {{ background: rgba(255, 255, 255, 76); }}
    QLineEdit[invalid="true"] {{ background: rgba(120, 10, 10, 150); }}
    QComboBox {{ padding-right: 26px; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox::down-arrow {{ image: url({theme.asset('chev_down_white')}); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView {{
        background: {C['surface2']}; color: {C['text']}; border: 1px solid {C['border2']};
        selection-background-color: rgba(91, 108, 255, 70); selection-color: {C['accent_text']}; padding: 4px;
    }}
    QPushButton[blockx="true"] {{
        background: rgba(255, 255, 255, 40); border: none; color: #FFFFFF; padding: 3px 9px;
        font-weight: 700; border-radius: 11px; min-height: 20px;
    }}
    QPushButton[blockx="true"]:hover {{ background: rgba(0, 0, 0, 70); }}
    """


class HotkeyEdit(QLineEdit):
    """Поле «нажми сочетание»: вместо ввода текста ловит реальное нажатие клавиш."""

    def __init__(self, keys: str = ""):
        super().__init__(keys)
        self.setReadOnly(True)
        self.setPlaceholderText("нажми сочетание клавиш")
        self.setCursor(Qt.PointingHandCursor)

    def keyPressEvent(self, e) -> None:
        key = e.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr, Qt.Key_unknown):
            return  # одни модификаторы: ждём основную клавишу
        mods = e.modifiers()
        if key in (Qt.Key_Backspace, Qt.Key_Delete) and not mods:
            self.setText("")
            return
        parts = [name for flag, name in ((Qt.ControlModifier, "Ctrl"), (Qt.AltModifier, "Alt"),
                                         (Qt.ShiftModifier, "Shift"), (Qt.MetaModifier, "Win")) if mods & flag]
        parts.append(QKeySequence(key).toString(QKeySequence.PortableText))
        text = "+".join(parts)
        try:
            text = normalize(text)
            bad = False
        except ValueError:
            bad = True  # например, голая «L» без Ctrl: покажем красным, сохранить не даст
        self.setText(text)
        self.setToolTip("Нужна хотя бы одна клавиша Ctrl, Alt, Shift или Win" if bad else "")
        set_prop(self, "invalid", bad)


class Block(QWidget):
    """Одна деталь пазла. Наследники добавляют слова и поля, а to_dict() отдаёт данные для конфига."""

    changed = pyqtSignal()
    remove_requested = pyqtSignal(object)
    type_id = ""
    category = "files"
    is_hat = False

    def __init__(self) -> None:
        super().__init__()
        self._press: Optional[QPoint] = None
        self._has_stretch = False
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(42, 14 if self.is_hat else 8 + TAB, 10, 8 + TAB)
        self.row.setSpacing(8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(_block_qss())

    # ---- помощники для наследников ----

    def word(self, text: str) -> QLabel:
        lb = QLabel(text)
        self.row.addWidget(lb)
        return lb

    def field(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.row.addWidget(widget, stretch)
        self._has_stretch = self._has_stretch or stretch > 0
        return widget

    def watch(self, signal) -> None:
        signal.connect(lambda *_a: self.changed.emit())

    def small_button(self, text: str, tip: str, on_click) -> QPushButton:
        b = QPushButton(text)
        b.setProperty("blockx", "true")
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.clicked.connect(lambda _=False: on_click())
        self.row.addWidget(b)
        return b

    def finish(self) -> None:
        if not self._has_stretch:
            self.row.addStretch(1)
        if not self.is_hat:
            self.small_button("×", "Убрать блок", lambda: self.remove_requested.emit(self))

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    # ---- вид ----

    def _shape(self) -> QPainterPath:
        w, h = float(self.width()), float(self.height())
        bh = h - TAB
        r = 12.0
        rt = 22.0 if self.is_hat else r
        nx, nw = 26.0, 26.0
        p = QPainterPath()
        p.moveTo(rt, 0)
        if not self.is_hat:  # вырез сверху, куда входит выступ предыдущего блока
            p.lineTo(nx, 0)
            p.lineTo(nx + 5, TAB)
            p.lineTo(nx + nw - 5, TAB)
            p.lineTo(nx + nw, 0)
        p.lineTo(w - r, 0)
        p.arcTo(QRectF(w - 2 * r, 0, 2 * r, 2 * r), 90, -90)
        p.lineTo(w, bh - r)
        p.arcTo(QRectF(w - 2 * r, bh - 2 * r, 2 * r, 2 * r), 0, -90)
        p.lineTo(nx + nw, bh)  # выступ снизу
        p.lineTo(nx + nw - 5, bh + TAB)
        p.lineTo(nx + 5, bh + TAB)
        p.lineTo(nx, bh)
        p.lineTo(r, bh)
        p.arcTo(QRectF(0, bh - 2 * r, 2 * r, 2 * r), 270, -90)
        p.lineTo(0, rt)
        p.arcTo(QRectF(0, 0, 2 * rt, 2 * rt), 180, -90)
        p.closeSubpath()
        return p

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(COLORS[self.category])
        p.setPen(QPen(color.darker(128), 1.4))
        p.setBrush(color)
        p.drawPath(self._shape())
        if not self.is_hat:  # «ручка» для перетаскивания
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 120))
            cy = (self.height() - TAB) / 2.0 + (TAB / 2.0)
            for dx in (14, 22):
                for dy in (-8, 0, 8):
                    p.drawEllipse(QRectF(dx - 2, cy + dy - 2, 4, 4))

    # ---- перетаскивание за ручку ----

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and not self.is_hat and e.x() < 36:
            self._press = e.pos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._press is not None and (e.pos() - self._press).manhattanLength() >= QApplication.startDragDistance():
            start, self._press = self._press, None
            self._drag(start)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._press = None
        self.unsetCursor()
        super().mouseReleaseEvent(e)

    def _drag(self, hotspot: QPoint) -> None:
        mime = QMimeData()
        mime.setData(MIME, json.dumps({"source": "stack", "id": id(self)}).encode("utf-8"))
        pixmap = QPixmap(self.size())
        pixmap.fill(Qt.transparent)
        self.render(pixmap, QPoint(), flags=QWidget.DrawChildren)  # без фона окна, только сам блок
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(pixmap)
        drag.setHotSpot(hotspot)
        fade = QGraphicsOpacityEffect(self)
        fade.setOpacity(0.35)
        self.setGraphicsEffect(fade)
        drag.exec_(Qt.MoveAction)
        self.setGraphicsEffect(None)
        self.unsetCursor()


# ---------------- триггеры ("Когда …") ----------------

class HotkeyBlock(Block):
    type_id, category, is_hat = "hotkey", "trigger", True

    def __init__(self, data: Optional[dict] = None):
        super().__init__()
        data = data or {}
        self.word("Когда нажато")
        self.keys = HotkeyEdit(data.get("keys", "Ctrl+Alt+L"))
        self.keys.setMinimumWidth(200)
        self.field(self.keys)
        self.watch(self.keys.textChanged)
        self.finish()

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "hotkey", "keys": self.keys.text().strip()}


class ScheduleBlock(Block):
    type_id, category, is_hat = "schedule", "trigger", True

    def __init__(self, data: Optional[dict] = None):
        super().__init__()
        data = data or {}
        self.word("Когда наступает")
        self.mode = QComboBox()
        for text, key in (("каждые", "every"), ("каждый день в", "daily"), ("по будням в", "weekdays")):
            self.mode.addItem(text, key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(data.get("mode", "every"))))
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 1440)
        self.minutes.setValue(int(data.get("minutes", 30)))
        self.minutes.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.minutes.setMinimumWidth(64)
        self.minutes_word = QLabel("мин.")
        self.at = QTimeEdit()
        self.at.setDisplayFormat("HH:mm")
        self.at.setTime(QTime.fromString(str(data.get("at", "09:00")), "HH:mm"))
        self.at.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.at.setMinimumWidth(72)
        for w in (self.mode, self.minutes, self.minutes_word, self.at):
            self.row.addWidget(w)
        self.mode.currentIndexChanged.connect(self._sync)
        for sig in (self.mode.currentIndexChanged, self.minutes.valueChanged, self.at.timeChanged):
            self.watch(sig)
        self._sync()
        self.finish()

    def _sync(self, *_a) -> None:
        every = self.mode.currentData() == "every"
        self.minutes.setVisible(every)
        self.minutes_word.setVisible(every)
        self.at.setVisible(not every)

    def to_dict(self) -> Dict[str, Any]:
        mode = self.mode.currentData()
        if mode == "every":
            return {"type": "schedule", "mode": mode, "minutes": self.minutes.value()}
        return {"type": "schedule", "mode": mode, "at": self.at.time().toString("HH:mm")}


class ClipboardBlock(Block):
    type_id, category, is_hat = "clipboard", "trigger", True

    def __init__(self, data: Optional[dict] = None):
        super().__init__()
        data = data or {}
        self.word("Когда скопировано")
        self.match = QComboBox()
        self.match.addItem("содержит", "contains")
        self.match.addItem("подходит под шаблон", "regex")
        self.match.setCurrentIndex(max(0, self.match.findData(data.get("match", "contains"))))
        self.text = QLineEdit(str(data.get("text", "")))
        self.text.setPlaceholderText("любой текст")
        self.field(self.match)
        self.field(self.text, 1)
        self.watch(self.match.currentIndexChanged)
        self.watch(self.text.textChanged)
        self.finish()

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "clipboard", "match": self.match.currentData(), "text": self.text.text()}


class StartupBlock(Block):
    type_id, category, is_hat = "startup", "trigger", True

    def __init__(self, data: Optional[dict] = None):
        super().__init__()
        self.word("Когда запускается Ordo")
        self.finish()

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "startup"}


# ---------------- действия ("Делать …") ----------------

class _TextActionBlock(Block):
    """Слово + одно текстовое поле на всю ширину: общая основа простых действий."""

    key = "text"
    label = ""
    placeholder = ""
    default = ""

    def __init__(self, data: Optional[dict] = None):
        super().__init__()
        data = data or {}
        self.word(self.label)
        self.edit = QLineEdit(str(data.get(self.key, self.default)))
        self.edit.setPlaceholderText(self.placeholder)
        self.field(self.edit, 1)
        self.watch(self.edit.textChanged)
        self._extra()
        self.finish()

    def _extra(self) -> None:
        pass


class SortBlock(_TextActionBlock):
    type_id, category = "sort", "files"
    key, label, placeholder = "folder", "Разобрать папку", "все папки под присмотром"

    def _extra(self) -> None:
        self.small_button("…", "Выбрать папку", self._browse)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Какую папку разобрать")
        if folder:
            self.edit.setText(folder)

    def to_dict(self) -> Dict[str, Any]:
        return {"do": "sort", "folder": self.edit.text().strip()}


class OpenBlock(_TextActionBlock):
    type_id, category = "open", "system"
    key, label, placeholder = "target", "Открыть", "программа, папка, файл или ссылка"

    def _extra(self) -> None:
        self.small_button("…", "Выбрать файл или программу", self._browse)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Что открыть")
        if path:
            self.edit.setText(path)

    def to_dict(self) -> Dict[str, Any]:
        return {"do": "open", "target": self.edit.text().strip()}


class NotifyBlock(_TextActionBlock):
    type_id, category = "notify", "notify"
    key, label, placeholder, default = "text", "Показать уведомление", "текст уведомления", "Готово"

    def to_dict(self) -> Dict[str, Any]:
        return {"do": "notify", "text": self.edit.text()}


class CopyTextBlock(_TextActionBlock):
    type_id, category = "copy_text", "clipboard"
    key, label, placeholder = "text", "Скопировать в буфер", "текст; можно {date}, {time}, {clipboard}"

    def to_dict(self) -> Dict[str, Any]:
        return {"do": "copy_text", "text": self.edit.text()}


class ClipTransformBlock(Block):
    type_id, category = "clip_transform", "clipboard"

    def __init__(self, data: Optional[dict] = None):
        super().__init__()
        data = data or {}
        self.word("Буфер обмена:")
        self.mode = QComboBox()
        for key, text in CLIP_MODE_LABELS.items():
            self.mode.addItem(text, key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(data.get("mode", "strip_utm"))))
        self.mode.setMinimumWidth(260)
        self.field(self.mode)
        self.watch(self.mode.currentIndexChanged)
        self.finish()

    def to_dict(self) -> Dict[str, Any]:
        return {"do": "clip_transform", "mode": self.mode.currentData()}


TRIGGERS: List[Tuple[str, Type[Block], str]] = [
    ("hotkey", HotkeyBlock, "Нажато сочетание клавиш"),
    ("schedule", ScheduleBlock, "Наступило время"),
    ("clipboard", ClipboardBlock, "Скопирован текст"),
    ("startup", StartupBlock, "Запущен Ordo"),
]
ACTIONS: List[Tuple[str, Type[Block], str]] = [
    ("sort", SortBlock, "Разобрать папку"),
    ("open", OpenBlock, "Открыть"),
    ("notify", NotifyBlock, "Показать уведомление"),
    ("copy_text", CopyTextBlock, "Скопировать в буфер"),
    ("clip_transform", ClipTransformBlock, "Обработать буфер"),
]
_BY_TRIGGER = {k: cls for k, cls, _t in TRIGGERS}
_BY_ACTION = {k: cls for k, cls, _t in ACTIONS}


def make_block(data: Dict[str, Any]) -> Optional[Block]:
    """Блок по данным из конфига: у триггера есть type, у действия do. Неизвестное вернёт None."""
    cls = _BY_TRIGGER.get(data.get("type")) if "type" in data else _BY_ACTION.get(data.get("do"))
    return cls(data) if cls else None


# ---------------- холст и палитра ----------------

class BlockStack(QWidget):
    """Столбик блоков: сверху триггер (шапка), ниже действия. Принимает перетаскивание."""

    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.hat: Optional[Block] = None
        self.blocks: List[Block] = []
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(-TAB)
        self._hint = QLabel("Перетащи сюда блок из палитры слева или просто нажми на него")
        self._hint.setAlignment(Qt.AlignCenter)
        self._hint.setFixedHeight(70)
        self._hint.setStyleSheet(
            f"border: 2px dashed {C['border2']}; border-radius: 14px; color: {C['muted']};")
        self._lay.addWidget(self._hint)
        self._lay.addStretch(1)
        self._line = QFrame(self)
        self._line.setStyleSheet(f"background: {C['accent_text']}; border-radius: 2px;")
        self._line.hide()

    # ---- состав ----

    def _offset(self) -> int:
        return 1 if self.hat is not None else 0

    def set_hat(self, block: Block) -> None:
        if self.hat is not None:
            self._lay.removeWidget(self.hat)
            self.hat.setParent(None)
            self.hat.deleteLater()
        self.hat = block
        block.changed.connect(self.changed)
        self._lay.insertWidget(0, block)
        self.changed.emit()

    def add_block(self, block: Block, index: Optional[int] = None) -> None:
        index = len(self.blocks) if index is None else max(0, min(index, len(self.blocks)))
        block.changed.connect(self.changed)
        block.remove_requested.connect(self.remove_block)
        self.blocks.insert(index, block)
        self._lay.insertWidget(self._offset() + index, block)
        self._hint.setVisible(False)
        self.changed.emit()

    def remove_block(self, block: Block) -> None:
        if block in self.blocks:
            self.blocks.remove(block)
            self._lay.removeWidget(block)
            block.setParent(None)
            block.deleteLater()
            self._hint.setVisible(not self.blocks)
            self.changed.emit()

    def move_block(self, block: Block, index: int) -> None:
        old = self.blocks.index(block)
        self.blocks.pop(old)
        self._lay.removeWidget(block)
        index = index - 1 if old < index else index
        index = max(0, min(index, len(self.blocks)))
        self.blocks.insert(index, block)
        self._lay.insertWidget(self._offset() + index, block)
        self.changed.emit()

    def trigger(self) -> Dict[str, Any]:
        return self.hat.to_dict() if self.hat else {}

    def to_actions(self) -> List[Dict[str, Any]]:
        return [b.to_dict() for b in self.blocks]

    # ---- перетаскивание ----

    @staticmethod
    def _payload(e) -> Optional[dict]:
        if not e.mimeData().hasFormat(MIME):
            return None
        try:
            return json.loads(bytes(e.mimeData().data(MIME)).decode("utf-8"))
        except ValueError:
            return None

    def _index_at(self, y: int) -> int:
        for i, b in enumerate(self.blocks):
            if y < b.geometry().center().y():
                return i
        return len(self.blocks)

    def _show_line(self, index: int) -> None:
        if index < len(self.blocks):
            y = self.blocks[index].geometry().top()
        elif self.blocks:
            y = self.blocks[-1].geometry().bottom() - TAB
        elif self.hat is not None:
            y = self.hat.geometry().bottom() - TAB
        else:
            y = 0
        self._line.setGeometry(8, y - 2, max(10, self.width() - 16), 4)
        self._line.show()
        self._line.raise_()

    def dragEnterEvent(self, e) -> None:
        if self._payload(e) is not None:
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        if self._payload(e) is not None:
            e.acceptProposedAction()
            self._show_line(self._index_at(e.pos().y()))

    def dragLeaveEvent(self, _e) -> None:
        self._line.hide()

    def dropEvent(self, e) -> None:
        payload = self._payload(e)
        self._line.hide()
        if payload is None:
            return
        index = self._index_at(e.pos().y())
        if payload.get("source") == "palette":
            if payload.get("kind") == "trigger":
                block = make_block({"type": payload["type"]})
                if block:
                    self.set_hat(block)
            else:
                block = make_block({"do": payload["type"]})
                if block:
                    self.add_block(block, index)
        else:
            block = next((b for b in self.blocks if id(b) == payload.get("id")), None)
            if block is not None:
                self.move_block(block, index)
        e.setDropAction(Qt.MoveAction)
        e.accept()


class PaletteItem(QFrame):
    """Образец блока в палитре: нажми, чтобы добавить, или перетащи на холст."""

    activated = pyqtSignal(str, str)  # вид (trigger/action), id типа

    def __init__(self, kind: str, type_id: str, category: str, text: str):
        super().__init__()
        self.kind, self.type_id, self.category, self.text = kind, type_id, category, text
        self._press: Optional[QPoint] = None
        self._hover = False
        self.setFixedHeight(38)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(COLORS[self.category])
        if self._hover:
            color = color.lighter(112)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height() - 3), 10, 10)
        p.setPen(QColor("#FFFFFF"))
        f = p.font()
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(14, 0, self.width() - 24, self.height() - 3), Qt.AlignVCenter | Qt.AlignLeft, self.text)

    def enterEvent(self, _e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = False
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._press = e.pos()

    def mouseMoveEvent(self, e) -> None:
        if self._press is not None and (e.pos() - self._press).manhattanLength() >= QApplication.startDragDistance():
            self._press = None
            mime = QMimeData()
            mime.setData(MIME, json.dumps(
                {"source": "palette", "kind": self.kind, "type": self.type_id}).encode("utf-8"))
            pixmap = QPixmap(self.size())
            pixmap.fill(Qt.transparent)
            self.render(pixmap, QPoint(), flags=QWidget.DrawChildren)
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(20, 16))
            drag.exec_(Qt.CopyAction)

    def mouseReleaseEvent(self, e) -> None:
        if self._press is not None and e.button() == Qt.LeftButton:
            self._press = None
            self.activated.emit(self.kind, self.type_id)


class Palette(QWidget):
    activated = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Transparent")
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        for heading, kind, entries in (("КОГДА", "trigger", TRIGGERS), ("ДЕЛАТЬ", "action", ACTIONS)):
            title = QLabel(heading)
            title.setProperty("role", "caption")
            title.setContentsMargins(2, 10 if kind == "action" else 0, 0, 2)
            col.addWidget(title)
            for type_id, cls, text in entries:
                item = PaletteItem(kind, type_id, cls.category, text)
                item.activated.connect(self.activated)
                col.addWidget(item)
        col.addStretch(1)
