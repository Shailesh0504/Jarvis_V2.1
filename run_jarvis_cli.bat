@echo off
setlocal
title JARVIS V2.1 - Interactive CLI
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_CMD=%~dp0venv\Scripts\python.exe"
) else (
    set "PYTHON_CMD=python"
)
"%PYTHON_CMD%" main.py --cli %*
endlocal
