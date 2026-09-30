@echo off
title AI Laser Scanner - Online Desktop Widget (Synced)
cd /d "%~dp0"
if exist "AI Laser Scanner Online.exe" (
    start "" "AI Laser Scanner Online.exe"
    exit /b 0
)
cd /d "%~dp0desktop_app_online"
start "" pythonw floating_widget.py
exit /b 0
