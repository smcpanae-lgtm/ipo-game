# -*- coding: utf-8 -*-
"""審査ボス戦（質疑応答）の動作検証。
全問正解 / 全問不正解 / ランダム回答 の3パターンで終局まで駆動し、
懸念ゲージの増減・指摘事項の追加/解消・最終判定を確認する。"""
import sys, io, random
sys.path.insert(0, r"C:\ipo_game_worldmap")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from web_game import GameSession, Phase


def run(answer_mode: str, seed: int, biz="A", market="A"):
    random.seed(seed)
    s = GameSession()
    blob_parts = []

    def go(v):
        r = s.handle(v)
        items = r[0] if isinstance(r, tuple) else []
        for it in items or []:
            blob_parts.append(it.get("html", "") if isinstance(it, dict) else str(it))

    go(""); go("__START__"); go(biz); go(market); go(f"BOSS-{answer_mode}")

    battle_seen = False
    battle_qids = []
    gauge_log = []
    for _ in range(600):
        phase = s.phase
        if phase == Phase.ENDING:
            break
        if phase == Phase.EXAM_BATTLE:
            battle_seen = True
            q = s._exam_qs[s._exam_idx]
            battle_qids.append(q["id"])
            ans = s._exam_q_answer(q)
            if answer_mode == "perfect":
                pick = "ABCD"[ans]
            elif answer_mode == "fail":
                pick = "ABCD"[(ans + 1) % 4]
            else:
                pick = random.choice("ABCD")
            go(pick)
            gauge_log.append(s._exam_gauge)
        elif phase in (Phase.EVENT_CHOICE, Phase.FORTUNE_CHOICE, Phase.ALT_CHOICE):
            go("A")   # 守り重視（審査到達率を上げる）
        else:
            go("")

    blob = "".join(blob_parts)
    ending = "?"
    for key, lab in [("上 場 承 認", "承認"), ("形式要件未達", "形式未達"),
                     ("上 場 審 査 不 通 過", "不通過"), ("上 場 申 請 却 下", "却下"),
                     ("倒産", "倒産"), ("解任", "解任")]:
        if key in blob:
            ending = lab
            break
    return {
        "mode": answer_mode, "seed": seed,
        "battle": battle_seen,
        "qids": battle_qids,
        "correct": getattr(s, "_exam_correct", -1),
        "gauge": gauge_log,
        "relief": "😌 審査官の懸念が解消" in blob,
        "penalty": "😠 審査官の懸念が増大" in blob,
        "added_issue": "審査質疑応答" in blob,
        "ending": ending,
    }


if __name__ == "__main__":
    for mode in ("perfect", "fail", "random"):
        for seed in (11, 22, 33):
            r = run(mode, seed)
            print(f"[{r['mode']:7s} seed={r['seed']}] battle={r['battle']} "
                  f"correct={r['correct']}/5 gauge={r['gauge']} "
                  f"relief={r['relief']} penalty={r['penalty']} ending={r['ending']}")
            print(f"    出題: {r['qids']}")
