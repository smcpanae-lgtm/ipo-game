# -*- coding: utf-8 -*-
"""タイマークライシス（後任CFO選定）の動作検証。
CFO逮捕の自然発生を待たず、内部状態を直接セットしてクライシスを発生させ、
①毎ターン必ず選択肢が出るか ②先送りで残り期数が減るか
③期限切れで確定ペナルティが発生するか ④対応で即時解消されるか を確認する。
※ 効果の説明文は「次ターン冒頭の意思決定結果報告」に遅延表示されるため、
  各ターンの先頭ブロックで前ターンの結果文をチェックする。"""
import sys, io, random
sys.path.insert(0, r"C:\ipo_game_worldmap")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from web_game import GameSession, Phase


def go(s, v):
    r = s.handle(v)
    items = r[0] if isinstance(r, tuple) else []
    txt = ""
    for it in items or []:
        txt += it.get("html", "") if isinstance(it, dict) else str(it)
    return txt


def setup(seed):
    random.seed(seed)
    s = GameSession()
    go(s, ""); go(s, "__START__"); go(s, "A"); go(s, "A"); go(s, "")
    s.company.cfo_arrested = True
    s._timer_crisis = {"id": "cfo_successor", "remaining": 2}
    return s


def advance_to_choice(s, max_steps=20):
    txt_acc = ""
    for _ in range(max_steps):
        if s.phase == Phase.ENDING:
            return None
        if s.phase in (Phase.EVENT_CHOICE, Phase.ALT_CHOICE, Phase.FORTUNE_CHOICE):
            return txt_acc
        txt_acc += go(s, "")
    return txt_acc


def drive_to_next_turn_report(s, steps=40):
    """次ターン冒頭の「意思決定結果報告」が出るまで進める（途中の選択は全てA）。
    累積テキストを返す。"""
    acc = ""
    for _ in range(steps):
        if s.phase == Phase.ENDING:
            break
        if s.phase in (Phase.EVENT_CHOICE, Phase.ALT_CHOICE, Phase.FORTUNE_CHOICE):
            acc += go(s, "A")
        else:
            acc += go(s, "")
        if "前Q意思決定の結果報告" in acc:
            break
    return acc


def choose_until_crisis_or_end(s, pick="A", max_picks=10):
    """現在のEVENT_CHOICEがクライシスならpickを選び、結果(remaining/expired/resolved含む報告)を集める。
    クライシス以外ならA（守り）で進める。クライシス解消/期限切れまで繰り返す。"""
    log = []
    for _ in range(max_picks):
        txt = advance_to_choice(s)
        if txt is None:
            log.append(("ended", None))
            break
        is_crisis = False
        if s.phase == Phase.EVENT_CHOICE and s.pending_event_idx < len(s.pending_events):
            is_crisis = getattr(s.pending_events[s.pending_event_idx], "id", "") == "cfo_successor_crisis"
        remaining_before = s._timer_crisis["remaining"] if s._timer_crisis else None
        if is_crisis:
            out = go(s, pick)
            log.append(("crisis_choice", pick, remaining_before, dict(s._timer_crisis) if s._timer_crisis else None, out))
            if s._timer_crisis is None:
                # 解消 or 期限切れ。次ターン冒頭の結果報告を確認
                report = drive_to_next_turn_report(s)
                log.append(("report", report))
                break
        else:
            go(s, "A")
    return log


if __name__ == "__main__":
    print("=== ① 先送りを2回続けて期限切れ ===")
    for seed in (1, 2, 3):
        s = setup(seed)
        log = choose_until_crisis_or_end(s, pick="B")
        for entry in log:
            if entry[0] == "crisis_choice":
                fall = "期限切れ — 後退" in entry[4]
                print(f"  [seed={seed}] choice=B remaining_before={entry[2]} -> timer={entry[3]}  マス後退={fall}")
            elif entry[0] == "report":
                txt = entry[1] or ""
                print(f"  [seed={seed}] 期限切れ報告: 文言あり={'期限切れとなりました' in txt}")
            else:
                print(f"  [seed={seed}] {entry}")

    print("\n=== ② 1回目で即対応して解消 ===")
    for seed in (1, 2, 3):
        s = setup(seed)
        log = choose_until_crisis_or_end(s, pick="A")
        for entry in log:
            if entry[0] == "crisis_choice":
                print(f"  [seed={seed}] choice=A remaining_before={entry[2]} -> timer={entry[3]}")
            elif entry[0] == "report":
                txt = entry[1] or ""
                print(f"  [seed={seed}] 解消報告: 文言あり={'解消されました' in txt}")
            else:
                print(f"  [seed={seed}] {entry}")

    print("\n=== ③ 1回先送り後に対応して解消 ===")
    for seed in (1, 2, 3):
        s = setup(seed)
        log = []
        # 1回目: クライシスをB（先送り）
        txt = advance_to_choice(s)
        assert s.phase == Phase.EVENT_CHOICE and getattr(s.pending_events[s.pending_event_idx], "id", "") == "cfo_successor_crisis", "1回目はクライシスのはず"
        go(s, "B")
        print(f"  [seed={seed}] 1回目B後 timer={s._timer_crisis}")
        # 残りのイベントをAで流す→次ターン
        # 2回目: クライシスをA（対応）
        log = choose_until_crisis_or_end(s, pick="A")
        for entry in log:
            if entry[0] == "crisis_choice":
                print(f"  [seed={seed}] 2回目choice=A remaining_before={entry[2]} -> timer={entry[3]}")
            elif entry[0] == "report":
                txt = entry[1] or ""
                print(f"  [seed={seed}] 解消報告: 文言あり={'解消されました' in txt}")
