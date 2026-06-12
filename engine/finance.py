from models.company import Company, BusinessType, Revenue


# 業種別パラメータ
BUSINESS_PARAMS = {
    BusinessType.SAAS: {
        "initial_cash": 800.0,
        "initial_revenue": 30.0,
        "growth_rate": 0.15,       # 四半期成長率
        "burn_rate": 80.0,
        "revenue_deferred_ratio": 0.4,  # 収益認識の繰延割合（SaaSは前受が多い）
        "description": "SaaS（月次サブスク収益、高成長・赤字体質）",
    },
    BusinessType.FINTECH: {
        "initial_cash": 1200.0,
        "initial_revenue": 50.0,
        "growth_rate": 0.12,
        "burn_rate": 100.0,
        "revenue_deferred_ratio": 0.2,
        "description": "FinTech（決済・融資、規制対応コスト高）",
    },
    BusinessType.MANUFACTURING: {
        "initial_cash": 600.0,
        "initial_revenue": 80.0,
        "growth_rate": 0.05,
        "burn_rate": 60.0,
        "revenue_deferred_ratio": 0.1,  # 検収基準での繰延
        "description": "製造業（棚卸資産が重要、原価計算が必須）",
    },
    BusinessType.RETAIL: {
        "initial_cash": 400.0,
        "initial_revenue": 120.0,
        "growth_rate": 0.06,
        "burn_rate": 100.0,
        "revenue_deferred_ratio": 0.05,
        "description": "小売業（薄利多売、在庫管理が生命線）",
    },
}


def initialize_company(company: Company):
    """業種に応じた初期パラメータ設定"""
    params = BUSINESS_PARAMS[company.business_type]
    company.cash = params["initial_cash"]
    company.quarterly_burn = params["burn_rate"]
    company.revenue.recognized = params["initial_revenue"]
    company.revenue.growth_rate = params["growth_rate"]
    company.revenue.deferred = params["initial_revenue"] * params["revenue_deferred_ratio"]
    company.market_cap_million = company.revenue.recognized * 20  # PER20倍

    # 初期キャップテーブル
    company.cap_table.add_shareholder("創業者A", 6_000_000, is_founder=True)
    company.cap_table.add_shareholder("創業者B", 2_000_000, is_founder=True)
    company.cap_table.add_shareholder("エンジェル投資家", 1_000_000)
    company.cap_table.total_shares = 9_000_000

    # 業種別フラグの初期状態
    if company.business_type == BusinessType.MANUFACTURING:
        company.flags.no_inventory_count = True  # 製造業は棚卸が課題になりがち
    if company.business_type in [BusinessType.SAAS, BusinessType.FINTECH]:
        company.flags.cash_basis_accounting = True  # SaaS/FintechはSaaS収益認識が複雑


def market_multiplier(company: Company) -> float:
    """📈 市況指数(0〜100)による時価総額の乗数。55でほぼ等倍。"""
    idx = getattr(company, "market_index", 55.0)
    return 0.70 + (idx / 100.0) * 0.60


def update_market_index(company: Company):
    """📈 市況のランダムウォーク（モメンタム付き：上げ/下げが続きやすい）"""
    import random
    idx = getattr(company, "market_index", 55.0)
    mom = getattr(company, "market_momentum", 0.0)
    delta = mom * 0.45 + random.uniform(-11.0, 11.0)
    company.market_momentum = delta
    company.market_index = min(95.0, max(5.0, idx + delta))


def effective_growth_rate(company: Company) -> float:
    """⚔🛡 トレードオフ修正後の実効成長率（基礎成長率＋恒久増減＋一時増減）"""
    g = company.revenue.growth_rate
    g += getattr(company, "growth_perm_delta", 0.0)
    for mod in getattr(company, "growth_temp_mods", []):
        g += mod[0]
    return min(0.40, max(-0.05, g))


def _tick_growth_mods(company: Company):
    """一時的な成長率修正の残期間を1Q減らし、切れたものを除去"""
    mods = getattr(company, "growth_temp_mods", [])
    for mod in mods:
        mod[1] -= 1
    company.growth_temp_mods = [m for m in mods if m[1] > 0]


