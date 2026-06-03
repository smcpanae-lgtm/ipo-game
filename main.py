"""
The IPO Path: 栄光への決断
IPO準備学習シミュレーションゲーム
"""
import sys
import os

# パスを通す
sys.path.insert(0, os.path.dirname(__file__))

from models.company import Company, BusinessType
from engine.timeline import Timeline, N_MINUS_2, N_MINUS_1, N_PERIOD
from engine.finance import initialize_company, advance_quarter_financials, check_cash_crisis
from engine.roulette import tick_bombs, audit_contract_roulette
from scenario.ipo_knowledge import get_available_events, shareholder_meeting_event, ALL_EVENTS
from ui.display import (
    console,
    render_title,
    render_business_type_selection,
    render_company_name_input,
    render_dashboard,
    render_event,
    render_choices,
    render_result,
    render_bomb_trigger,
    render_audit_contract_result,
    render_shareholder_meeting,
    render_period_transition,
    render_tse_examination,
    render_ending,
    press_enter_to_continue,
)


# ──────────────────────────────────────────
# ゲーム初期化
# ──────────────────────────────────────────
def setup_game() -> tuple[Company, Timeline]:
    """タイトル画面 → 業種選択 → 会社名入力 → 初期化"""
    render_title()
    press_enter_to_continue("ゲームを開始する")

    # 業種選択
    btype_index = render_business_type_selection()
    btype = list(BusinessType)[btype_index]

    # 会社名入力
    company_name = render_company_name_input()

    # 初期フラグのランダム設定
    company = Company(name=company_name, business_type=btype)
    initialize_company(company)

    # 初期状態の整備（未整備フラグを設定）
    company.flags.no_voucher_management = True
    company.flags.no_job_separation = True
    company.flags.no_outside_director = True
    company.flags.no_related_party_review = True
    company.flags.no_compliance_system = True

    # 業種に応じた主幹事証券会社の初期設定（N-3期はまだ未選定）
    company.has_underwriter = False

    timeline = Timeline()
    return company, timeline


# ──────────────────────────────────────────
# 期の移行処理
# ──────────────────────────────────────────
def handle_period_transition(company: Company, timeline: Timeline, events: dict):
    """N-2/N-1/N期への移行時の特別処理"""

    # ─── 定時株主総会（Q4終了時） ───
    if events.get("year_end"):
        result = shareholder_meeting_event(company, timeline.n_period)
        render_shareholder_meeting(result, timeline.n_period)
        press_enter_to_continue()

    # ─── N-2期に入る：監査契約ルーレット ───
    if events.get("enter_n2"):
        render_period_transition(-3, -2)

        console.print(
            "\n[bold yellow]N-2期（直前々期）に入りました。\n"
            "監査法人との「準金商法監査契約」を結ぶ時期です。\n"
            "あなたの内部管理体制が問われます……[/bold yellow]\n"
        )
        press_enter_to_continue("監査契約ルーレットへ")

        success, msg = audit_contract_roulette(company)
        render_audit_contract_result(success, msg)

        if not success:
            # 代替対応の選択
            from models.events import Choice
            alt_choices = [
                Choice(
                    label="A. 急いで体制整備して別の監査法人に再チャレンジする（¥20百万円）",
                    description="コストはかかるが上場スケジュールを維持しようとする",
                    immediate_effect=lambda c: _emergency_internal_control(c),
                ),
                Choice(
                    label="B. 上場スケジュールを1年延期して体制整備に専念する",
                    description="確実な上場のため、N-3期をやり直す覚悟で",
                    immediate_effect=lambda c: _postpone_ipo(c, timeline),
                ),
            ]
            render_event(
                "監査契約拒絶後の対応",
                "監査法人に受嘱を断られました。どう対処しますか？"
            )
            idx = render_choices(alt_choices)
            result_msg = alt_choices[idx].immediate_effect(company)
            is_good = idx == 0
            render_result(result_msg, is_good)

        press_enter_to_continue()

    # ─── N-1期に入る ───
    if events.get("enter_n1"):
        render_period_transition(-2, -1)
        press_enter_to_continue()

    # ─── N期（申請期）に入る ───
    if events.get("enter_n"):
        render_period_transition(-1, 0)
        # 主幹事証券会社の自動選定（未選定の場合）
        if not company.has_underwriter:
            if company.investor_trust >= 50 and company.compliance_score >= 40:
                company.has_underwriter = True
                console.print(
                    "[bright_green]✅ 主幹事証券会社が決定しました！[/bright_green]\n"
                    "   引受審査を通過し、上場申請に向けた体制が整いました。"
                )
            else:
                console.print(
                    "[bright_red]⚠️  主幹事証券会社が決まっていません。[/bright_red]\n"
                    "   投資家信頼またはコンプライアンス体制の不備が原因です。"
                )
        press_enter_to_continue()


