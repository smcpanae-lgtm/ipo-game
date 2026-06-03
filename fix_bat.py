import os

game_dir = os.path.join(os.environ["USERPROFILE"], "Documents", "Claude code", "ipo_game")

# 英語名のバッチファイルを新規作成（日本語ファイル名を避ける）
bat_path = os.path.join(game_dir, "start_game.bat")

lines = [
    "@echo off",
    'cd /d "%~dp0"',
    "if not exist C:\\ipo_venv\\Scripts\\python.exe (",
    "    C:\\Python314\\python.exe -m venv C:\\ipo_venv",
    "    C:\\ipo_venv\\Scripts\\pip.exe install rich",
    ")",
    "C:\\ipo_venv\\Scripts\\python.exe main.py",
    "pause",
]

with open(bat_path, "w", encoding="ascii") as f:
    f.write("\r\n".join(lines) + "\r\n")

print("OK: " + bat_path)
print("-> start_game.bat をダブルクリックするとゲームが起動します")
