@echo off
setlocal
rem Dynamic startup launcher for Windows Startup folder
for %%I in ("%~dp0..") do set "JARVIS_ROOT=%%~fI"
if exist "%JARVIS_ROOT%\.venv\Scripts\pythonw.exe" (
    set "JARVIS_PYTHON=%JARVIS_ROOT%\.venv\Scripts\pythonw.exe"
) else (
    set "JARVIS_PYTHON=pythonw.exe"
)
set "JARVIS_MAIN=%JARVIS_ROOT%\main.py"
cd /d "%JARVIS_ROOT%"
start "Jarvis V2" /min "%JARVIS_PYTHON%" "%JARVIS_MAIN%"
endlocal
