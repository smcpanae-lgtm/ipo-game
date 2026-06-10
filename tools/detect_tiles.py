# -*- coding: utf-8 -*-
"""マップ盤面イラストからマス目（明るいベージュの円盤）を検出し、
中心座標一覧と確認用のマーカー入り画像を出力する。"""
from PIL import Image, ImageDraw, ImageFont
from collections import deque
import os

SRC = r"C:\Users\smcpa\Documents\Claude code\ipo_game\マップ盤面イラスト.png"
DST_JPG = r"C:\ipo_game_worldmap\static\bg_worldmap.jpg"
DBG = r"C:\ipo_game_worldmap\tools\tiles_debug.png"

im = Image.open(SRC).convert("RGB")
w, h = im.size
px = im.load()

# マップ本体をJPGで保存
im.save(DST_JPG, quality=86)
print(f"map: {w}x{h} -> {DST_JPG} ({os.path.getsize(DST_JPG)//1024} KB)")

# 円盤らしい色（明るいベージュ〜クリーム）判定
def is_tile_color(c):
    r, g, b = c
    return (195 <= r <= 255 and 180 <= g <= 245 and 150 <= b <= 230
            and r >= g >= b and (r - b) >= 15 and (r - b) <= 80)

visited = bytearray(w*h)
comps = []
for y in range(0, h, 2):          # 2px間引きで高速化
    for x in range(0, w, 2):
        if visited[y*w+x] or not is_tile_color(px[x, y]):
            continue
        # BFS
        q = deque([(x, y)])
        visited[y*w+x] = 1
        pts_n = 0; sx = 0; sy = 0
        minx = maxx = x; miny = maxy = y
        while q:
            cx, cy = q.popleft()
            pts_n += 1; sx += cx; sy += cy
            minx = min(minx, cx); maxx = max(maxx, cx)
            miny = min(miny, cy); maxy = max(maxy, cy)
            for dx, dy in ((2,0),(-2,0),(0,2),(0,-2)):
                nx, ny = cx+dx, cy+dy
                if 0 <= nx < w and 0 <= ny < h and not visited[ny*w+nx] and is_tile_color(px[nx, ny]):
                    visited[ny*w+nx] = 1
                    q.append((nx, ny))
        bw, bh = maxx-minx, maxy-miny
        if pts_n < 60 or bw < 18 or bh < 10 or bw > 130 or bh > 130:
            continue
        # 円盤はほぼ楕円＝バウンディングボックスへの充填率が高い
        fill = pts_n / max(1, (bw/2)*(bh/2))
        comps.append((sx/pts_n, sy/pts_n, bw, bh, pts_n, fill))

print(f"components: {len(comps)}")
dbg = im.copy()
d = ImageDraw.Draw(dbg)
try:
    font = ImageFont.truetype("arial.ttf", 30)
except Exception:
    font = None
for i, (cx, cy, bw, bh, n, fill) in enumerate(sorted(comps, key=lambda c: (-c[1], c[0]))):
    d.ellipse([cx-8, cy-8, cx+8, cy+8], fill=(255,0,0))
    d.text((cx+10, cy-18), str(i), fill=(255,0,0), font=font)
    print(f"{i}: ({cx:.0f},{cy:.0f}) box={bw}x{bh} n={n} fill={fill:.2f}")
dbg.save(DBG)
print("debug ->", DBG)
