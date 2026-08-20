@echo off
cd /d "%~dp0"
set "PY_EXE=%~dp0.venv\Scripts\python.exe"
set "PY_ARGS="
if exist "%PY_EXE%" goto run
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY_EXE=py"
  set "PY_ARGS=-3"
  goto run
)
where python >nul 2>nul
if %errorlevel%==0 (
  set "PY_EXE=python"
  set "PY_ARGS="
  goto run
)
echo [ERROR] 找不到 Python。请先安装 Python 3，或在项目里创建 .venv。
pause
exit /b 1
:run
"%PY_EXE%" %PY_ARGS% launcher.py
if errorlevel 1 (
  echo.
  echo 启动失败。按任意键查看后关闭。
  pause
)
