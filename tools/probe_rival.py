# -*- coding: utf-8 -*-
"""ライバルレースの進行・ニュース・先行上場ディスカウントを検証"""
import sys, io, random
sys.path.insert(0, r"C:\ipo_game_worldmap")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from web_game import GameSession, Phase


def probe(seed):
    random.seed(seed)
    s = GameSession()
    news = scandal = surge = listed_news = 0

    def go(v):
        nonlocal news, scandal, surge, listed_news
        r = s.handle(v)
        for it in (r[0] if isinstance(r, tuple) else []) or []:
            html = it.get("html", "") if isinstance(it, dict) else str(it)
            if "業界ニュース — 上場レース" in html:
                news += 1
                if "不祥事報道" in html:
                    scandal += 1
                if "急成長" in html:
                    surge += 1
                if "【速報】" in html and "上場！" in html:
                    listed_news += 1

    go(""); go("__START__"); go("A"); go("A"); go("X")
    for _ in range(600):
        if s.phase == Phase.ENDING:
            break
        if s.phase in (Phase.EVENT_CHOICE, Phase.FORTUNE_CHOICE, Phase.ALT_CHOICE):
            go("A")
        else:
            go("")

    rv = getattr(s, "_rival", {})
    c = s.company
    print(f"seed{seed}: rival={rv.get('name')} pos={rv.get('pos')}/26 listed={rv.get('listed')} "
          f"| player_pos={getattr(s,'_map_pos','?')} discount={getattr(c,'rival_listed_first',False)} "
          f"| news={news}（不祥事{scandal}/急成長{surge}/上場速報{listed_news}） mktcap={c.market_cap_million:,.0f}M")


for seed in (11, 22, 33, 44, 55):
    probe(seed)
