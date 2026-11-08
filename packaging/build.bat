@echo off
rem Сборка Ordo.exe одной командой. Нужен Python 3.9+ с галочкой "Add to PATH".
setlocal
cd /d "%~dp0\.."
python -m venv .build-venv || goto :fail
call .build-venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :fail
python -m pip install -e ".[gui]" pyinstaller pillow || goto :fail
python packaging\make_icon.py || goto :fail
pyinstaller --noconfirm --clean packaging\ordo.spec || goto :fail
echo.
echo Готово: dist\Ordo\Ordo.exe
exit /b 0
:fail
echo Сборка не удалась, смотри сообщение выше.
exit /b 1
