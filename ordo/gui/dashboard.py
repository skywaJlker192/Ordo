"""Главная: состояние слежения, цифры, график активности, рейтинг правил, последние действия."""
from __future__ import annotations

from typing import Callable, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..cli import human_size, plural
from .fmt import VERBS_PAST, ago, number, tail
from .state import AppState
from .widgets import (
    BarChart, Card, EmptyState, PageHeader, ShareBar, StatCard, button, divider, label, pill,
)


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)  # убрать из окна сразу, а не после deleteLater
            widget.deleteLater()
        elif item.layout():
            clear_layout(item.layout())


class DashboardPage(QWidget):
    def __init__(self, state: AppState, run_now: Callable[[], None], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.state = state
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        self.header = PageHeader("Главная", "")
        self.watch_btn = button("", "default", "pause", state.toggle_watch)
        self.run_btn = button("Разобрать сейчас", "primary", "bolt", run_now)
        self.header.add_action(self.watch_btn)
        self.header.add_action(self.run_btn)
        root.addWidget(self.header)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.s_ops = StatCard("операций выполнено", "activity")
        self.s_bytes = StatCard("данных разобрано", "database")
        self.s_batches = StatCard("пакетов в журнале", "layers")
        self.s_undone = StatCard("пакетов отменено", "rotate")
        for c in (self.s_ops, self.s_bytes, self.s_batches, self.s_undone):
            stats.addWidget(c, 1)
        root.addLayout(stats)

        mid = QHBoxLayout()
        mid.setSpacing(14)
        chart_card = Card()
        chart_card.body.addWidget(label("Активность за 14 дней", "h2"))
        self.chart = BarChart()
        chart_card.body.addWidget(self.chart, 1)
        mid.addWidget(chart_card, 3)

        top_card = Card()
        top_card.body.addWidget(label("Чаще всего срабатывали", "h2"))
        self.top_box = QVBoxLayout()
        self.top_box.setSpacing(12)
        top_card.body.addLayout(self.top_box)
        top_card.body.addStretch(1)
        mid.addWidget(top_card, 2)
        root.addLayout(mid)

        recent = Card()
        recent.body.addWidget(label("Последние действия", "h2"))
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(0)
        recent.body.addLayout(self.recent_box)
        root.addWidget(recent)
        root.addStretch(1)

        state.watch_changed.connect(self._sync_watch)
        state.config_changed.connect(self._sync_watch)
        state.journal_changed.connect(self.refresh)
        self._sync_watch()
        self.refresh()

    def _sync_watch(self, *_a) -> None:
        folders = len(self.state.watch_folders)
        if self.state.watching:
            sub = f"Слежение включено: {plural(folders, 'папка', 'папки', 'папок')} под присмотром"
            self.watch_btn.setText("Приостановить")
            self.watch_btn.setIcon(self._icon("pause"))
        else:
            sub = "Слежение на паузе: новые файлы не трогаю, пока не включишь"
            self.watch_btn.setText("Включить слежение")
            self.watch_btn.setIcon(self._icon("play"))
        self.header.subtitle.setText(sub)

    def _icon(self, name: str):
        from . import icons
        from .theme import C
        return icons.icon(name, C["text"], size=16)

    def refresh(self) -> None:
        j = self.state.journal
        s = j.stats()
        self.s_ops.set_value(number(s["ops"]))
        self.s_bytes.set_value(human_size(s["bytes"]))
        self.s_batches.set_value(number(s["batches"]))
        self.s_undone.set_value(number(s["undone"]))
        self.chart.set_data([(f"{d:%d.%m}", n) for d, n in j.daily_counts(14)])

        clear_layout(self.top_box)
        if s["top_rules"]:
            peak = max(n for _r, n in s["top_rules"])
            for rule, n in s["top_rules"]:
                head = QHBoxLayout()
                head.addWidget(label(rule, "h3"), 1)
                head.addWidget(label(number(n), "muted"))
                box = QVBoxLayout()
                box.setSpacing(5)
                box.addLayout(head)
                box.addWidget(ShareBar(n / peak))
                self.top_box.addLayout(box)
        else:
            self.top_box.addWidget(label("Правила ещё не срабатывали", "muted"))

        clear_layout(self.recent_box)
        rows = j.recent_ops(8)
        if not rows:
            self.recent_box.addWidget(EmptyState(
                "bolt", "Пока пусто",
                "Нажми «Разобрать сейчас» или включи слежение: действия появятся здесь"))
            return
        for i, r in enumerate(rows):
            if i:
                self.recent_box.addWidget(divider())
            self.recent_box.addWidget(self._row(r))

    def _row(self, r) -> QWidget:
        w = QWidget()
        w.setObjectName("Transparent")
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 10, 0, 10)
        row.setSpacing(12)
        from pathlib import Path
        name = Path(r["src"]).name
        dst = Path(r["dst"])
        where = (f"→ {dst.name}" if r["kind"] == "rename" else f"→ {tail(dst.parent)}")
        col = QVBoxLayout()
        col.setSpacing(1)
        title = label(name, "h3")
        sub = label(f"{VERBS_PAST.get(r['kind'], r['kind'])} {where}", "caption")
        if r["undone"]:
            title.setStyleSheet("color: #5C6578; text-decoration: line-through;")
        col.addWidget(title)
        col.addWidget(sub)
        row.addLayout(col, 1)
        row.addWidget(pill("отменено", "danger") if r["undone"] else pill(r["rule"], "accent"))
        when = label(ago(r["ts"]), "caption")
        when.setMinimumWidth(110)
        when.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(when)
        return w