def advance_quarter_financials(company: Company, n_period: int, quarter: int):
    """四半期財務処理"""
    params = BUSINESS_PARAMS[company.business_type]

    # 📈 市況の変動（時価総額評価に影響）
    update_market_index(company)

    # 売上成長（⚔🛡 トレードオフ修正を反映）
    growth = effective_growth_rate(company)
    # 内部統制スコアが低いと成長にペナルティ（不正確な数字）
    if company.accounting_quality < 30:
        growth *= 0.7

    company.revenue.recognized *= (1 + growth)
    _tick_growth_mods(company)

    # 繰延収益の認識（SaaSの前受など）
    deferred_recognition = company.revenue.deferred * 0.25
    company.revenue.recognized += deferred_recognition
    company.revenue.deferred -= deferred_recognition

    # キャッシュフロー計算
    net_cash_flow = company.revenue.recognized - company.quarterly_burn

    # コンプライアンス・管理体制のコスト
    compliance_cost = (100 - company.compliance_score) * 0.5  # 体制が整っていないほどコスト高
    net_cash_flow -= compliance_cost

    company.cash += net_cash_flow

    # 時価総額更新（📈 市況乗数を反映：弱気で割安評価、強気でプレミアム）
    new_mktcap = company.revenue.recognized * _get_per_multiple(company) * market_multiplier(company)
    # 🏁 ライバルに先に上場された場合：同業IPOの新鮮味低下で評価ディスカウント
    #   （-15%。ただし自社も山頂目前まで迫っていた場合は -7% に軽減）
    if getattr(company, "rival_listed_first", False):
        new_mktcap *= getattr(company, "rival_discount", 0.85)
    if n_period == -3 and quarter == 1:
        # N-3期Q1は開始直後のため、PER倍率差による過大変動を5%以内に抑制する
        old_mktcap = company.market_cap_million
        delta_limit = old_mktcap * 0.05
        new_mktcap = max(old_mktcap - delta_limit, min(old_mktcap + delta_limit, new_mktcap))
    company.market_cap_million = new_mktcap

    # スコアの下限・上限ガード
    company.internal_control_score = min(100, max(0, company.internal_control_score))
    company.compliance_score       = min(100, max(0, company.compliance_score))
    company.accounting_quality     = min(100, max(0, company.accounting_quality))
    company.governance_score       = min(100, max(0, company.governance_score))
    company.auditor_trust          = min(100, max(0, company.auditor_trust))
    company.investor_trust         = min(100, max(0, company.investor_trust))
    company.employee_morale        = min(100, max(0, company.employee_morale))

    # 横領リスクの時間経過での上昇
    if company.flags.no_job_separation:
        company.flags.embezzlement_risk_level = min(5, company.flags.embezzlement_risk_level + 1)


def _get_per_multiple(company: Company) -> float:
    """業種・成長率に応じたPER倍率"""
    base = {
        BusinessType.SAAS: 30.0,
        BusinessType.FINTECH: 25.0,
        BusinessType.MANUFACTURING: 15.0,
        BusinessType.RETAIL: 12.0,
    }[company.business_type]
    # プライム市場：製造業・小売業は大手企業として高PER補正
    # （成熟した大手企業は安定収益が評価され、スタートアップより高いPER評価を受ける）
    if getattr(company, 'target_market_code', '') == 'prime':
        prime_per_override = {
            BusinessType.MANUFACTURING: 25.0,  # 大手製造業：安定収益・ブランド力で15→25
            BusinessType.RETAIL:        18.0,  # 全国チェーン：規模の経済で12→18
        }
        base = prime_per_override.get(company.business_type, base)
    # ガバナンス・コンプライアンスが低いとディスカウント
    discount = (100 - company.governance_score) / 200
    return base * (1 - discount)


def raise_funding(company: Company, round_name: str, amount: float, pre_money_valuation: float,
                  investor_name: str, shareholder_boost: int = 50) -> str:
    """資金調達とキャップテーブル更新
    shareholder_boost: このラウンドで追加される株主数（機関投資家＋個人投資家の合計）
    """
    new_shares = int(company.cap_table.total_shares * amount / pre_money_valuation)
    company.cap_table.add_shareholder(investor_name, new_shares, is_vc=True)
    company.cash += amount
    company.shareholder_count += shareholder_boost

    founder_ratio = company.cap_table.founder_ratio()
    return (f"{round_name}ラウンド調達完了: ¥{amount:.0f}百万円 "
            f"(Pre-money: ¥{pre_money_valuation:.0f}百万円) | "
            f"創業者持分: {founder_ratio:.1%} | 株主数 +{shareholder_boost}名")


def check_cash_crisis(company: Company) -> bool:
    """資金ショートチェック"""
    return company.cash < 0
