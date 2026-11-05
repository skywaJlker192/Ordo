"""Тёмная тема Ordo: палитра и таблица стилей. Один акцентный цвет, остальное нейтральное."""
from __future__ import annotations

import tempfile
from pathlib import Path
from string import Template

from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtWidgets import QApplication, QWidget

from . import icons

C = {
    "bg": "#0E1014",
    "sidebar": "#12151B",
    "surface": "#171B22",
    "surface2": "#1D222B",
    "surface3": "#252B36",
    "border": "#262C37",
    "border2": "#343C4B",
    "text": "#E7EAF0",
    "muted": "#8A93A6",
    "muted2": "#5C6578",
    "accent": "#5B6CFF",
    "accent_hover": "#7482FF",
    "accent_press": "#4A59E8",
    "accent_text": "#9AA6FF",
    "accent_soft": "rgba(91, 108, 255, 36)",
    "success": "#3DD68C",
    "success_soft": "rgba(61, 214, 140, 30)",
    "warning": "#F5B94A",
    "danger": "#F26D6D",
    "danger_soft": "rgba(242, 109, 109, 30)",
    "scroll": "#2B3240",
    "scroll_hover": "#3A4356",
}

_QSS = Template("""
* {
    font-family: "Segoe UI", "Inter", "Roboto", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: $text;
    outline: 0;
}
QMainWindow, QDialog, QMessageBox { background: $bg; }
QWidget#Page, QWidget#Transparent { background: transparent; }
QToolTip {
    background: $surface3; color: $text; border: 1px solid $border2;
    padding: 6px 8px; border-radius: 6px;
}

/* ---------- каркас ---------- */
QWidget#Sidebar { background: $sidebar; border-right: 1px solid $border; }
QFrame#Card { background: $surface; border: 1px solid $border; border-radius: 14px; }
QFrame#CardInner { background: $surface2; border: 1px solid $border; border-radius: 10px; }
QFrame#Divider { background: $border; max-height: 1px; min-height: 1px; border: none; }
QFrame#IconTile { background: $accent_soft; border-radius: 10px; }
QFrame#BrandMark { background: transparent; }

/* ---------- текст ---------- */
QLabel { background: transparent; }
QLabel[role="title"] { font-size: 24px; font-weight: 700; }
QLabel[role="h2"] { font-size: 15px; font-weight: 600; }
QLabel[role="h3"] { font-size: 13px; font-weight: 600; }
QLabel[role="muted"] { color: $muted; }
QLabel[role="caption"] { color: $muted; font-size: 12px; }
QLabel[role="value"] { font-size: 28px; font-weight: 700; }
QLabel[role="brand"] { font-size: 18px; font-weight: 700; }
QLabel[role="mono"] { font-family: "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace; font-size: 12px; color: $muted; }
QLabel[pill="success"] {
    background: $success_soft; color: $success; border-radius: 10px;
    padding: 3px 10px; font-size: 12px; font-weight: 600;
}
QLabel[pill="muted"] {
    background: $surface2; color: $muted; border-radius: 10px;
    padding: 3px 10px; font-size: 12px; font-weight: 600;
}
QLabel[pill="accent"] {
    background: $accent_soft; color: $accent_text; border-radius: 10px;
    padding: 3px 10px; font-size: 12px; font-weight: 600;
}
QLabel[pill="danger"] {
    background: $danger_soft; color: $danger; border-radius: 10px;
    padding: 3px 10px; font-size: 12px; font-weight: 600;
}
QLabel[chip="true"] {
    background: $surface2; color: $accent_text; border: 1px solid $border;
    border-radius: 7px; padding: 2px 8px; font-size: 12px;
}

/* ---------- кнопки ---------- */
QPushButton {
    background: $surface2; border: 1px solid $border; border-radius: 9px;
    padding: 8px 14px; color: $text; font-weight: 500;
}
QPushButton:hover { background: $surface3; border-color: $border2; }
QPushButton:pressed { background: $border; }
QPushButton:disabled { color: $muted2; background: $surface; border-color: $border; }
QPushButton[variant="primary"] {
    background: $accent; border: 1px solid $accent; color: #FFFFFF; font-weight: 600;
}
QPushButton[variant="primary"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton[variant="primary"]:pressed { background: $accent_press; border-color: $accent_press; }
QPushButton[variant="primary"]:disabled { background: $surface2; border-color: $border; color: $muted2; }
QPushButton[variant="ghost"] { background: transparent; border: 1px solid transparent; color: $muted; }
QPushButton[variant="ghost"]:hover { background: $surface2; color: $text; }
QPushButton[variant="danger"] { background: transparent; color: $danger; }
QPushButton[variant="danger"]:hover { background: $danger_soft; border-color: $danger; }
QPushButton[variant="icon"] {
    background: transparent; border: 1px solid transparent; padding: 6px; border-radius: 8px;
}
QPushButton[variant="icon"]:hover { background: $surface3; }
QPushButton[variant="icon-danger"] {
    background: transparent; border: 1px solid transparent; padding: 6px; border-radius: 8px;
}
QPushButton[variant="icon-danger"]:hover { background: $danger_soft; }
QPushButton[nav="true"] {
    text-align: left; padding: 10px 14px; border-radius: 10px; background: transparent;
    border: none; color: $muted; font-weight: 500;
}
QPushButton[nav="true"]:hover { background: $surface2; color: $text; }
QPushButton[nav="true"]:checked { background: $accent_soft; color: $accent_text; font-weight: 600; }

/* ---------- поля ввода ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {
    background: $surface2; border: 1px solid $border; border-radius: 9px;
    padding: 8px 10px; selection-background-color: $accent; selection-color: #FFFFFF;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus { border: 1px solid $accent; }
QLineEdit:disabled, QComboBox:disabled { color: $muted2; }
QLineEdit[invalid="true"] { border: 1px solid $danger; }
QComboBox {
    background: $surface2; border: 1px solid $border; border-radius: 9px;
    padding: 7px 30px 7px 10px; min-height: 18px;
}
QComboBox:hover { border-color: $border2; }
QComboBox::drop-down { border: none; width: 28px; subcontrol-origin: padding; subcontrol-position: center right; }
QComboBox::down-arrow { image: url($chev_down); width: 12px; height: 12px; }
QComboBox QAbstractItemView {
    background: $surface; border: 1px solid $border2; padding: 4px;
    selection-background-color: $accent_soft; selection-color: $accent_text;
}
QSpinBox { padding-right: 26px; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; }
QSpinBox::up-arrow { image: url($chev_up); width: 9px; height: 9px; }
QSpinBox::down-arrow { image: url($chev_down); width: 9px; height: 9px; }
QCheckBox { spacing: 9px; background: transparent; }
QCheckBox::indicator {
    width: 18px; height: 18px; border-radius: 5px; border: 1px solid $border2; background: $surface2;
}
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url($check); }

/* ---------- списки и таблицы ---------- */
QTreeWidget, QTreeView, QListWidget, QTableWidget {
    background: transparent; border: none; alternate-background-color: transparent;
}
QTreeWidget::item { padding: 7px 4px; border-radius: 8px; }
QTreeWidget::item:hover { background: $surface2; }
QTreeWidget::item:selected { background: $accent_soft; color: $text; }
QTreeView::branch:closed:has-children { image: url($chev_right); }
QTreeView::branch:open:has-children { image: url($chev_down); }
QTreeView::branch { background: transparent; }
QTreeView::branch:selected,
QTreeView::branch:selected:has-children,
QTreeView::branch:open:has-children:selected,
QTreeView::branch:closed:has-children:selected { background: $accent_soft; }
QHeaderView::section {
    background: transparent; border: none; border-bottom: 1px solid $border;
    color: $muted; padding: 8px 6px; font-size: 12px; font-weight: 600;
}
QAbstractScrollArea { background: transparent; border: none; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: $scroll_hover; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $scroll; border-radius: 4px; min-width: 36px; }
QScrollBar::handle:horizontal:hover { background: $scroll_hover; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---------- меню ---------- */
QMenu { background: $surface; border: 1px solid $border2; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 8px 16px 8px 12px; border-radius: 6px; }
QMenu::item:selected { background: $accent_soft; color: $accent_text; }
QMenu::item:disabled { color: $muted2; }
QMenu::separator { height: 1px; background: $border; margin: 6px 4px; }
""")


