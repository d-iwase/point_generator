@echo off
setlocal
cd /d "%~dp0"
python3.12.exe app.py
if errorlevel 1 pause
