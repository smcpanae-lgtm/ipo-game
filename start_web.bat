@echo off
cd /d "%~dp0"

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

:: ★ ここにあなたのGemini APIキーを貼り付けてください ★
set GEMINI_API_KEY=AIzaSyDGx8EGSCaubClwUN1_uM5aI-W71MhU9bA
echo.
echo  ── Gemini AI ナラティブ設定（任意）──────────────────────
echo  AIナラティブを有効化するには：
echo  set GEMINI_API_KEY=あなたのAPIキー
echo  （Google AI Studio https://aistudio.google.com/ で無料取得）
echo  未設定の場合はルールベースナラティブで動作します
echo  ────────────────────────────────────────────────────────
echo.
echo  ====================================================
echo    THE IPO PATH: Launching Web Browser Game...
echo    http://127.0.0.1:5000 が自動的に開きます
echo    終了するには このウィンドウを閉じてください
echo  ====================================================
echo.
C:\ipo_venv\Scripts\python.exe web_game.py
pause
