@echo off
title AI Laser Scanner - Floating Widget
cd /d "%~dp0desktop_app"
python floating_widget.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Widget closed with error code %ERRORLEVEL%.
    pause
)
