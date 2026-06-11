# -*- coding: utf-8 -*-
"""ライバルチビキャラ3ポーズの背景透過処理"""
import sys, os
sys.path.insert(0, r"C:\ipo_game_worldmap\tools")
import process_sprites as ps

ps.FILES = [
    ("ライバル会社女性①.png", "rival_idle.png"),
    ("ライバル会社女性②.png", "rival_walk.png"),
    ("ライバル会社女性③.png", "rival_fall.png"),
]
os.makedirs(ps.DST_DIR, exist_ok=True)
for src, dst in ps.FILES:
    print(dst)
    ps.process(os.path.join(ps.SRC_DIR, src), os.path.join(ps.DST_DIR, dst))
