"""Автозапуск вместе с Windows (ключ Run в реестре текущего пользователя, права админа не нужны)."""
from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Ordo"


def supported() -> bool:
    return sys.platform == "win32"


def command() -> str:
    """Команда запуска: свёрнутым в трей, без чёрного окна консоли."""
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):  # собранный .exe (PyInstaller)
        return f'"{exe}" --minimized'
    pythonw = exe.with_name("pythonw.exe")
    launcher = pythonw if pythonw.exists() else exe
    return f'"{launcher}" -m ordo gui --minimized'


def is_enabled() -> bool:
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(on: bool) -> None:
    if not supported():
        raise OSError("Автозапуск поддерживается только в Windows")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
