import random
from typing import List, Tuple
from models.company import Company


def roll(probability: float) -> bool:
    """確率ルーレット: probabilityの確率でTrueを返す"""
    return random.random() < probability


def weighted_roll(outcomes: List[Tuple[str, float, callable]]) -> Tuple[str, any]:
    """
    重み付きルーレット
    outcomes: [(説明文, 確率weight, 効果関数), ...]
    """
    total = sum(w for _, w, _ in outcomes)
    r = random.random() * total
    cumulative = 0
    for desc, weight, effect in outcomes:
        cumulative += weight
        if r <= cumulative:
            return desc, effect
    return outcomes[-1][0], outcomes[-1][2]


def tick_bombs(company: Company) -> List[str]:
    """
    毎ターン爆弾のタイマーを進め、発動したものを処理する。
    戻り値: 発動したイベントの説明リスト
    """
    triggered = []

    # 未払残業代爆弾
    if company.flags.unpaid_overtime and company.flags.overtime_bomb_timer > 0:
        company.flags.overtime_bomb_timer -= 1
        if company.flags.overtime_bomb_timer == 0:
            damage = _trigger_labor_inspection(company)
            triggered.append(damage)

    # 反社チェック不備爆弾
    if company.flags.antisocial_vendor and company.flags.antisocial_bomb_timer > 0:
        company.flags.antisocial_bomb_timer -= 1
        if company.flags.antisocial_bomb_timer == 0:
            damage = _trigger_antisocial_scandal(company)
            triggered.append(damage)

    # 横領リスク爆弾（確率的に発動）
    if company.flags.no_job_separation and company.flags.embezzlement_risk_level >= 3:
        if roll(company.flags.embezzlement_risk_level * 0.05):
            damage = _trigger_embezzlement(company)
            triggered.append(damage)

    # 利益操作爆弾（監査で発覚）
    if company.flags.profit_manipulation and company.flags.profit_manipulation_bomb_timer > 0:
        company.flags.profit_manipulation_bomb_timer -= 1
        if company.flags.profit_manipulation_bomb_timer == 0:
            damage = _trigger_profit_manipulation_discovery(company)
            triggered.append(damage)

    return triggered


def _trigger_labor_inspection(company: Company) -> str:
    """労基署調査イベント発動"""
    damage = company.revenue.recognized * 0.3  # 30%相当の引当金
    company.cash -= damage
    company.auditor_trust = max(0, company.auditor_trust - 20)
    company.investor_trust = max(0, company.investor_trust - 15)
    company.flags.total_risk_score += 25
    company.flags.unpaid_overtime = False
    return (f"🚨 【爆弾発動】労基署の調査が入りました！\n"
            f"   未払残業代の未払いが発覚。引当金計上 ¥{damage:.1f}百万円。\n"
            f"   監査法人の信頼が低下し、上場スケジュールが見直しに。\n"
            f"   ▶ 実務解説: N-3期でコストを抑えるため残業代を払わなかった結果、\n"
            f"     直前期にこれが発覚。監査法人は引当金計上を求め、利益が大幅減少。\n"
            f"     上場申請書の利益計画も下方修正が必要となりました。")


def _trigger_antisocial_scandal(company: Company) -> str:
    """反社チェック不備スキャンダル発動"""
    company.flags.total_risk_score += 40
    company.investor_trust = max(0, company.investor_trust - 30)
    company.auditor_trust = max(0, company.auditor_trust - 25)
    company.has_underwriter = False  # 主幹事離脱
    return (f"💣 【爆弾発動】反社チェック不備が発覚！\n"
            f"   安さ重視で選んだ仕入先が反社会的勢力との関係を指摘されました。\n"
            f"   主幹事証券会社から上場延期を通告されました。\n"
            f"   ▶ 実務解説: コンプライアンスよりコスト削減を優先した結果、\n"
            f"     上場直前に取引先の反社チェックが不十分だったことが判明。\n"
            f"     証券会社の引受審査を通過できず、最低6ヶ月の延期が確定しました。")


