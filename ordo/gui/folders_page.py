"""Папки под присмотром: добавить, убрать, настроить, разобрать вручную."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable, Optional

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QSpinBox, QVBoxLayout, QWidget

from ..paths import expand
from . import icons
from .dashboard import clear_layout
from .rules_page import confirm, warn
from .state import AppState
from .theme import C
from .widgets import Card, ElidedLabel, EmptyState, PageHeader, button, label, pill


class FoldersPage(QWidget):
    def __init__(self, state: AppState, run_now: Callable[[Optional[Path]], None],
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.state = state
        self._run_now = run_now
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        header = PageHeader("Папки", "За этими папками следит Ordo и к ним применяет правила")
        header.add_action(button("Добавить папку", "primary", "plus", self._add))
        root.addWidget(header)
        self.box = QVBoxLayout()
        self.box.setSpacing(10)
        root.addLayout(self.box)

        hint = Card(padding=14, spacing=4)
        hint.body.addWidget(label("Как это работает", "h3"))
        hint.body.addWidget(label(
            "Ordo разбирает файлы, лежащие прямо в папке (вложенные папки не трогает). "
            "Недокачанные файлы (.crdownload, .part) он пропускает и ждёт, пока файл перестанет меняться: "
            "это время можно настроить у каждой папки.", "muted", wrap=True))
        root.addWidget(hint)
        root.addStretch(1)
        state.config_changed.connect(self.rebuild)
        self.rebuild()

    def rebuild(self) -> None:
        clear_layout(self.box)
        folders = self.state.watch_folders
        if not folders:
            self.box.addWidget(EmptyState("folder", "Папок пока нет",
                                          "Добавь «Загрузки» или любую другую папку, которую хочешь держать в порядке"))
            return
        for i, spec in enumerate(folders):
            self.box.addWidget(self._card(i, spec))

    def _card(self, i: int, spec: dict) -> QFrame:
        path = expand(spec["folder"])
        exists = path.is_dir()
        card = Card(padding=14)
        row = QHBoxLayout()
        row.setSpacing(14)
        card.body.addLayout(row)

        tile = QFrame()
        tile.setObjectName("IconTile")
        tile.setFixedSize(44, 44)
        tl = QHBoxLayout(tile)
        tl.setContentsMargins(0, 0, 0, 0)
        ic = label()
        ic.setPixmap(icons.pixmap("folder" if exists else "alert", C["accent_text"] if exists else C["warning"], 22))
        ic.setAlignment(Qt.AlignCenter)
        tl.addWidget(ic)
        row.addWidget(tile)

        col = QVBoxLayout()
        col.setSpacing(3)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(ElidedLabel(str(spec["folder"]), "h2"), 1)
        head.addWidget(pill("найдена" if exists else "не найдена", "success" if exists else "danger"))
        col.addLayout(head)
        wait = QHBoxLayout()
        wait.setSpacing(8)
        wait.addWidget(label("Ждать после последнего изменения файла", "caption"))
        spin = QSpinBox()
        spin.setRange(1, 120)
        spin.setSuffix(" сек")
        spin.setValue(int(float(spec.get("settle_seconds", 3))))
        spin.setFixedWidth(96)
        spin.editingFinished.connect(lambda s=spin, k=i: self._set_wait(k, s.value()))
        wait.addWidget(spin)
        wait.addStretch(1)
        col.addLayout(wait)
        row.addLayout(col, 1)

        row.addWidget(button("Разобрать", "default", "bolt", lambda p=path: self._run_now(p)))
        row.addWidget(button("", "icon", "external", lambda p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))),
                             "Открыть в проводнике"))
        row.addWidget(button("", "icon-danger", "trash", lambda k=i: self._remove(k), "Убрать из списка"))
        return card

    def _save(self, folders) -> None:
        err = self.state.set_watch_folders(folders)
        if err:
            warn(self, err)
            self.rebuild()

    def _set_wait(self, i: int, seconds: int) -> None:
        folders = copy.deepcopy(self.state.watch_folders)
        if i < len(folders) and int(float(folders[i].get("settle_seconds", 3))) != seconds:
            folders[i]["settle_seconds"] = seconds
            self._save(folders)

    def _add(self) -> None:
        start = str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Какую папку держать в порядке", start)
        if not chosen:
            return
        folders = copy.deepcopy(self.state.watch_folders)
        if any(expand(f["folder"]) == Path(chosen) for f in folders):
            warn(self, "Эта папка уже в списке.")
            return
        folders.append({"folder": chosen, "settle_seconds": 3})
        self._save(folders)

    def _remove(self, i: int) -> None:
        name = self.state.watch_folders[i]["folder"]
        if confirm(self, "Убрать папку", f"Больше не следить за «{name}»?\nСами файлы останутся на месте.",
                   "Убрать", danger=True):
            folders = copy.deepcopy(self.state.watch_folders)
            del folders[i]
            self._save(folders)
