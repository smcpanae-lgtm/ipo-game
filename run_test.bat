@echo off
cd /d "%~dp0"
C:\ipo_venv\Scripts\python.exe test_imports.py > test_out.txt 2> test_err.txt
