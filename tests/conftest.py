import sys
import traceback


def _hook(exc_type, exc, tb):
    # PyQt5 роняет процесс при необработанной ошибке в слоте: сначала покажем полный стек
    traceback.print_exception(exc_type, exc, tb)


sys.excepthook = _hook
