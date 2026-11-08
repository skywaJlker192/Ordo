"""Радиальное меню: круг у курсора, плавно раскрывается, сектора подсвечиваются с инерцией."""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from PyQt5.QtCore import QEasingCurve, QPoint, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt5.QtGui import (
    QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen,
    QRadialGradient,
)
from PyQt5.QtWidgets import QWidget

from ..radial import sector_at, sector_center_angle
from . import icons
from .theme import C

INNER = 66.0
OUTER = 152.0
GROW = 10.0          # насколько сектор под курсором выезжает наружу
PAD = 30.0           # запас под тень и выезд
GAP_DEG = 2.4        # просвет между секторами
ICON = 26


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))


class RadialMenu(QWidget):
    chosen = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setMouseTracking(True)
        side = int(2 * (OUTER + PAD))
        self.setFixedSize(side, side)
        self._items: List[Dict[str, str]] = []
        self._hover: Optional[int] = None
        self._level: List[float] = []      # плавная «степень наведения» каждого сектора, 0..1
        self._picked: Optional[int] = None
        self._open = 0.0                   # 0..1, раскрытие
        self._closing = False
        self._label_alpha = 0.0
        self._label_text = ""

        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_open)
        self._anim.finished.connect(self._on_anim_done)

        self._frame = QTimer(self)
        self._frame.setInterval(16)
        self._frame.timeout.connect(self._step)

        self._watch = QTimer(self)  # закрыть, если курсор ушёл далеко (когда окно не получило фокус)
        self._watch.setInterval(120)
        self._watch.timeout.connect(self._check_far)

    # ---------- данные ----------

    def set_items(self, items: List[Dict[str, str]]) -> None:
        self._items = list(items)
        self._level = [0.0] * len(self._items)

    @property
    def center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    # ---------- показ и закрытие ----------

    def popup(self, at: Optional[QPoint] = None) -> None:
        if not self._items:
            return
        at = at or QCursor.pos()
        screen = QGuiApplication.screenAt(at) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        half = self.width() // 2
        cx = int(_clamp(at.x(), area.left() + half, area.right() - half))
        cy = int(_clamp(at.y(), area.top() + half, area.bottom() - half))
        self.move(cx - half, cy - half)
        self._level = [0.0] * len(self._items)
        self._hover, self._picked, self._closing = None, None, False
        self._label_alpha, self._label_text = 0.0, ""
        self._open = 0.0
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._run_anim(0.0, 1.0, 330, QEasingCurve.OutBack)
        self._frame.start()
        self._watch.start()
        self._sync_hover(self.mapFromGlobal(QCursor.pos()))

    def dismiss(self) -> None:
        if not self.isVisible() or self._closing:
            return
        self._closing = True
        self._run_anim(self._open, 0.0, 170, QEasingCurve.InCubic)

    def _run_anim(self, a: float, b: float, ms: int, curve) -> None:
        self._anim.stop()
        self._anim.setStartValue(float(a))
        self._anim.setEndValue(float(b))
        self._anim.setDuration(ms)
        easing = QEasingCurve(curve)
        if curve == QEasingCurve.OutBack:
            easing.setOvershoot(1.25)
        self._anim.setEasingCurve(easing)
        self._anim.start()

    def _on_open(self, v) -> None:
        self._open = float(v)
        self.update()

    def _on_anim_done(self) -> None:
        if self._closing:
            self._frame.stop()
            self._watch.stop()
            self.hide()
            self._closing = False

    def _check_far(self) -> None:
        d = QCursor.pos() - (self.pos() + QPoint(self.width() // 2, self.height() // 2))
        if math.hypot(d.x(), d.y()) > OUTER + 110:
            self.dismiss()

    # ---------- плавность наведения ----------

    def _step(self) -> None:
        moving = False
        for i in range(len(self._level)):
            target = 1.0 if i == self._hover and self._picked is None else 0.0
            diff = target - self._level[i]
            if abs(diff) > 0.004:
                self._level[i] += diff * 0.26
                moving = True
            else:
                self._level[i] = target
        want = 1.0 if self._hover is not None else 0.0
        if abs(want - self._label_alpha) > 0.004:
            self._label_alpha += (want - self._label_alpha) * 0.3
            moving = True
        if moving or self._anim.state() == QVariantAnimation.Running:
            self.update()

    def _sync_hover(self, pos: QPoint) -> None:
        d = QPointF(pos) - self.center
        idx = sector_at(d.x(), d.y(), len(self._items), INNER - 4, OUTER + GROW)
        if idx != self._hover:
            self._hover = idx
            if idx is not None:
                self._label_text = self._items[idx]["label"]

    # ---------- ввод ----------

    def mouseMoveEvent(self, e) -> None:
        if not self._closing:
            self._sync_hover(e.pos())

    def mousePressEvent(self, e) -> None:
        if self._closing:
            return
        self._sync_hover(e.pos())  # решает точка клика, а не прошлое положение курсора
        if e.button() == Qt.LeftButton and self._hover is not None:
            self._choose(self._hover)
        else:
            self.dismiss()  # клик мимо сектора или правой кнопкой: закрыть

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.dismiss()
        elif Qt.Key_1 <= e.key() <= Qt.Key_8 and e.key() - Qt.Key_1 < len(self._items) and not self._closing:
            self._choose(e.key() - Qt.Key_1)

    def event(self, e) -> bool:
        if e.type() == e.WindowDeactivate and self.isVisible():
            self.dismiss()
        return super().event(e)

    def leaveEvent(self, _e) -> None:
        self._hover = None

    def _choose(self, index: int) -> None:
        self._picked = index
        self._label_text = self._items[index]["label"]
        item_id = self._items[index]["id"]
        self.dismiss()
        self.chosen.emit(item_id)

    # ---------- рисование ----------

    def _sector_path(self, i: int, n: int, r_in: float, r_out: float) -> QPainterPath:
        half = 180.0 / n
        c = sector_center_angle(i, n)
        start = 90.0 - (c + half - GAP_DEG)      # у Qt 0° справа и против часовой
        span = 2 * (half - GAP_DEG)
        outer = QRectF(-r_out, -r_out, 2 * r_out, 2 * r_out)
        inner = QRectF(-r_in, -r_in, 2 * r_in, 2 * r_in)
        p = QPainterPath()
        p.arcMoveTo(outer, start)
        p.arcTo(outer, start, span)
        p.arcTo(inner, start + span, -span)
        p.closeSubpath()
        return p

    def paintEvent(self, _e) -> None:
        n = len(self._items)
        if not n:
            return
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        p.translate(self.center)
        o = self._open
        fade = _clamp(o * 1.6)

        # мягкая тень под кольцом
        shadow = QRadialGradient(QPointF(0, 0), OUTER + PAD - 2)
        edge = (OUTER + 6) / (OUTER + PAD - 2)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 0))
        shadow.setColorAt(INNER / (OUTER + PAD - 2), QColor(0, 0, 0, int(70 * fade)))
        shadow.setColorAt(edge, QColor(0, 0, 0, int(95 * fade)))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(shadow)
        p.drawEllipse(QPointF(0, 0), OUTER + PAD - 2, OUTER + PAD - 2)

        base = QColor(C["surface2"])
        base.setAlpha(238)
        accent = QColor(C["accent"])
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)

        for i in range(n):
            local = _clamp(o * 1.5 - i * (0.5 / max(n, 1)))   # сектора выезжают по очереди
            ease = QEasingCurve(QEasingCurve.OutCubic).valueForProgress(local)
            if ease <= 0.001:
                continue
            lvl = self._level[i] if i < len(self._level) else 0.0
            picked = self._picked == i
            grow = GROW * lvl + (14 * (1 - o) if picked and self._closing else 0)
            scale = (0.6 + 0.4 * ease) * (1.0 + (0.12 * (1 - o) if picked and self._closing else 0.0))

            p.save()
            p.rotate((1 - ease) * -22)
            p.scale(scale, scale)
            p.setOpacity(ease if not (self._closing and not picked) else ease)
            path = self._sector_path(i, n, INNER, OUTER + grow)
            fill = _mix(base, accent, 0.0 + 0.92 * lvl)
            p.setPen(QPen(_mix(QColor(C["border2"]), QColor(C["accent_hover"]), lvl), 1.2))
            p.setBrush(fill)
            p.drawPath(path)

            ang = math.radians(sector_center_angle(i, n))
            mid = (INNER + OUTER + grow) / 2 + 2
            cx, cy = math.sin(ang) * mid, -math.cos(ang) * mid
            k = 1.0 + 0.16 * lvl
            name = self._items[i].get("icon", "bolt")
            p.save()
            p.translate(cx, cy - 8)
            p.scale(k, k)
            op = p.opacity()
            p.setOpacity(op * (1 - lvl))     # два готовых цвета плавно перетекают друг в друга
            p.drawPixmap(QPointF(-ICON / 2, -ICON / 2), icons.pixmap(name, C["accent_text"], ICON, 2.0))
            p.setOpacity(op * lvl)
            p.drawPixmap(QPointF(-ICON / 2, -ICON / 2), icons.pixmap(name, "#FFFFFF", ICON, 2.0))
            p.restore()
            color = _mix(QColor(C["accent_text"]), QColor("#FFFFFF"), lvl)
            p.setFont(font)
            p.setPen(color)
            label = QFontMetrics(font).elidedText(self._items[i]["label"], Qt.ElideRight, 84)
            p.drawText(QRectF(cx - 44, cy + 9 + 3 * lvl, 88, 16), Qt.AlignHCenter | Qt.AlignTop, label)
            p.restore()

        # центр: подпись наведённого пункта
        p.setOpacity(_clamp(o * 1.4))
        disc = QColor(C["bg"])
        disc.setAlpha(240)
        p.setPen(QPen(QColor(C["border2"]), 1.2))
        p.setBrush(disc)
        r = (INNER - 8) * (0.7 + 0.3 * _clamp(o))
        p.drawEllipse(QPointF(0, 0), r, r)
        big = QFont(self.font())
        big.setPixelSize(13)
        big.setBold(True)
        p.setFont(big)
        shown = QColor(C["text"])
        hint = QColor(C["muted2"])
        p.setPen(_mix(hint, shown, self._label_alpha))
        text = self._label_text if self._label_alpha > 0.05 else "Ordo"
        p.drawText(QRectF(-r + 6, -r, 2 * r - 12, 2 * r), Qt.AlignCenter | Qt.TextWordWrap, text)
