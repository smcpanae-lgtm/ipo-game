@echo off
cd /d "%~dp0"
if not exist "C:\ipo_venv\Scripts\python.exe" (
    C:\Python314\python.exe -m venv C:\ipo_venv
    C:\ipo_venv\Scripts\pip.exe install rich
)
C:\ipo_venv\Scripts\python.exe main.py
pause
