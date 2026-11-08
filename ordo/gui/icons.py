"""Векторные иконки (стиль Feather) из SVG-строк: без внешних файлов, чёткие на любом масштабе."""
from __future__ import annotations

from typing import Dict, Optional

from PyQt5.QtCore import QByteArray, QPointF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

_BODIES: Dict[str, str] = {
    "home": '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    "rules": ('<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>'
              '<line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>'
              '<line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>'),
    "history": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    "settings": ('<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>'
                 '<line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>'
                 '<line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>'
                 '<line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/>'
                 '<line x1="17" y1="16" x2="23" y2="16"/>'),
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "pause": '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "edit": '<path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>',
    "trash": ('<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>'
              '<path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>'),
    "up": '<polyline points="18 15 12 9 6 15"/>',
    "down": '<polyline points="6 9 12 15 18 9"/>',
    "right": '<polyline points="9 18 15 12 9 6"/>',
    "undo": '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
    "bolt": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "eye": '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    "export": ('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/>'
               '<line x1="12" y1="15" x2="12" y2="3"/>'),
    "import": ('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/>'
               '<line x1="12" y1="3" x2="12" y2="15"/>'),
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "x": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "copy": ('<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>'
             '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'),
    "layers": ('<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/>'
               '<polyline points="2 12 12 17 22 12"/>'),
    "activity": '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    "database": ('<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>'
                 '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'),
    "rotate": '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
    "scenario": '<circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "alert": ('<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>'
              '<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'),
    "external": ('<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
                 '<polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>'),
}

LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#8794FF"/><stop offset="1" stop-color="#5B3DF5"/>'
    '</linearGradient></defs>'
    '<rect width="64" height="64" rx="16" fill="url(#g)"/>'
    '<rect x="14" y="17" width="36" height="8" rx="4" fill="#fff"/>'
    '<rect x="14" y="28" width="26" height="8" rx="4" fill="#fff" fill-opacity=".85"/>'
    '<rect x="14" y="39" width="16" height="8" rx="4" fill="#fff" fill-opacity=".7"/>'
    '</svg>'
)

_DPR = 2.0
_cache: Dict[tuple, QPixmap] = {}


def _render(svg: str, px: int) -> QPixmap:
    pm = QPixmap(int(px * _DPR), int(px * _DPR))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter)
    painter.end()
    pm.setDevicePixelRatio(_DPR)
    return pm


def pixmap(name: str, color: str = "#8A93A6", size: int = 18, stroke: float = 2.0) -> QPixmap:
    key = (name, color, size, stroke)
    if key not in _cache:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
            f'stroke-linejoin="round">{_BODIES[name]}</svg>'
        )
        _cache[key] = _render(svg, size)
    return _cache[key]


def icon(name: str, color: str = "#8A93A6", on_color: Optional[str] = None,
         size: int = 18, stroke: float = 2.0) -> QIcon:
    """on_color: цвет для нажатого/выбранного состояния (для кнопок навигации)."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size, stroke), QIcon.Normal, QIcon.Off)
    if on_color:
        on = pixmap(name, on_color, size, stroke)
        ic.addPixmap(on, QIcon.Normal, QIcon.On)
        ic.addPixmap(on, QIcon.Active, QIcon.On)
    return ic


def save_png(name: str, color: str, size: int, path: str, stroke: float = 2.4) -> None:
    """Для QSS (стрелки в списках): там иконку можно задать только файлом."""
    pixmap(name, color, size, stroke).save(path, "PNG")


def logo_pixmap(size: int = 64, dot: Optional[str] = None) -> QPixmap:
    """Логотип; dot: цвет индикатора состояния в правом нижнем углу (для трея)."""
    pm = _render(LOGO_SVG, size)
    if dot:
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r = size * 0.30
        c = QPointF(size - r * 0.95, size - r * 0.95)
        p.setPen(QColor("#0E1014"))
        p.setBrush(QColor(dot))
        p.drawEllipse(c, r * 0.85, r * 0.85)
        p.end()
    return pm


def app_icon(dot: Optional[str] = None) -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(s, dot))
    return ic
