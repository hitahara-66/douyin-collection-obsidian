@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto :need_setup
".venv\Scripts\python.exe" -m processor.sync %*
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" echo [提示] 退出码 %EXITCODE%（2=需要登录，1=出错；详细见 data\logs）
pause
exit /b %EXITCODE%

:need_setup
echo 请先双击「准备.cmd」完成安装。
pause
exit /b 1
