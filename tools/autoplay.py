# -*- coding: utf-8 -*-
"""バランステスト用オートプレイ。
GameSession を直接駆動し、3つのポリシーで終局まで進めて結果を集計する。
  safe   : 常に A（守り寄り）
  cheap  : 常に最後の選択肢（手抜き・攻め寄り）
  theory : 序盤(N-3〜N-2)は3択以上なら最後＝攻め、2択はA。終盤(N-1〜)は常にA（守りへシフト）
"""
import sys, io, random
sys.path.insert(0, r"C:\ipo_game_worldmap")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from web_game import GameSession, Phase
from engine.finance import effective_growth_rate


def run(policy: str, seed: int):
    random.seed(seed)
    s = GameSession()
    blob_parts = []

    def go(v):
        r = s.handle(v)
        items = r[0] if isinstance(r, tuple) else []
        for it in items or []:
            blob_parts.append(it.get("html", "") if isinstance(it, dict) else str(it))

    go("")            # タイトル
    go("__START__")
    go("A")           # 業種 SaaS
    go("A")           # グロース
    go(f"AUTO-{policy}")  # 社名

    step = 0
    for step in range(600):
        phase = s.phase
        if phase == Phase.ENDING:
            break
        if phase in (Phase.EVENT_CHOICE, Phase.FORTUNE_CHOICE, Phase.ALT_CHOICE):
            if phase == Phase.ALT_CHOICE:
                n = len(s._alt_choices)
            elif phase == Phase.EVENT_CHOICE:
                ev = s.pending_events[s.pending_event_idx]
                n = len(ev.choices)
            else:
                n = max(1, len(getattr(s, "_fortune_choices", []) or [1, 1]))
            letters = "ABCD"[:max(1, n)]
            t = s.timeline
            if policy == "safe":
                pick = "A"
            elif policy == "cheap":
                pick = letters[-1]
            else:  # theory
                early = (t is not None) and (t.n_period <= -2)
                pick = (letters[-1] if (early and n >= 3 and phase == Phase.EVENT_CHOICE) else "A")
            go(pick)
        else:
            go("")

    c = s.company
    blob = "".join(blob_parts[-200:])
    ending = "?"
    for key, lab in [("CONGRATULATIONS", "🏆成功"), ("上 場 承 認", "🏆承認"), ("形式要件未達", "形式未達"),
                     ("上 場 審 査 不 通 過", "不通過"), ("上 場 申 請 却 下", "却下"),
                     ("上場1年延期", "延期"), ("倒産", "倒産"), ("解任", "解任")]:
        if key in blob:
            ending = lab
            break
    return {
        "policy": policy, "seed": seed, "steps": step, "phase": str(s.phase).split(".")[-1],
        "mktcap": round(c.market_cap_million) if c else -1,
        "cash": round(c.cash) if c else -1,
        "g": round(effective_growth_rate(c) * 100, 1) if c else -1,
        "mi": round(getattr(c, "market_index", 55.0)) if c else -1,
        "od": f"{getattr(c,'offense_score',0)}/{getattr(c,'defense_score',0)}" if c else "-",
        "risk": c.flags.total_risk_score if c else -1,
        "shr": c.shareholder_count if c else -1,
        "pos": getattr(s, "_map_pos", "-"),
        "ending": ending,
    }


if __name__ == "__main__":
    print(f"{'policy':7} {'seed':4} {'steps':5} {'phase':10} {'mktcap':>7} {'cash':>6} {'g%':>5} {'mi':>3} {'off/def':>7} {'risk':>4} {'shr':>4} {'pos':>3}  ending")
    for pol in ("safe", "cheap", "theory"):
        for seed in (11, 22, 33):
            try:
                r = run(pol, seed)
                print(f"{r['policy']:7} {r['seed']:<4} {r['steps']:<5} {r['phase']:10} {r['mktcap']:>7} {r['cash']:>6} "
                      f"{r['g']:>5} {r['mi']:>3} {r['od']:>7} {r['risk']:>4} {r['shr']:>4} {str(r['pos']):>3}  {r['ending']}")
            except Exception as e:
                import traceback
                print(f"{pol:7} seed={seed} ERROR: {e}")
                traceback.print_exc()