def _trigger_embezzlement(company: Company) -> str:
    """横領事件発動"""
    stolen = company.cash * 0.1
    company.cash -= stolen
    company.flags.total_risk_score += 35
    company.internal_control_score = max(0, company.internal_control_score - 20)
    company.employee_morale = max(0, company.employee_morale - 20)
    company.flags.no_job_separation = False  # 事件後は対応を強制
    return (f"🔐 【爆弾発動】経理担当者による横領事件が発覚！\n"
            f"   出納と記帳を同一担当者に任せていた結果、横領 ¥{stolen:.1f}百万円。\n"
            f"   内部統制の重大な欠陥として、監査法人に報告義務が生じます。\n"
            f"   ▶ 実務解説: 職務分掌（出納と記帳の分離）は内部統制の基本中の基本。\n"
            f"     コスト削減で1人に集中させた結果、監査意見に影響が出るレベルの\n"
            f"     重要な欠陥と認定される可能性があります。")


def _trigger_profit_manipulation_discovery(company: Company) -> str:
    """利益操作が監査法人によって発覚"""
    manip_type = company.flags.profit_manipulation_type
    company.flags.profit_manipulation = False
    company.flags.profit_manipulation_type = ""

    # 致命的なダメージ
    company.accounting_quality = max(0, company.accounting_quality - 30)
    company.auditor_trust = max(0, company.auditor_trust - 40)
    company.investor_trust = max(0, company.investor_trust - 25)
    company.compliance_score = max(0, company.compliance_score - 20)
    company.flags.total_risk_score += 35

    if manip_type == "revenue_front":
        # 前倒し計上分を戻す
        company.revenue.recognized = max(0, company.revenue.recognized - 15.0)
        return (
            "🚨 【爆弾発動】監査法人が売上の前倒し計上を発見！\n\n"
            "   期末監査で、検収完了日と実際の納品日の不整合が発覚。\n"
            "   前倒し計上された売上¥15Mを全額取り消し。\n\n"
            "   💬 監査法人パートナー：「これは重大な虚偽表示です。\n"
            "     監査意見に影響するレベルの不正であり、\n"
            "     過去の全取引を再検証する必要があります。」\n\n"
            "   ▶ 売上-¥15M / 会計品質-30 / 監査法人信頼-40\n"
            "   ▶ 投資家信頼-25 / コンプラ-20 / リスクスコア+35\n\n"
            "   ▶ 【実務】不適切な収益認識は、上場審査における\n"
            "     最も深刻な不正類型の一つです。\n"
            "     「監査中止→上場延期1年以上」が通常のシナリオです。"
        )
    else:  # inventory_inflate
        company.revenue.recognized = max(0, company.revenue.recognized - 8.0)
        return (
            "🚨 【爆弾発動】棚卸立会で在庫の過大評価が発覚！\n\n"
            "   監査法人の棚卸立会で、帳簿上の在庫と実地棚卸に\n"
            "   重大な乖離が発見されました。\n"
            "   過大評価された在庫¥8M相当を減額修正。\n\n"
            "   💬 監査法人パートナー：「在庫の過大評価は\n"
            "     利益操作の典型的な手法です。\n"
            "     監査の基本前提である信頼関係が損なわれました。」\n\n"
            "   ▶ 利益-¥8M / 会計品質-30 / 監査法人信頼-40\n"
            "   ▶ 投資家信頼-25 / コンプラ-20 / リスクスコア+35\n\n"
            "   ▶ 【実務】棚卸資産の過大評価は、監査法人が\n"
            "     最も注意を払う項目です。\n"
            "     一度失われた監査法人の信頼は容易に回復しません。"
        )


