"""Свои виджеты: переключатель, карточки, график, кнопки и заголовок страницы."""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PyQt5.QtCore import QRectF, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolTip,
    QVBoxLayout, QWidget,
)

from . import icons
from .theme import C, set_prop


def label(text: str = "", role: Optional[str] = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    return lb


class ElidedLabel(QLabel):
    """Подпись, которая сама укорачивается «…», если не хватает места (длинные пути)."""

    def __init__(self, text: str = "", role: Optional[str] = None, mode=Qt.ElideMiddle):
        super().__init__()
        if role:
            self.setProperty("role", role)
        self._mode = mode
        self._full = ""
        self.setText(text)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def setText(self, text: str) -> None:
        self._full = text
        super().setText(text)
        self.setToolTip(text)

    def minimumSizeHint(self) -> QSize:
        return QSize(48, super().minimumSizeHint().height())

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setPen(self.palette().windowText().color())
        p.setFont(self.font())
        shown = self.fontMetrics().elidedText(self._full, self._mode, self.width())
        p.drawText(self.rect(), Qt.AlignVCenter | Qt.AlignLeft, shown)


def pill(text: str, variant: str = "muted") -> QLabel:
    lb = QLabel(text)
    lb.setProperty("pill", variant)
    lb.setAlignment(Qt.AlignCenter)
    lb.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return lb


def set_pill(lb: QLabel, text: str, variant: str) -> None:
    lb.setText(text)
    set_prop(lb, "pill", variant)


def button(text: str = "", variant: str = "default", icon: Optional[str] = None,
           on_click: Optional[Callable] = None, tooltip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setProperty("variant", variant)
    b.setCursor(Qt.PointingHandCursor)
    if icon:
        color = {"primary": "#FFFFFF", "danger": C["danger"], "icon-danger": C["danger"]}.get(
            variant, C["muted"] if variant in ("ghost", "icon") else C["text"])
        b.setIcon(icons.icon(icon, color, size=16 if text else 18))
        b.setIconSize(QSize(16, 16) if text else QSize(18, 18))
    if tooltip:
        b.setToolTip(tooltip)
    if on_click:
        b.clicked.connect(lambda _=False: on_click())
    return b


def divider() -> QFrame:
    d = QFrame()
    d.setObjectName("Divider")
    d.setFrameShape(QFrame.NoFrame)
    return d


class Card(QFrame):
    def __init__(self, parent: Optional[QWidget] = None, padding: int = 18, spacing: int = 12):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(spacing)


class Toggle(QAbstractButton):
    """Переключатель в стиле iOS с плавным ходом ползунка."""

    def __init__(self, checked: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 24)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._animate)

    def _on_anim(self, v) -> None:
        self._pos = float(v)
        self.update()

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_checked_silent(self, on: bool) -> None:
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(40, 24)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off, on = QColor(C["scroll_hover"]), QColor(C["accent"])
        t = self._pos
        track = QColor(int(off.red() + (on.red() - off.red()) * t),
                       int(off.green() + (on.green() - off.green()) * t),
                       int(off.blue() + (on.blue() - off.blue()) * t))
        if not self.isEnabled():
            p.setOpacity(0.45)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, 40, 24), 12, 12)
        x = 3 + 16 * t
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x, 3, 18, 18))


class StatCard(QFrame):
    """Крупная цифра с иконкой: «операций», «разобрано данных» и т.п."""

    def __init__(self, title: str, icon_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Card")
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 16, 18, 16)
        row.setSpacing(14)
        tile = QFrame()
        tile.setObjectName("IconTile")
        tile.setFixedSize(44, 44)
        tl = QHBoxLayout(tile)
        tl.setContentsMargins(0, 0, 0, 0)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, C["accent_text"], 22))
        ic.setAlignment(Qt.AlignCenter)
        tl.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.value = label("0", "value")
        self.title = label(title, "caption")
        col.addWidget(self.value)
        col.addWidget(self.title)
        row.addWidget(tile, 0, Qt.AlignVCenter)
        row.addLayout(col, 1)

    def set_value(self, text: str) -> None:
        self.value.setText(text)


