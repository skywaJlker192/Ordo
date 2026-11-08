"""Точка входа для сборки .exe (PyInstaller не любит запускать пакет напрямую)."""
import sys

from ordo.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
