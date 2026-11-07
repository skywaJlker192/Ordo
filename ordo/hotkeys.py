"""Глобальные горячие клавиши: разбор «Ctrl+Alt+L» и слушатель для Windows (RegisterHotKey)."""
from __future__ import annotations

import re
import sys
import threading
from typing import Callable, Dict, List, Optional, Tuple

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x0008, 0x4000
WM_HOTKEY, WM_QUIT, WM_USER, PM_NOREMOVE = 0x0312, 0x0012, 0x0400, 0x0000

_MODS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT,
    "win": MOD_WIN, "meta": MOD_WIN, "super": MOD_WIN,
}
_MOD_ORDER = [("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN)]

# имя клавиши (в нижнем регистре) -> (красивое имя, виртуальный код Windows)
_NAMED = {
    "space": ("Space", 0x20), "enter": ("Enter", 0x0D), "return": ("Enter", 0x0D),
    "tab": ("Tab", 0x09), "esc": ("Esc", 0x1B), "escape": ("Esc", 0x1B),
    "backspace": ("Backspace", 0x08), "delete": ("Delete", 0x2E), "del": ("Delete", 0x2E),
    "insert": ("Insert", 0x2D), "ins": ("Insert", 0x2D), "home": ("Home", 0x24), "end": ("End", 0x23),
    "pageup": ("PageUp", 0x21), "pgup": ("PageUp", 0x21),
    "pagedown": ("PageDown", 0x22), "pgdown": ("PageDown", 0x22),
    "up": ("Up", 0x26), "down": ("Down", 0x28), "left": ("Left", 0x25), "right": ("Right", 0x27),
}
_FKEY = re.compile(r"f([1-9]|1\d|2[0-4])")

HINT = "например, Ctrl+Alt+L или Win+Shift+F8"


def supported() -> bool:
    return sys.platform == "win32"


def _parse(text: str) -> Tuple[int, str, int]:
    """(маска модификаторов, красивое имя клавиши, виртуальный код). ValueError с понятным текстом."""
    parts = [p.strip() for p in str(text).split("+") if p.strip()]
    if not parts:
        raise ValueError(f"не указано сочетание клавиш ({HINT})")
    *mod_names, key = parts
    mods = 0
    for m in mod_names:
        flag = _MODS.get(m.lower())
        if flag is None:
            raise ValueError(f"«{m}» не клавиша-модификатор: можно Ctrl, Alt, Shift, Win ({HINT})")
        mods |= flag
    k = key.lower()
    if k in _MODS:
        raise ValueError(f"после модификаторов нужна обычная клавиша ({HINT})")
    if k in _NAMED:
        name, vk = _NAMED[k]
    elif _FKEY.fullmatch(k):
        name, vk = k.upper(), 0x70 + int(k[1:]) - 1
    elif len(k) == 1 and k.isascii() and k.isalnum():
        name, vk = k.upper(), ord(k.upper())
    else:
        raise ValueError(f"не знаю клавишу «{key}» ({HINT})")
    if not mods and not _FKEY.fullmatch(k):
        raise ValueError(f"нужна хотя бы одна клавиша-модификатор: Ctrl, Alt, Shift или Win ({HINT})")
    return mods, name, vk


def parse_hotkey(text: str) -> Tuple[int, int]:
    mods, _name, vk = _parse(text)
    return mods, vk


def normalize(text: str) -> str:
    """«alt + ctrl + l» -> «Ctrl+Alt+L»: одинаковая запись для сравнения и хранения."""
    mods, name, _vk = _parse(text)
    return "+".join([n for n, flag in _MOD_ORDER if mods & flag] + [name])


class HotkeyListener(threading.Thread):
    """Поток с циклом сообщений Windows: регистрирует сочетания и сообщает о нажатиях.

    Обращения к WinAPI собраны в методы _api_*, чтобы логику можно было проверить без Windows.
    """

    def __init__(self, bindings: Dict[int, str], on_hotkey: Callable[[int], None],
                 on_failed: Callable[[int, str], None]):
        super().__init__(daemon=True, name="ordo-hotkeys")
        self.bindings = bindings
        self.on_hotkey = on_hotkey
        self.on_failed = on_failed
        self.registered: List[int] = []
        self._ready = threading.Event()

    def run(self) -> None:
        try:
            self._api_setup()
            for hid, keys in self.bindings.items():
                try:
                    mods, vk = parse_hotkey(keys)
                except ValueError:
                    self.on_failed(hid, keys)
                    continue
                if self._api_register(hid, mods | MOD_NOREPEAT, vk):
                    self.registered.append(hid)
                else:  # чаще всего сочетание уже занято другой программой
                    self.on_failed(hid, keys)
            self._ready.set()
            while True:
                msg = self._api_wait_message()
                if msg is None:
                    break
                if msg[0] == WM_HOTKEY and msg[1] in self.registered:
                    self.on_hotkey(msg[1])
        finally:
            self._ready.set()
            for hid in self.registered:
                self._api_unregister(hid)

    def stop(self) -> None:
        self._ready.wait(3)
        self._api_post_quit()
        self.join(3)

    # ---- WinAPI (на других системах не вызывается) ----

    def _api_setup(self) -> None:
        import ctypes
        from ctypes import wintypes
        self._user32 = ctypes.windll.user32
        self._user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        self._msg = wintypes.MSG()
        # PostThreadMessage работает только если у потока уже есть очередь сообщений
        self._user32.PeekMessageW(ctypes.byref(self._msg), None, WM_USER, WM_USER, PM_NOREMOVE)

    def _api_register(self, hid: int, mods: int, vk: int) -> bool:
        return bool(self._user32.RegisterHotKey(None, hid, mods, vk))

    def _api_unregister(self, hid: int) -> None:
        self._user32.UnregisterHotKey(None, hid)

    def _api_wait_message(self) -> Optional[Tuple[int, int]]:
        import ctypes
        got = self._user32.GetMessageW(ctypes.byref(self._msg), None, 0, 0)
        if got <= 0:  # 0 = WM_QUIT, -1 = ошибка
            return None
        return self._msg.message, int(self._msg.wParam)

    def _api_post_quit(self) -> None:
        tid = getattr(self, "_tid", None)
        if tid:
            self._user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
