"""Автозапуск проверяем на подставном реестре: настоящий Windows тут недоступен."""
import sys
import types

import pytest

from ordo import autostart


class FakeKey:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_fake_winreg():
    store = {}
    m = types.ModuleType("winreg")
    m.HKEY_CURRENT_USER = "HKCU"
    m.KEY_SET_VALUE = 2
    m.REG_SZ = 1
    opened = []

    def open_key(root, path, reserved=0, access=0):
        opened.append((root, path))
        return FakeKey(store)

    def query(key, name):
        if name not in key.store:
            raise FileNotFoundError(name)
        return key.store[name], 1

    m.OpenKey = open_key
    m.QueryValueEx = query
    m.SetValueEx = lambda key, name, _r, _t, value: key.store.__setitem__(name, value)

    def delete(key, name):
        if name not in key.store:
            raise FileNotFoundError(name)
        del key.store[name]

    m.DeleteValue = delete
    m.store, m.opened = store, opened
    return m


@pytest.fixture
def fake_windows(monkeypatch):
    fake = make_fake_winreg()
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    return fake


def test_command_starts_minimized_without_console():
    cmd = autostart.command()
    assert cmd.endswith("-m ordo gui --minimized") and cmd.startswith('"')


def test_command_for_frozen_exe(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\Ordo\Ordo.exe")
    assert autostart.command().endswith("Ordo.exe\" --minimized")


def test_enable_disable_roundtrip(fake_windows):
    assert autostart.is_enabled() is False
    autostart.set_enabled(True)
    assert autostart.is_enabled() is True
    assert fake_windows.store["Ordo"] == autostart.command()
    assert fake_windows.opened[-1] == ("HKCU", autostart.RUN_KEY)  # только ветка текущего пользователя
    autostart.set_enabled(False)
    assert autostart.is_enabled() is False
    autostart.set_enabled(False)  # повторное выключение не падает


def test_not_supported_outside_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert autostart.supported() is False and autostart.is_enabled() is False
    with pytest.raises(OSError):
        autostart.set_enabled(True)
