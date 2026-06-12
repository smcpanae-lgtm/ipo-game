# -*- coding: utf-8 -*-
"""切り札イベントの発火・効果を検証（policyで選ぶカードを変える）"""
import sys, io, random
sys.path.insert(0, r"C:\ipo_game_worldmap")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from web_game import GameSession, Phase


def probe(seed, trump_pick):
    random.seed(seed)
    s = GameSession()
    offers = 0
    used_msgs = []

    def go(v):
        nonlocal offers
        r = s.handle(v)
        for it in (r[0] if isinstance(r, tuple) else []) or []:
            html = it.get("html", "") if isinstance(it, dict) else str(it)
            if "緊急取締役会 — 社長の切り札" in html and "panel-title" in html:
                offers += 1
            for key in ("メディア戦略", "アライアンス電撃", "引き抜きに成功"):
                if key in html and "意思決定" not in html and "choice-item" not in html:
                    if key not in used_msgs:
                        used_msgs.append(key)

    go(""); go("__START__"); go("A"); go("A"); go("X")
    for _ in range(600):
        if s.phase == Phase.ENDING:
            break
        if s.phase in (Phase.EVENT_CHOICE, Phase.FORTUNE_CHOICE, Phase.ALT_CHOICE):
            pick = "A"
            if s.phase == Phase.EVENT_CHOICE:
                ev = s.pending_events[s.pending_event_idx]
                if getattr(ev, "id", "") == "trump_card":
                    pick = trump_pick
            go(pick)
        else:
            go("")

    rv = getattr(s, "_rival", {})
    c = s.company
    print(f"seed{seed} pick={trump_pick}: 提示{offers}回 used={getattr(s,'_trump_used',False)} "
          f"| rival={rv.get('pos')}/26 listed={rv.get('listed')} "
          f"player={getattr(s,'_map_pos','?')} risk={c.flags.total_risk_score} "
          f"discount={getattr(c,'rival_discount',None) if getattr(c,'rival_listed_first',False) else 'なし'} "
          f"mktcap={c.market_cap_million:,.0f}M")


for seed, pick in [(22, "A"), (55, "B"), (22, "C"), (55, "D")]:
    probe(seed, pick)
