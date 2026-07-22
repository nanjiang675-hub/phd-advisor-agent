@echo off
cd /d "%~dp0"
set "PYTHON_CMD=python"
where python >nul 2>nul
if errorlevel 1 set "PYTHON_CMD=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON_CMD%" (
  echo Python was not found. Please ask your administrator to install Python 3.10 or newer.
  pause
  exit /b 1
)
"%PYTHON_CMD%" agent.py init
"%PYTHON_CMD%" agent.py export
"%PYTHON_CMD%" agent.py serve
pause
