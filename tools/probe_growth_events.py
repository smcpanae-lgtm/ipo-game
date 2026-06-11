# -*- coding: utf-8 -*-
"""成長戦略イベントが年度ごとに最低1回出現することを検証"""
import sys, io, random, re
sys.path.insert(0, r"C:\ipo_game_worldmap")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from web_game import GameSession, Phase


def probe(seed):
    random.seed(seed)
    s = GameSession()
    blob = []

    def go(v):
        r = s.handle(v)
        for it in (r[0] if isinstance(r, tuple) else []) or []:
            html = it.get("html", "") if isinstance(it, dict) else str(it)
            t = s.timeline
            blob.append((t.n_period if t else None, t.quarter if t else None, html))

    go(""); go("__START__"); go("A"); go("A"); go("X")
    for _ in range(600):
        if s.phase == Phase.ENDING:
            break
        if s.phase in (Phase.EVENT_CHOICE, Phase.FORTUNE_CHOICE, Phase.ALT_CHOICE):
            go("A")
        else:
            go("")

    hits = {}
    for n, q, html in blob:
        if "売上成長戦略の実行" in html or "上場直前の成長戦略" in html:
            hits.setdefault(n, []).append(f"Q{q}")
    print(f"seed{seed}: 成長戦略イベント出現 = " +
          ", ".join(f"N{n}期:{'/'.join(qs)}" for n, qs in sorted(hits.items())))
    missing = [p for p in (-3, -2, -1, 0) if p not in hits]
    print(f"  未出現の期: {missing if missing else 'なし ✅'}")


for seed in (11, 22, 33, 44):
    probe(seed)
