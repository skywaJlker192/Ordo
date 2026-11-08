# PyInstaller: одна папка с Ordo.exe, без консольного окна. Запуск: pyinstaller packaging/ordo.spec
from pathlib import Path

root = Path(SPECPATH).parent
icon = root / "packaging" / "ordo.ico"

a = Analysis(
    [str(root / "packaging" / "ordo_gui.py")],
    pathex=[str(root)],
    datas=[(str(root / "ordo" / "presets"), "ordo/presets")],
    # ненужное Qt-обвязка не тянем: приложение лёгкое
    excludes=["tkinter", "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngineCore", "PyQt5.QtQml",
              "PyQt5.QtQuick", "PyQt5.QtMultimedia", "PyQt5.QtSql", "PyQt5.QtTest", "matplotlib", "numpy"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Ordo",
    console=False,
    icon=str(icon) if icon.exists() else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Ordo", upx=False)