def install_assets() -> dict:
    """Стрелки и галочка для QSS нужны файлами: кладём во временную папку."""
    folder = Path(tempfile.gettempdir()) / "ordo-ui-assets"
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for key, name, color in (
        ("chev_down", "down", C["muted"]),
        ("chev_up", "up", C["muted"]),
        ("chev_right", "right", C["muted"]),
        ("check", "check", "#FFFFFF"),
    ):
        path = folder / f"{key}.png"
        icons.save_png(name, color, 14 if key != "check" else 12, str(path))
        out[key] = path.as_posix()
    return out


def stylesheet() -> str:
    return _QSS.substitute({**C, **install_assets()})


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")  # единая база на всех ОС, дальше красим сами
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(C["bg"]))
    pal.setColor(QPalette.WindowText, QColor(C["text"]))
    pal.setColor(QPalette.Base, QColor(C["surface"]))
    pal.setColor(QPalette.Text, QColor(C["text"]))
    pal.setColor(QPalette.Button, QColor(C["surface2"]))
    pal.setColor(QPalette.ButtonText, QColor(C["text"]))
    pal.setColor(QPalette.Highlight, QColor(C["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ToolTipBase, QColor(C["surface3"]))
    pal.setColor(QPalette.ToolTipText, QColor(C["text"]))
    app.setPalette(pal)
    f = QFont()
    f.setPixelSize(13)
    app.setFont(f)
    app.setStyleSheet(stylesheet())


def set_prop(widget: QWidget, name: str, value) -> None:
    """Сменить динамическое свойство и перерисовать стиль (нужно для variant/pill)."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
