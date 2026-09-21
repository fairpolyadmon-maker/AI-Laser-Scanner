@echo off
cd /d "%~dp0"
if exist "dist\AI Laser Scanner.exe" (
    start "" "dist\AI Laser Scanner.exe"
    exit /b 0
)
cd /d "%~dp0desktop_offline_app"
start "" pythonw floating_widget.py
exit /b 0
