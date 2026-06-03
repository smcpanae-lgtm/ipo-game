@echo off
cd /d "%~dp0"
C:\ipo_venv\Scripts\python.exe check_syntax.py > check_output.txt 2>&1
