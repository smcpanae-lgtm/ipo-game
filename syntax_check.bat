@echo off
cd /d "%~dp0"
C:\ipo_venv\Scripts\python.exe -c "import ast; ast.parse(open('web_game.py',encoding='utf-8').read()); print('web_game.py: syntax OK')" 2>&1
pause
