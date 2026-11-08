"""Рисует packaging/ordo.ico из логотипа Ordo (векторного, из ordo/gui/icons.py)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtGui import QGuiApplication  # noqa: E402

from ordo.gui import icons  # noqa: E402

app = QGuiApplication([])
out = Path(__file__).with_name("ordo.ico")
big = icons.logo_pixmap(256).toImage()
big.save(str(out.with_suffix(".png")))
from PIL import Image  # noqa: E402

img = Image.open(out.with_suffix(".png")).convert("RGBA")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
out.with_suffix(".png").unlink()
print("saved", out)
