@echo off
title AI Laser Scanner - Online Desktop Widget (Synced)
cd /d "%~dp0desktop_app_online"
start "" pythonw floating_widget.py
exit /b 0
