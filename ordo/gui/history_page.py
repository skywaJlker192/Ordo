"""Журнал: пакеты операций, раскрываются до отдельных файлов, любой пакет можно откатить."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ..cli import human_size
from ..describe import SOURCE_LABELS
from .fmt import VERBS_PAST, ago, tail
from .rules_page import confirm
from .state import AppState
from .theme import C
from .widgets import Card, EmptyState, PageHeader, button

_BATCH_ID = Qt.UserRole
_PLACEHOLDER = Qt.UserRole + 1


class HistoryPage(QWidget):
    def __init__(self, state: AppState, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.state = state
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        header = PageHeader("Журнал", "Каждая операция записана. Любой пакет можно вернуть как было")
        self.undo_sel = button("Отменить выбранный", "danger", "undo", self._undo_selected)
        self.undo_last = button("Отменить последний", "default", "undo", self._undo_last)
        header.add_action(self.undo_last)
        header.add_action(self.undo_sel)
        root.addWidget(header)

        card = Card(padding=8)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Пакет", "Когда", "Откуда", "Операций", "Статус"])
        self.tree.setIndentation(20)
        self.tree.setMinimumHeight(420)
        head = self.tree.header()
        head.setStretchLastSection(False)
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, width in ((1, 170), (2, 150), (3, 100), (4, 110)):
            head.setSectionResizeMode(col, QHeaderView.Fixed)
            self.tree.setColumnWidth(col, width)
        card.body.addWidget(self.tree)
        self.empty = EmptyState("history", "Журнал пуст", "Когда Ordo что-то разберёт, пакеты появятся здесь")
        card.body.addWidget(self.empty)
        root.addWidget(card, 1)

        self.tree.itemExpanded.connect(self._load_children)
        self.tree.itemSelectionChanged.connect(self._sync_buttons)
        state.journal_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        selected = self._current_batch()
        self.tree.clear()
        rows = self.state.journal.history(150)
        self.tree.setVisible(bool(rows))
        self.empty.setVisible(not rows)
        for r in rows:
            undone = bool(r["undone"])
            item = QTreeWidgetItem([
                f"#{r['id']}", ago(r["ts"]), SOURCE_LABELS.get(r["source"], r["source"]),
                str(r["n"]), "отменён" if undone else "применён",
            ])
            item.setData(0, _BATCH_ID, r["id"])
            item.setForeground(4, QColor(C["warning"] if undone else C["success"]))
            for c in (1, 2, 3):
                item.setForeground(c, QColor(C["muted"]))
            if undone:
                item.setForeground(0, QColor(C["muted2"]))
            if r["n"]:
                ph = QTreeWidgetItem(["…"])
                ph.setData(0, _PLACEHOLDER, True)
                item.addChild(ph)
            self.tree.addTopLevelItem(item)
            if selected == r["id"]:
                self.tree.setCurrentItem(item)
        self._sync_buttons()

    def _load_children(self, item: QTreeWidgetItem) -> None:
        if item.childCount() != 1 or not item.child(0).data(0, _PLACEHOLDER):
            return
        item.takeChild(0)
        for op in self.state.journal.ops(item.data(0, _BATCH_ID)):
            src, dst = Path(op["src"]), Path(op["dst"])
            where = dst.name if op["kind"] == "rename" else tail(dst.parent)
            child = QTreeWidgetItem([
                f"{src.name}   →   {where}    ·    {VERBS_PAST.get(op['kind'], op['kind']).lower()}, "
                f"{human_size(op['size'])}, правило «{op['rule']}»"
            ])
            child.setForeground(0, QColor(C["muted"]))
            item.addChild(child)
            child.setFirstColumnSpanned(True)  # только после addChild, иначе не сработает

    def _current_batch(self) -> Optional[int]:
        item = self.tree.currentItem()
        if item is None:
            return None
        top = item.parent() or item
        return top.data(0, _BATCH_ID)

    def _sync_buttons(self) -> None:
        bid = self._current_batch()
        row = self.state.journal.batch_exists(bid) if bid else None
        self.undo_sel.setEnabled(bool(row) and not row["undone"])
        self.undo_last.setEnabled(self.state.journal.last_active_batch() is not None)

    def _undo_selected(self) -> None:
        bid = self._current_batch()
        if bid and confirm(self, "Отменить пакет", f"Вернуть файлы пакета #{bid} на прежние места?",
                           "Отменить пакет"):
            self.state.undo(bid)

    def _undo_last(self) -> None:
        last = self.state.journal.last_active_batch()
        if last and confirm(self, "Отменить последний пакет", f"Вернуть файлы пакета #{last} на прежние места?",
                            "Отменить пакет"):
            self.state.undo(last)