def _emergency_internal_control(company: Company) -> str:
    company.cash -= 20.0
    company.internal_control_score += 20
    company.accounting_quality += 15
    # 再チャレンジ（確率50%）
    from engine.roulette import roll
    if roll(0.5):
        company.has_audit_contract = True
        return ("✅ 緊急体制整備の結果、別の監査法人と契約できました！\n"
                f"   ¥20百万円のコストで上場スケジュールを維持。\n"
                f"   内部統制スコア+20 / 会計品質+15")
    else:
        company.flags.total_risk_score += 15
        return ("❌ 再チャレンジしましたが、監査法人に受嘱を断られました。\n"
                f"   上場スケジュールの大幅な見直しが必要です。\n"
                f"   ¥20百万円のコスト計上 / リスクスコア+15")


def _postpone_ipo(company: Company, timeline: Timeline) -> str:
    company.internal_control_score += 30
    company.accounting_quality += 25
    company.flags.total_risk_score = max(0, company.flags.total_risk_score - 10)
    return ("📅 上場を1年延期して体制整備に専念します。\n"
            f"   じっくり整備することで、来期の監査契約成功確率が大幅に上がります。\n"
            f"   内部統制スコア+30 / 会計品質+25 / リスクスコア-10")


# ──────────────────────────────────────────
# メインゲームループ
# ──────────────────────────────────────────
def game_loop(company: Company, timeline: Timeline):
    """メインゲームループ"""

    while True:
        # ─── ダッシュボード表示 ───
        render_dashboard(company, timeline)

        # ─── 資金ショートチェック ───
        if check_cash_crisis(company):
            press_enter_to_continue("結末を確認")
            render_ending(company, "bankruptcy", [])
            return

        # ─── 解任チェック ───
        if company.investor_trust <= 5 or company.auditor_trust <= 5:
            press_enter_to_continue("結末を確認")
            render_ending(company, "dismissed", [])
            return

        # ─── N期Q4 = 上場審査（ゲームクライマックス） ───
        if timeline.n_period == N_PERIOD and timeline.quarter == 4:
            press_enter_to_continue("東証上場審査へ")
            tse_result = render_tse_examination(company)

            if tse_result["passed"]:
                render_ending(company, "success", [])
            else:
                # 問題が致命的かどうかで分岐
                fatal = any("反社" in i or "監査契約" in i for i in tse_result["issues"])
                if fatal:
                    render_ending(company, "dismissed", tse_result["issues"])
                else:
                    render_ending(company, "delay", tse_result["issues"])
            return

        # ─── イベント発生 ───
        available_events = get_available_events(company, timeline.n_period)
        for event in available_events:
            render_event(event.title, event.description)
            idx = render_choices(event.choices)
            choice = event.choices[idx]

            # 即時効果の適用
            result_msg = choice.immediate_effect(company)

            # 将来フラグの設定
            if choice.future_flag_setter:
                choice.future_flag_setter(company)

            # 結果の判定（コストが含まれているか等で判定）
            is_good = not any(kw in result_msg for kw in ["⚠️", "❗", "❌", "💰（短期のみ）"])
            render_result(result_msg, is_good)
            event.fired = True
            company.add_event_log(f"[{timeline.full_label()}] {event.title}: {choice.label[:30]}")

            press_enter_to_continue()

        # ─── 財務進行 ───
        advance_quarter_financials(company, timeline.n_period, timeline.quarter)

        # ─── 爆弾タイマー処理 ───
        triggered = tick_bombs(company)
        for bomb_msg in triggered:
            render_bomb_trigger(bomb_msg)
            company.add_event_log(f"[{timeline.full_label()}] 爆弾発動!")
            press_enter_to_continue()

        # ─── タイムライン進行 ───
        period_events = timeline.advance()

        # ─── 期の移行処理 ───
        handle_period_transition(company, timeline, period_events)


# ──────────────────────────────────────────
# エントリーポイント
# ──────────────────────────────────────────
def main():
    try:
        company, timeline = setup_game()
        game_loop(company, timeline)
    except KeyboardInterrupt:
        console.print("\n\n[dim]ゲームを終了します。[/dim]")
        sys.exit(0)


if __name__ == "__main__":
    main()
