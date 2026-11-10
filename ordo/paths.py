from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional


def ordo_home() -> Path:
    """Папка с данными Ordo. Переопределяется переменной ORDO_HOME."""
    env = os.environ.get("ORDO_HOME")
    return Path(env).expanduser() if env else Path.home() / ".ordo"


def config_path() -> Path:
    return ordo_home() / "config.json"


def db_path() -> Path:
    return ordo_home() / "ordo.db"


def trash_dir() -> Path:
    return ordo_home() / "trash"


def _windows_downloads() -> Optional[Path]:
    """Настоящая папка «Загрузки» из Windows: пользователь мог перенести её на другой диск."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                        ("d", ctypes.c_ubyte * 8)]

        # FOLDERID_Downloads = {374DE290-123F-4565-9164-39C4925E467B}
        fid = GUID(0x374DE290, 0x123F, 0x4565, (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except (OSError, AttributeError, ValueError):
        return None


def downloads_dir() -> Path:
    """Папка загрузок пользователя (в Windows спрашиваем систему, иначе ~/Downloads)."""
    found = _windows_downloads()
    return found if found else Path.home() / "Downloads"


_DOWNLOADS_PREFIX = re.compile(r"^~[\\/]+Downloads(?=[\\/]|$)", re.IGNORECASE)


def expand(value: str) -> Path:
    """~ и переменные окружения (%USERPROFILE%, $HOME) -> Path.

    «~/Downloads» понимается как настоящая папка загрузок, даже если она перенесена.
    """
    text = str(value)
    if _DOWNLOADS_PREFIX.match(text):
        text = str(downloads_dir()) + text[len("~/Downloads"):]
    return Path(os.path.expandvars(os.path.expanduser(text)))
