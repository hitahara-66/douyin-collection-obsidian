@echo off
chcp 65001 >nul
rem 供 Windows 计划任务调用的无界面同步入口：不 pause，输出追加到 data\logs\scheduled.log
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"

if not exist "data\logs" mkdir "data\logs"
>>"data\logs\scheduled.log" echo.
>>"data\logs\scheduled.log" echo ===== %date% %time% =====
".venv\Scripts\python.exe" -m processor.sync >>"data\logs\scheduled.log" 2>&1
set "RC=%ERRORLEVEL%"
>>"data\logs\scheduled.log" echo ===== exit=%RC% =====
exit /b %RC%
