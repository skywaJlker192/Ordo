"""Окно предпросмотра: что именно Ordo сделает с файлами, и кнопка «Применить»."""
from __future__ import annotations

from collections import OrderedDict
from typing import List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ..cli import plural
from . import icons
from .fmt import VERBS_PAST, tail
from .state import Plan
from .theme import C
from .widgets import button, label, pill

_VERBS = {"move": "переместить", "copy": "скопировать", "rename": "переименовать", "trash": "в корзину"}


class PreviewDialog(QDialog):
    def __init__(self, plans: List[Plan], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Предпросмотр разбора")
        self.setWindowIcon(icons.app_icon())
        self.resize(860, 640)
        total_ops = sum(len(ops) for _f, ops, _t in plans)

        col = QVBoxLayout(self)
        col.setContentsMargins(28, 24, 28, 20)
        col.setSpacing(12)
        col.addWidget(label("Что сделает Ordo", "title"))
        col.addWidget(label("Пока ничего не тронуто. После применения всё можно откатить кнопкой «Отменить».",
                            "muted"))

        stats = QHBoxLayout()
        stats.setSpacing(8)
        stats.addWidget(pill(plural(total_ops, "операция", "операции", "операций"), "accent"))
        touched = len({op.origin for _f, ops, _t in plans for op in ops})
        stats.addWidget(pill(f"файлов затронуто: {touched}", "muted"))
        stats.addStretch(1)
        col.addLayout(stats)

        tree = QTreeWidget()
        tree.setHeaderLabels(["Файл", "Что будет сделано"])
        tree.setColumnWidth(0, 360)
        tree.setIndentation(18)
        tree.setUniformRowHeights(True)
        col.addWidget(tree, 1)

        for folder, ops, total in plans:
            top = QTreeWidgetItem([f"{folder}", f"файлов в папке: {total}, к обработке: {len({o.origin for o in ops})}"])
            top.setIcon(0, icons.icon("folder", C["accent_text"]))
            top.setForeground(1, QColor(C["muted"]))
            tree.addTopLevelItem(top)
            by_rule: "OrderedDict[str, list]" = OrderedDict()
            for op in ops:
                by_rule.setdefault(op.rule, []).append(op)
            for rule, rule_ops in by_rule.items():
                r_item = QTreeWidgetItem([rule, plural(len(rule_ops), "операция", "операции", "операций")])
                r_item.setForeground(1, QColor(C["muted"]))
                top.addChild(r_item)
                for op in rule_ops:
                    dest = op.dst.name if op.kind == "rename" else tail(op.dst.parent) + "/"
                    leaf = QTreeWidgetItem([op.src.name, f"{_VERBS[op.kind]}  →  {dest}"])
                    leaf.setForeground(1, QColor(C["muted"]))
                    r_item.addChild(leaf)
            top.setExpanded(True)
            for i in range(top.childCount()):
                top.child(i).setExpanded(total_ops <= 60)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(button("Закрыть", on_click=self.reject))
        self.apply_btn = button(f"Применить ({total_ops})", "primary", "check", self.accept)
        self.apply_btn.setEnabled(total_ops > 0)
        footer.addWidget(self.apply_btn)
        col.addLayout(footer)
