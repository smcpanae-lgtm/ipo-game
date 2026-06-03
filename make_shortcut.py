import os

desktop  = os.path.join(os.environ["USERPROFILE"], "Desktop")
game_dir = os.path.join(os.environ["USERPROFILE"], "Documents", "Claude code", "ipo_game")
bat_name = "\u30b2\u30fc\u30e0\u8d77\u52d5.bat"   # ゲーム起動.bat
lnk_name = "IPO\u30b2\u30fc\u30e0.lnk"            # IPOゲーム.lnk

lnk_path = os.path.join(desktop, lnk_name)
bat_path  = os.path.join(game_dir, bat_name)

vbs_lines = [
    'Set ws = CreateObject("WScript.Shell")',
    'Set sc = ws.CreateShortcut("{}")'.format(lnk_path),
    'sc.TargetPath = "{}"'.format(bat_path),
    'sc.WorkingDirectory = "{}"'.format(game_dir),
    'sc.WindowStyle = 1',
    'sc.Description = "The IPO Path"',
    'sc.Save',
    'WScript.Echo "OK"',
]

vbs_path = os.path.join(os.environ["TEMP"], "mksc.vbs")
with open(vbs_path, "w", encoding="utf-16") as f:
    f.write("\n".join(vbs_lines))

ret = os.system('cscript //Nologo "{}"'.format(vbs_path))
os.remove(vbs_path)

if os.path.exists(lnk_path):
    print("ショートカット作成成功: " + lnk_path)
else:
    print("作成失敗 (ret={})".format(ret))
