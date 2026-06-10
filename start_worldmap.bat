@echo off
:: ════════════════════════════════════════════
::  THE IPO PATH - ワールドマップ版（開発用）
::  C:\ipo_game_worldmap で起動します
:: ════════════════════════════════════════════

:: ポート5000で動いている旧プロセスを強制終了
echo  既存のサーバーを停止中...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr /R ":5000 "') do (
    taskkill /pid %%a /f >nul 2>&1
)
timeout /t 2 /nobreak >nul

if not exist C:\ipo_venv\Scripts\python.exe (
    C:\Python314\python.exe -m venv C:\ipo_venv
)
C:\ipo_venv\Scripts\pip.exe install rich flask google-genai dill --quiet

echo.
echo  ====================================================
echo    THE IPO PATH [WorldMap DEV]: Launching...
echo    http://127.0.0.1:5000 をブラウザで開いてください
echo    終了するには このウィンドウを閉じてください
echo  ====================================================
echo.
start http://127.0.0.1:5000
C:\ipo_venv\Scripts\python.exe "C:\ipo_game_worldmap\web_game.py"
pause
