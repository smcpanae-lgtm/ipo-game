# -*- coding: utf-8 -*-
"""チビキャラPNGのチェック柄背景を透過化して static/ に保存する。
外周からのフラッドフィルでチェック柄（明色2色）のみ除去し、
キャラ内部の白（シャツ等）は保護する。"""
from PIL import Image
from collections import deque
import os, sys

SRC_DIR = r"C:\Users\smcpa\Documents\Claude code\ipo_game"
DST_DIR = r"C:\ipo_game_worldmap\static"

FILES = [
    ("1. 正面向きで元気に立っているポーズ（待機用）.png",   "piece_idle.png"),
    ("2. 横向き（右向き）で腕を振って歩いているポーズ（移動用）.png", "piece_walk.png"),
    ("3. 尻もちをついて目を回しているポーズ（転落用）.png",  "piece_fall.png"),
    ("4. 両手を上げて大喜びしているポーズ（ゴール・成功用）.png", "piece_goal.png"),
]

TOL = 28  # チェック柄色との許容距離

def near(c, ref, tol=TOL):
    return abs(c[0]-ref[0]) <= tol and abs(c[1]-ref[1]) <= tol and abs(c[2]-ref[2]) <= tol

def process(src, dst):
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    px = im.load()

    # 角からチェック柄の2色を採取（4角×数点）
    refs = []
    for x, y in [(2,2),(40,2),(2,40),(w-3,2),(w-3,40),(2,h-3),(w-3,h-3),(w//2,2)]:
        c = px[x, y][:3]
        if not any(near(c, r, 12) for r in refs):
            refs.append(c)
    print(f"  checker colors: {refs[:4]}")

    def is_bg(c):
        return any(near(c, r) for r in refs)

    # 外周からBFS
    visited = bytearray(w*h)
    q = deque()
    for x in range(w):
        for y in (0, h-1):
            if is_bg(px[x,y][:3]) and not visited[y*w+x]:
                visited[y*w+x] = 1; q.append((x,y))
    for y in range(h):
        for x in (0, w-1):
            if is_bg(px[x,y][:3]) and not visited[y*w+x]:
                visited[y*w+x] = 1; q.append((x,y))
    n = 0
    while q:
        x, y = q.popleft()
        px[x, y] = (0, 0, 0, 0)
        n += 1
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx, ny = x+dx, y+dy
            if 0 <= nx < w and 0 <= ny < h and not visited[ny*w+nx]:
                if is_bg(px[nx,ny][:3]):
                    visited[ny*w+nx] = 1; q.append((nx,ny))
    print(f"  cleared {n} px ({100.0*n/(w*h):.1f}%)")

    # 余白をトリミングして 512px 角に収める
    bbox = im.getbbox()
    im = im.crop(bbox)
    im.thumbnail((512, 512), Image.LANCZOS)
    canvas = Image.new("RGBA", (512, 512), (0,0,0,0))
    canvas.paste(im, ((512-im.width)//2, 512-im.height))  # 下端揃え
    canvas.save(dst)
    print(f"  -> {dst} ({os.path.getsize(dst)//1024} KB)")

if __name__ == "__main__":
    os.makedirs(DST_DIR, exist_ok=True)
    for src_name, dst_name in FILES:
        print(src_name[:14])
        process(os.path.join(SRC_DIR, src_name), os.path.join(DST_DIR, dst_name))
