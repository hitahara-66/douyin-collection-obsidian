@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto :need_setup
".venv\Scripts\python.exe" -m processor.sync --login
echo.
pause
exit /b 0

:need_setup
echo 请先双击「准备.cmd」完成安装。
pause
exit /b 1
