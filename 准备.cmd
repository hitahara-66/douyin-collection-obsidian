@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"

if exist "config\settings.yml" goto :settings_ok
copy /y "config\settings.example.yml" "config\settings.yml" >nul
echo [提示] 已生成 config\settings.yml（默认输出到 D:\Obsidian\抖音收藏），请按需修改。
:settings_ok

set "PYEXE=python"
where python >nul 2>nul
if not %errorlevel%==0 set "PYEXE=py -3"

rem 国内网络访问官方 PyPI 很慢；如已设置 PIP_INDEX_URL 则尊重你的设置
if not defined PIP_INDEX_URL set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"

if exist ".venv\Scripts\python.exe" goto :venv_ok
echo [1/4] 创建 Python 虚拟环境 ...
%PYEXE% -m venv .venv
if errorlevel 1 goto :fail
:venv_ok

echo [2/4] 安装 Python 核心依赖 ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r "processor\requirements-core.txt"
if errorlevel 1 goto :fail

echo [3/4] 尝试安装降级工具 f2（可选，失败不影响主流程）...
".venv\Scripts\python.exe" -m pip install -r "processor\requirements-fallback.txt"
if errorlevel 1 echo [提示] f2 未安装成功；仅当网页接口失效需要降级时才用到它。

echo [3b/4] 安装深挖依赖（yt-dlp / faster-whisper）...
".venv\Scripts\python.exe" -m pip install -r "processor\requirements-deep.txt"
if errorlevel 1 echo [警告] 深挖依赖安装失败，可稍后重跑「准备.cmd」；同步功能不受影响。

echo [4/4] 安装 Node 依赖 ...
pushd fetcher
call npm install
if errorlevel 1 goto :fail_npm
popd

echo.
echo 准备完成。下一步：双击「登录抖音.cmd」扫码登录，然后双击「同步.cmd」。
exit /b 0

:fail_npm
popd
:fail
echo.
echo [错误] 准备失败，请把上面的报错发给 Codex。
pause
exit /b 1