def audit_contract_roulette(company: Company) -> Tuple[bool, str, float]:
    """
    N-2期入り時の監査契約ルーレット。
    内部管理体制スコアと証憑管理の状態により成功確率が変わる。
    N-3期の準備状況（ショートレビュー・発生主義・証憑管理）が
    監査法人の受嘱判断に直結する。
    audit_firm_tier（big/mid/small）で基本確率とペナルティが変わる。
    """
    tier = getattr(company, 'audit_firm_tier', '') or 'mid'
    # ティア別の基本確率
    tier_base = {"big": 0.70, "mid": 0.80, "small": 0.90}
    tier_labels = {"big": "大手監査法人（Big4系）", "mid": "中堅監査法人", "small": "小規模監査法人"}
    base_prob = tier_base.get(tier, 0.80)

    # N-3期の準備状況による調整（大手ほどペナルティが大きい）
    penalty_mult = {"big": 1.3, "mid": 1.0, "small": 0.7}.get(tier, 1.0)

    if company.internal_control_score < 30:
        base_prob -= 0.3 * penalty_mult
    elif company.internal_control_score < 50:
        base_prob -= 0.15 * penalty_mult

    if company.flags.no_voucher_management:
        base_prob -= 0.2 * penalty_mult
    if company.flags.cash_basis_accounting:
        base_prob -= 0.20 * penalty_mult
    if company.flags.no_inventory_count and company.business_type.value in ["製造業", "小売業"]:
        base_prob -= 0.2 * penalty_mult
    if company.accounting_quality < 30:
        base_prob -= 0.1 * penalty_mult
    if not company.flags.short_review_done:
        base_prob -= 0.15 * penalty_mult
    if not company.has_cfo:
        base_prob -= 0.10 * penalty_mult

    base_prob = max(0.05, min(0.95, base_prob))

    # 拒絶理由を事前に生成（成否に関わらず使用）
    reasons = []
    if company.flags.cash_basis_accounting:
        reasons.append("現金主義会計が未解消（発生主義移行が完了していない）")
    if company.flags.no_voucher_management:
        reasons.append("証憑管理体制が未整備（監査を受け入れられる状態にない）")
    if not company.flags.short_review_done:
        reasons.append("ショートレビュー未実施（準備状況が不明確）")
    if not company.has_cfo:
        reasons.append("常勤CFO不在（財務管理体制の責任者がいない）")
    if company.internal_control_score < 30:
        reasons.append("内部管理体制スコアが低水準")
    if company.accounting_quality < 30:
        reasons.append("会計品質が低水準（帳簿の正確性に疑義）")

    firm_label = tier_labels.get(tier, "監査法人")
    success = roll(base_prob)

    if success:
        company.audit_firm_agreed = True
        company.auditor_trust += 10
        # 大手法人なら追加の信頼ボーナス
        if tier == "big":
            company.auditor_trust = min(100, company.auditor_trust + 5)
        if company.flags.short_review_done:
            sr_note = "N-3期のショートレビューで事前に課題を把握・改善していたことが評価されました。"
        else:
            sr_note = "ただし、ショートレビュー未実施のため、一部の潜在リスクが未把握のまま監査が始まります。"
        msg = (f"✅ {firm_label}から、株主総会での会計監査人選任を条件に\n"
               f"   準金商法監査契約の内諾を得ました！（成功確率{base_prob:.0%}）\n"
               f"   ▶ 次回の定時株主総会で会計監査人として正式選任された後、\n"
               f"     N-2期（直前々期）からの監査がスタートします。\n"
               f"   ▶ 【実務】IPO準備の「監査難民」問題：\n"
               f"     監査法人の人手不足により、IPO会社への新規受嘱を断るケースが増えています。\n"
               f"     N-3期中から監査法人との関係構築・ショートレビュー実施が早期契約の鍵です。\n"
               f"   ▶ 上場申請には過去2期分（N-2・N-1期）の無限定適正意見が必要です。\n"
               f"   ▶ {sr_note}")
    else:
        company.flags.audit_contract_rejected = True
        company.flags.total_risk_score += 25
        reason_str = "\n   ・".join(reasons) if reasons else "内部管理体制の総合的な不備"
        msg = (f"❌ {firm_label}に受嘱を拒絶されました！（成功確率{base_prob:.0%}）\n\n"
               f"   【拒絶理由】\n   ・{reason_str}\n\n"
               f"   ▶ 【実務】「IPO監査難民」の現実：\n"
               f"     監査法人はIPO会社の受嘱審査で内部管理体制・決算品質を厳格に確認します。\n"
               f"     N-3期のショートレビューを実施せず、指摘事項を改善しないまま\n"
               f"     N-2期を迎えると、監査法人に受嘱を断られるリスクが現実化します。\n"
               f"     一度断られると別の監査法人への打診が必要ですが、\n"
               f"     「他社に断られた企業」というシグナルが更なる拒絶を招きます。\n"
               f"   ▶ 上場スケジュールの見直しが不可避です。リスクスコア+25")

    return success, msg, base_prob
