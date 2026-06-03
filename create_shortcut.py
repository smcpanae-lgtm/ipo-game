"""デスクトップにショートカットを作成するスクリプト"""
import os
import sys

# デスクトップのパスを取得
desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
lnk_path = os.path.join(desktop, "IPO\u30b2\u30fc\u30e0\u8d77\u52d5.lnk")
bat_path  = r"C:\Users\smcpa\Documents\Claude code\ipo_game\u30b2\u30fc\u30e0\u8d77\u52d5.bat"

# VBScriptでショートカットを作成
bat_path  = os.path.join(
    r"C:\Users\smcpa\Documents\Claude code\ipo_game",
    "\u30b2\u30fc\u30e0\u8d77\u52d5.bat"
)
work_dir  = r"C:\Users\smcpa\Documents\Claude code\ipo_game"

vbs = f'''
Set ws = CreateObject("WScript.Shell")
Set sc = ws.CreateShortcut("{lnk_path}")
sc.TargetPath      = "{bat_path}"
sc.WorkingDirectory = "{work_dir}"
sc.WindowStyle     = 1
sc.Description     = "The IPO Path: Eiryo heno Ketsudan"
sc.Save
WScript.Echo "OK: " & "{lnk_path}"
'''

# VBSファイルに書き出して実行
vbs_path = os.path.join(os.environ["TEMP"], "make_shortcut.vbs")
with open(vbs_path, "w", encoding="utf-8") as f:
    f.write(vbs)

ret = os.system(f'cscript //Nologo "{vbs_path}"')
if ret == 0 and os.path.exists(lnk_path):
    print(f"ショートカットを作成しました:\n  {lnk_path}")
else:
    print("作成に失敗しました。手動で作成してください。")

os.remove(vbs_path)