class ShareBar(QWidget):
    """Тонкая полоса «доля от максимума» для рейтинга правил."""

    def __init__(self, fraction: float = 0.0, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._f = max(0.0, min(1.0, fraction))
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["surface3"]))
        p.drawRoundedRect(QRectF(self.rect()), 3, 3)
        if self._f > 0:
            p.setBrush(QColor(C["accent"]))
            p.drawRoundedRect(QRectF(0, 0, max(6.0, self.width() * self._f), self.height()), 3, 3)


class BarChart(QWidget):
    """Столбики активности по дням. Наведи мышь, чтобы увидеть число."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._data: List[Tuple[str, int]] = []
        self._hover = -1
        self.setMouseTracking(True)
        self.setMinimumHeight(150)

    def set_data(self, data: List[Tuple[str, int]]) -> None:
        self._data = data
        self.update()

    def _geometry(self):
        n = len(self._data)
        top, bottom, gap = 8.0, 22.0, 6.0
        plot_h = self.height() - top - bottom
        bar_w = (self.width() - gap * (n - 1)) / n if n else 0
        return n, top, plot_h, bar_w, gap

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n, top, plot_h, bar_w, gap = self._geometry()
        if not n or max(v for _, v in self._data) == 0:
            p.setPen(QColor(C["muted"]))
            p.drawText(self.rect(), Qt.AlignCenter, "Пока нет данных: разбери папку, и тут появятся столбики")
            return
        peak = max(v for _, v in self._data)
        small = QFont(self.font())
        small.setPixelSize(10)
        p.setFont(small)
        for i, (name, value) in enumerate(self._data):
            x = i * (bar_w + gap)
            h = max(4.0, plot_h * value / peak) if value else 3.0
            rect = QRectF(x, top + plot_h - h, bar_w, h)
            if value == 0:
                color = QColor(C["surface3"])
            else:
                color = QColor(C["accent_hover"] if i == self._hover else C["accent"])
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(rect, 4, 4)
            if i % 2 == (n - 1) % 2:
                p.setPen(QColor(C["muted"]))
                p.drawText(QRectF(x - 6, self.height() - 18, bar_w + 12, 16), Qt.AlignCenter, name)

    def mouseMoveEvent(self, e) -> None:
        n, _t, _h, bar_w, gap = self._geometry()
        if not n:
            return
        i = int(e.x() / (bar_w + gap))
        i = i if 0 <= i < n else -1
        if i != self._hover:
            self._hover = i
            self.update()
        if i >= 0:
            name, value = self._data[i]
            QToolTip.showText(e.globalPos(), f"{name}: {value}", self)

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()


class PageHeader(QWidget):
    """Заголовок страницы: название, подпись и кнопки справа."""

    def __init__(self, title: str, subtitle: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Transparent")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(title, "title"))
        self.subtitle = label(subtitle, "muted")
        col.addWidget(self.subtitle)
        row.addLayout(col, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        row.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget, 0, Qt.AlignVCenter)


class EmptyState(QWidget):
    """Пустое место с иконкой и подсказкой, что делать дальше."""

    def __init__(self, icon_name: str, title: str, hint: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Transparent")
        col = QVBoxLayout(self)
        col.setAlignment(Qt.AlignCenter)
        col.setSpacing(8)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, C["muted2"], 40, 1.6))
        ic.setAlignment(Qt.AlignCenter)
        col.addWidget(ic)
        t = label(title, "h2")
        t.setAlignment(Qt.AlignCenter)
        col.addWidget(t)
        h = label(hint, "muted", wrap=True)
        h.setAlignment(Qt.AlignCenter)
        col.addWidget(h)
