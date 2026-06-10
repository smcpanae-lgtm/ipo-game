# -*- coding: utf-8 -*-
"""不通過ケースの審査指摘事項を抽出するデバッグスクリプト"""
import sys, io, random, re
sys.path.insert(0, r"C:\ipo_game_worldmap")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from web_game import GameSession, Phase


def probe(policy, seed):
    random.seed(seed)
    s = GameSession()
    blob = []

    def go(v):
        r = s.handle(v)
        for it in (r[0] if isinstance(r, tuple) else []) or []:
            blob.append(it.get("html", "") if isinstance(it, dict) else str(it))

    go(""); go("__START__"); go("A"); go("A"); go("X")
    for _ in range(600):
        if s.phase == Phase.ENDING:
            break
        if s.phase in (Phase.EVENT_CHOICE, Phase.FORTUNE_CHOICE, Phase.ALT_CHOICE):
            if s.phase == Phase.ALT_CHOICE:
                n = len(s._alt_choices)
            elif s.phase == Phase.EVENT_CHOICE:
                n = len(s.pending_events[s.pending_event_idx].choices)
            else:
                n = 2
            t = s.timeline
            letters = "ABCD"[:max(1, n)]
            if policy == "safe":
                pick = "A"
            else:
                pick = (letters[-1] if (t and t.n_period <= -2 and n >= 3 and s.phase == Phase.EVENT_CHOICE) else "A")
            go(pick)
        else:
            go("")
    text = "".join(blob)
    fails = re.findall(r"FAIL &nbsp; ([^<]+)", text)
    print(f"--- {policy} seed{seed} FAIL項目 ---")
    for f in fails[-12:]:
        print("  ", f[:90])


for args in [("safe", 22), ("theory", 22), ("theory", 33), ("theory", 11)]:
    probe(*args)
