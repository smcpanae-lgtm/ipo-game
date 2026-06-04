#!/usr/bin/env python3
# split_avatars_v2.py — キャラクターシートを顔まわりに寄せて16枚に再分割
#   v1からの変更：上の余白・左右の余白・下のラベル帯をより多くカットし、
#   顔がアバター枠いっぱいに表示されるようにする。

from PIL import Image
import pathlib

SRC = pathlib.Path(r"C:\Users\smcpa\Documents\Claude code\ipo_game\ChatGPT Image 2026年6月3日 22_15_30.png")
DST = pathlib.Path(r"C:\ipo_game\static")
DST.mkdir(exist_ok=True)

img = Image.open(SRC)
W, H = img.size
print(f"画像サイズ: {W} x {H}")

COLS, ROWS = 4, 4
cw = W / COLS
ch = H / ROWS

# 各セル内のトリミング比率（顔に寄せる）
TOP    = 0.04   # 上の余白カット
BOTTOM = 0.17   # 下のラベル帯カット（やや多め）
SIDE   = 0.11   # 左右の余白カット

chars = [
    (0, 0, "teacher_normal"),    (0, 1, "teacher_mouth"),
    (0, 2, "ceo_normal"),        (0, 3, "ceo_mouth"),
    (1, 0, "advisor_normal"),    (1, 1, "advisor_mouth"),
    (1, 2, "underwriter_normal"),(1, 3, "underwriter_mouth"),
    (2, 0, "director_a_normal"), (2, 1, "director_a_mouth"),
    (2, 2, "director_b_normal"), (2, 3, "director_b_mouth"),
    (3, 0, "investor_a_normal"), (3, 1, "investor_a_mouth"),
    (3, 2, "investor_b_normal"), (3, 3, "investor_b_mouth"),
]

for row, col, name in chars:
    left   = int(col * cw + cw * SIDE)
    right  = int((col + 1) * cw - cw * SIDE)
    top    = int(row * ch + ch * TOP)
    bottom = int((row + 1) * ch - ch * BOTTOM)
    cropped = img.crop((left, top, right, bottom))
    out = DST / f"{name}.png"
    cropped.save(out)
    print(f"[OK] {name}.png  ({left},{top})-({right},{bottom})  size={cropped.size}")

print(f"\n✅ 16枚を顔寄せで再保存しました → {DST}")
