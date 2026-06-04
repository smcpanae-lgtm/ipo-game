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

:: ── Gemini APIキーは gemini_api_key.txt から読み込みます ──
::   （このファイルは .gitignore 済み＝GitHubに公開されません）
::   AIナラティブを使うには C:\ipo_game\gemini_api_key.txt に
::   キーを1行で記入してください。未設定ならルールベースで動作します。
echo.
echo  ── Gemini AI ナラティブ設定 ──────────────────────────────
echo  AIを使う場合: gemini_api_key.txt にAPIキーを1行で記入
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
C:\ipo_venv\Scripts\python.exe "C:\ipo_game\web_game.py"
pause
