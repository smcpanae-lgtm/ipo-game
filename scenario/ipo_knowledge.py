"""
IPO実務イベントライブラリ
上場準備に関わる意思決定イベントの定義
"""
import copy
import random
from models.company import Company
from models.events import Choice, GameEvent
from engine.finance import raise_funding


# ─────────────────────────────────────────────
# ⚔🛡 攻守トレードオフ ヘルパー（第1弾）
#   守りの選択 → 成長率ダウン（現場負荷・固定費増）
#   攻めの選択 → 成長率アップ＋リスク
# ─────────────────────────────────────────────
def _growth_tax(c: Company, pt: float, quarters: int = 0, mark: bool = True) -> str:
    """管理対応の現場負荷：四半期成長率を pt ポイント引き下げる（quarters=0 で恒久）。
    mark=True（既定）のとき「🏗 現場負荷」としてメーターに数える。
    成長ブレーキ（コスト優先選択など管理対応でないもの）は mark=False で除外する。"""
    if quarters <= 0:
        c.growth_perm_delta -= pt / 100.0
        dur = "恒久"
    else:
        c.growth_temp_mods.append([-pt / 100.0, quarters])
        dur = f"{quarters}Q間"
    if mark:
        c.defense_score += 1
        return f"🏗 現場負荷: 成長率-{pt:g}pt（{dur}）— 現場リソースを管理対応に充当"
    return f"📉 成長ブレーキ: 成長率-{pt:g}pt（{dur}）"


def _growth_boost(c: Company, pt: float, quarters: int = 0, mark: bool = False) -> str:
    """成長率を pt ポイント引き上げる（quarters=0 で恒久）。
    mark=True のときだけ「🚀 事業投資」としてメーターに数える。
    （手抜き・先送りによる一時的な伸びは数えない＝戦略的な成長投資のみカウント）"""
    if quarters <= 0:
        c.growth_perm_delta += pt / 100.0
        dur = "恒久"
    else:
        c.growth_temp_mods.append([pt / 100.0, quarters])
        dur = f"{quarters}Q間"
    if mark:
        c.offense_score += 1
    return f"🚀 成長への追い風: 成長率+{pt:g}pt（{dur}）"


# ─────────────────────────────────────────────
# イベント1: ショートレビュー
# ─────────────────────────────────────────────
def _short_review_full(company: Company) -> str:
    company.flags.short_review_done = True
    company.accounting_quality += 15
    company.internal_control_score += 10
    _tax_msg = _growth_tax(company, 2, 1)
    risks = company.flags.visible_bombs()
    if risks:
        risk_str = "\n   ".join(risks)
        return (f"🔍 ショートレビュー（全範囲）を実施しました。\n"
                f"   以下の潜在リスク（爆弾）が発見されました:\n   {risk_str}\n"
                f"   ▶ N-2期期首から改善に着手することで上場への道が開けます！\n"
                f"   ▶ 【実務】ショートレビューでの指摘は「通常あるもの」です。\n"
                f"     指摘を受けない企業はほとんど存在しません。\n"
                f"     重要なのは指摘内容をN-2期の監査開始前に改善しきることです。\n"
                f"     これを怠ると、N-2期の監査意見が「限定付適正意見」となるリスクがあります。\n"
                f"   会計品質+15 / 内部統制スコア+10\n   {_tax_msg}")
    return ("🔍 ショートレビューを実施しました。\n"
            f"   重大なリスクは発見されませんでした。準備が進んでいます！\n"
            f"   ▶ 【実務】ショートレビューでの指摘は「通常あるもの」です。\n"
            f"     指摘を受けない企業はほとんど存在しません。\n"
            f"     N-3期中にショートレビューを実施し、N-2期首から改善に着手する\n"
            f"     ことが上場審査でも高く評価されます。\n"
            f"   会計品質+15 / 内部統制スコア+10\n   {_tax_msg}")


def _short_review_limited(company: Company) -> str:
    company.flags.short_review_done = True
    company.accounting_quality += 5
    company.flags.total_risk_score += 8
    return ("🔍 会計面のみのショートレビューを実施しました。\n"
            f"   範囲が限定的なため、内部統制・労務・ガバナンス面のリスクは未確認です。\n"
            f"   ▶ 【注意】N-2期の監査では全範囲が審査対象となります。\n"
            f"     会計以外のリスクが後から発覚すると、N-2期首からの対応が間に合わず\n"
            f"     「限定付適正意見」リスクが高まります。\n"
            f"   会計品質+5のみ / リスクスコア+8（未発見リスク残存）")


def _skip_short_review(company: Company) -> str:
    company.flags.total_risk_score += 20
    _boost_msg = _growth_boost(company, 1, 1)
    return (f"⏭️  ショートレビューをスキップしました。\n"
            f"   {_boost_msg}\n"
            f"   ▶ 【重大警告】N-2期の監査は、ショートレビューの結果を踏まえた\n"
            f"     「改善後の状態」を前提に計画されます。\n"
            f"     N-3期にショートレビューを実施しないと、N-2期期首の監査開始時に\n"
            f"     初めて問題が発覚し、改善する時間が失われます。\n"
            f"     その結果、監査意見が「限定付適正意見」となり上場スケジュールが\n"
            f"     大幅に遅延する最大リスクになります。\n"
            f"   リスクスコア+20（限定付適正意見リスク）")


EVENT_SHORT_REVIEW = GameEvent(
    id="short_review",
    title="ショートレビューの実施（N-3期 最重要）",
    description=(
        "ショートレビュー契約を締結した監査法人から連絡がありました。\n\n"
        "「社長、IPO準備のスタートとしてショートレビュー（予備的調査）の\n"
        "実施をお勧めします。財務・内部統制・労務・ガバナンスの全体像を\n"
        "N-3期のうちに把握し、N-2期（直前々期）の監査開始前に改善しておくことが\n"
        "IPO成功の鉄則です。\n\n"
        "なお、ショートレビューでの指摘は『通常あるもの』です。\n"
        "指摘を受けない企業はほとんど存在しません。重要なのはN-2期期首から\n"
        "改善に着手することです。これを怠ると監査意見が\n"
        "『限定付適正意見』となり、上場スケジュールが崩壊します。」\n\n"
        "【ポイント】ショートレビューはN-3期の必須イベント。指摘 → N-2期首から改善がIPOの王道です。"
    ),
    choices=[
        Choice(
            label="A. 全範囲のショートレビューを依頼する（¥5百万円）",
            description="財務・内部統制・労務・コンプライアンス・ガバナンス全てを調査",
            immediate_effect=lambda c: (_apply_cost(c, 5.0), _short_review_full(c))[1],
            profit_hint="",
            risk_hint="コスト¥5M。しかし全リスクが可視化され、N-2期対応を最大化できる",
        ),
        Choice(
            label="B. 会計面のみの簡易レビューにする（¥2百万円）",
            description="範囲を絞ってコスト削減。ただし内部統制・労務面は未確認",
            immediate_effect=lambda c: (_apply_cost(c, 2.0), _short_review_limited(c))[1],
            profit_hint="コスト半減",
            risk_hint="会計以外のリスクが後から発覚 → 限定付適正意見リスク+8",
        ),
        Choice(
            label="C. 今はスキップする（費用ゼロ）",
            description="まだ早いとして先送り。ただしN-2期開始時に初めて問題発覚するリスク大",
            immediate_effect=_skip_short_review,
            profit_hint="コストゼロ",
            risk_hint="N-2期での限定付適正意見リスク → 上場スケジュール崩壊の最大要因",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント2: 証憑管理
# ─────────────────────────────────────────────
def _fix_voucher_management(company: Company) -> str:
    company.flags.no_voucher_management = False
    company.accounting_quality += 20
    company.internal_control_score += 10
    _tax_msg = _growth_tax(company, 1, 2)
    return ("📁 証憑管理システムを整備しました。\n"
            f"   伝票番号と証憑書類の紐付けルールを全社展開。\n"
            f"   会計品質+20 / 内部統制スコア+10\n   {_tax_msg}\n"
            f"   ▶ 実務: 監査法人が後から会計処理の妥当性を検証できる状態が必要です。")


def _partial_voucher_fix(company: Company) -> str:
    company.flags.no_voucher_management = True  # 完全には解決していない
    company.accounting_quality += 8
    return ("📁 一部の部門で証憑管理を改善しました（完全整備には至らず）。\n"
            f"   会計品質+8（監査法人からの指摘は残る可能性あり）")


def _ignore_voucher(company: Company) -> str:
    company.flags.no_voucher_management = True
    company.flags.total_risk_score += 10
    return ("❗ 証憑管理の整備を先送りにしました。\n"
            f"   将来の監査で「監査受入不可」と判断されるリスクが高まります。\n"
            f"   リスクスコア+10")


EVENT_VOUCHER_MANAGEMENT = GameEvent(
    id="voucher_management",
    title="証憑管理の整備",
    description=(
        "経理担当者から報告がありました。「現在、各営業部門がバラバラに請求書を保管しており、\n"
        "口頭だけで取引が成立しているケースも多数あります。監査が入ったら問題になりそうです。」\n"
        "【ポイント】証憑書類の整理は監査受入体制の最低条件です。"
    ),
    choices=[
        Choice(
            label="A. 証憑管理ルールを全社展開し、電子保管システムを導入する（¥8百万円）",
            description="伝票番号による証憑紐付け、全社ルール統一",
            immediate_effect=lambda c: (_apply_cost(c, 8.0), _fix_voucher_management(c))[1],
            risk_hint="初期コスト大",
        ),
        Choice(
            label="B. とりあえず本社部門だけ整備する（¥3百万円）",
            description="部分対応でコスト削減",
            immediate_effect=lambda c: (_apply_cost(c, 3.0), _partial_voucher_fix(c))[1],
            profit_hint="コスト削減",
            risk_hint="営業部門の証憑は未整備のまま",
        ),
        Choice(
            label="C. 現行通りで様子を見る（費用ゼロ）",
            description="問題が起きてから対処する方針",
            immediate_effect=_ignore_voucher,
            profit_hint="即時コストゼロ",
            risk_hint="監査受入不可リスクが高まる",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=True,
    trigger_condition=lambda c: c.flags.no_voucher_management,
)


# ─────────────────────────────────────────────
# イベント3: 発生主義・収益認識# ─────────────────────────────────────────────
def _adopt_accrual_accounting(company: Company) -> str:
    company.flags.cash_basis_accounting = False
    company.accounting_quality += 25
    # 収益認識基準適用により一時的に売上が調整される
    revenue_impact = company.revenue.recognized * 0.1
    company.revenue.deferred += revenue_impact
    company.revenue.recognized -= revenue_impact
    _tax_msg = _growth_tax(company, 1)      # 検収基準化で計上が保守化（恒久）
    return (f"📊 発生主義・収益認識会計基準への完全移行が完了しました。\n"
            f"   一時的に売上計上タイミングが変わり、¥{revenue_impact:.1f}百万円が繰延収益へ。\n"
            f"   会計品質+25\n   {_tax_msg}\n"
            f"   ▶ 【実務】5ステップモデル（契約識別→履行義務識別→取引価格算定\n"
            f"     →配分→収益認識）に従い、出荷基準→検収基準・進捗基準へ切り替え完了。")


def _partial_accrual(company: Company) -> str:
    company.flags.cash_basis_accounting = True  # まだ完全移行できていない
    company.accounting_quality += 10
    company.flags.total_risk_score += 8
    return ("📊 主要取引のみ発生主義に移行しました（完全移行は未達）。\n"
            f"   会計品質+10 / リスクスコア+8\n"
            f"   ▶ 【注意】月次決算の早期化（翌月10日目処）や、\n"
            f"     賞与引当金・退職給付債務の月割計上が未整備のため\n"
            f"     監査で残った現金主義項目への指摘リスクが残ります。\n"
            f"     取締役会への予実報告体制も再整備が必要です。")


def _keep_cash_basis(company: Company) -> str:
    company.flags.cash_basis_accounting = True
    company.flags.total_risk_score += 20
    # 一時的な利益増（費用計上を後回しにできる）
    company.revenue.recognized *= 1.05
    _boost_msg = _growth_boost(company, 1, 1)
    return ("💰 現金主義を継続。費用計上を後回しにできるため短期利益が増加。\n"
            f"   売上+5%（一時的） / {_boost_msg}\n"
            f"   ▶ 【重大警告】N-2期の監査開始時に現金主義が残っていると\n"
            f"     「限定付適正意見」リスクが現実化します。\n"
            f"     月次決算体制・引当金月割計上・取締役会への予実報告も\n"
            f"     すべて未整備のまま残り、N-2期の監査対応が困難になります。\n"
            f"   リスクスコア+20（限定付適正意見リスク大）")


EVENT_ACCRUAL_ACCOUNTING = GameEvent(
    id="accrual_accounting",
    title="発生主義・収益認識基準への移行（月次決算早期化）",
    description=(
        "CFOから報告がありました。\n\n"
        "「社長、現在の会計処理は現金主義ベースです。N-2期の監査開始前に\n"
        "以下の整備を完了させる必要があります。\n\n"
        "①収益認識：出荷基準→検収基準・進捗基準へ（5ステップモデル適用）\n"
        "②月次決算の早期化：翌月10日目処での締め・集計体制\n"
        "③引当金の月割計上：減価償却費・賞与引当金・退職給付等\n"
        "④取締役会への予算実績差異分析資料の提出体制\n\n"
        "上場審査では予実の乖離率と乖離原因の説明が確認されます。\n"
        "計画と実績の差異が大きい場合、事業計画の信頼性が問われます。」\n\n"
        "【ポイント】発生主義移行はN-2期監査開始前の必須事項。翌月10日月次決算が目標です。"
    ),
    choices=[
        Choice(
            label="A. 完全移行する（収益認識・月次早期化・引当金月割・予実体制すべて整備）（¥10M）",
            description="システム改修含む全整備。N-2期監査を万全の状態で迎える",
            immediate_effect=lambda c: (_apply_cost(c, 10.0), _adopt_accrual_accounting(c))[1],
            risk_hint="コスト大だが根本解決。N-2期の限定付適正意見リスクを排除",
        ),
        Choice(
            label="B. 主要取引のみ移行する（月次早期化・引当金月割は後回し）（¥4M）",
            description="収益認識の主要部分のみ対応。月次体制は次期に持ち越し",
            immediate_effect=lambda c: (_apply_cost(c, 4.0), _partial_accrual(c))[1],
            profit_hint="コスト抑制",
            risk_hint="月次・引当金・予実体制未整備 → 監査指摘リスク+8",
        ),
        Choice(
            label="C. 現金主義を継続する（今期はコスト削減優先）",
            description="問題を先送り。N-2期監査開始時に初めて発覚するリスク",
            immediate_effect=_keep_cash_basis,
            profit_hint="今期利益+5%",
            risk_hint="N-2期の限定付適正意見リスク → 上場スケジュール崩壊",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=True,
    trigger_condition=lambda c: c.flags.cash_basis_accounting,
)


# ─────────────────────────────────────────────
# イベント4: 棚卸資産管理
# ─────────────────────────────────────────────
def _implement_inventory_system(company: Company) -> str:
    company.flags.no_inventory_count = False
    company.flags.no_cost_accounting = False
    company.internal_control_score += 15
    company.accounting_quality += 15
    company.quarterly_burn += 2.0   # 在庫管理の運用コスト
    _tax_msg = _growth_tax(company, 1, 1)
    return ("📦 棚卸資産管理システムと原価計算体制を整備しました。\n"
            f"   棚卸要領・受払記録マニュアル・監査法人の立会体制をフルセット整備。\n"
            f"   内部統制スコア+15 / 会計品質+15 / 毎Q費用+¥2M\n   {_tax_msg}\n"
            f"   ▶ 【実務①：棚卸立会のタイミング】\n"
            f"     N-2期から監査が始まるため、N-2期の期末棚卸から監査法人が立ち会います。\n"
            f"     N-3期中に棚卸管理体制を整備しておかないと、\n"
            f"     N-2期期末の立会時に「監査範囲の制約」となり監査意見が表明できません。\n"
            f"     これは『限定付適正意見』に直結する最重大リスクです。\n"
            f"   ▶ 【実務②：原価計算体制（製造業・小売業）】\n"
            f"     棚卸資産の評価には正確な原価計算が必要です。\n"
            f"     原価計算体制が未整備だと、製造原価の検証が不可能となり\n"
            f"     売上原価・棚卸資産評価額の信頼性が問われます。")


def _manual_inventory_only(company: Company) -> str:
    company.flags.no_inventory_count = True
    company.accounting_quality += 5
    company.flags.total_risk_score += 10
    return ("📦 手動の在庫カウントを開始しましたが、受払記録・原価計算体制は未整備。\n"
            f"   会計品質+5 / リスクスコア+10\n"
            f"   ▶ 【注意】受払記録がないと、N-2期期末の監査法人棚卸立会で\n"
            f"     「帳簿残高の合理性が検証できない」と判断される可能性があります。\n"
            f"     原価計算体制の未整備は製造業では致命的な監査指摘事項になります。")


def _skip_inventory(company: Company) -> str:
    company.flags.no_inventory_count = True
    company.flags.total_risk_score += 25
    return ("❗ 棚卸整備を先送りにしました。\n"
            f"   ▶ 【重大警告】N-2期期末の棚卸から監査法人が立ち会います。\n"
            f"     N-3期中に整備しないと、N-2期末立会時に：\n"
            f"     ①棚卸要領・受払記録の欠如 → 監査範囲の制約\n"
            f"     ②立会体制の未整備 → 監査法人が立会を実施できない\n"
            f"     ③結果：『限定付適正意見』→ 上場申請書類として使用不可\n"
            f"     監査法人との契約前に棚卸立会体制が必須であることを\n"
            f"     N-2期入りルーレットでも厳しく審査されます。\n"
            f"   リスクスコア+25（限定付適正意見リスク）")


EVENT_INVENTORY = GameEvent(
    id="inventory_management",
    title="棚卸資産管理・原価計算体制の整備（N-2立会に備える）",
    description=(
        "在庫担当者から報告: 「本社が初めて棚卸に立ち会ったところ、実数と帳簿が全く合っていません。\n"
        "実地棚卸のマニュアルもなく、各現場担当者任せでした。」\n\n"
        "【なぜN-3期中の整備が必須か】\n"
        "N-2期（直前々期）から監査が始まります。\n"
        "N-2期の期末棚卸（通常3月末）に監査法人が立ち会います。\n"
        "N-3期中に体制が整っていないと、N-2期末の立会で\n"
        "『監査範囲の制約』→『限定付適正意見』となり、上場申請が不可能になります。\n\n"
        "【原価計算体制（製造業・小売業）】\n"
        "棚卸資産の評価に必要な原価計算体制が未整備だと、\n"
        "製造原価・売上原価の信頼性が監査で問われます。\n\n"
        "【ポイント】棚卸立会は「N-2期期末に備えてN-3期中に整備する」が鉄則です。"
    ),
    choices=[
        Choice(
            label="A. 棚卸管理システム・受払記録・立会体制・原価計算をフルセット整備（¥12M）",
            description="N-2期期末立会に万全の状態で臨む。原価計算体制も同時整備",
            immediate_effect=lambda c: (_apply_cost(c, 12.0), _implement_inventory_system(c))[1],
            risk_hint="コスト¥12M。ただしN-2期末立会・限定付適正意見リスクを完全排除",
        ),
        Choice(
            label="B. まず手動の在庫カウントだけ始める（¥2M）",
            description="受払記録・原価計算は後回し。立会体制が不完全な状態で監査を迎える",
            immediate_effect=lambda c: (_apply_cost(c, 2.0), _manual_inventory_only(c))[1],
            profit_hint="コスト抑制",
            risk_hint="N-2期末立会で帳簿合理性検証不可リスク。+10",
        ),
        Choice(
            label="C. 今期は後回しにする（コスト削減）",
            description="N-2期以降に対処。しかしN-2期末立会に間に合わない可能性が高い",
            immediate_effect=_skip_inventory,
            profit_hint="今期コストゼロ",
            risk_hint="N-2期末の限定付適正意見リスク → 上場申請不可。+25",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=True,
    trigger_condition=lambda c: c.flags.no_inventory_count,
)


# ─────────────────────────────────────────────
# イベント5: 労務管理
# ─────────────────────────────────────────────
def _fix_overtime_properly(company: Company) -> str:
    company.flags.unpaid_overtime = False
    company.quarterly_burn += 3.0  # 残業代コスト増
    company.employee_morale += 15
    company.compliance_score += 20
    _tax_msg = _growth_tax(company, 2)   # 残業規制で稼働減（恒久）
    return ("⏰ 労務コンプライアンス体制を完全整備しました。\n"
            f"   勤怠管理システム導入・残業代完全支払い・36協定の適正管理。\n"
            f"   従業員士気+15 / コンプライアンス+20（コスト¥3百万円/Q増加）\n"
            f"   {_tax_msg}\n"
            f"   ▶ 【実務】労務コンプライアンスの上場審査チェックポイント：\n"
            f"     ①未払残業代：ショートレビューで必ず指摘される最頻発項目\n"
            f"       上場直前に引当金計上が必要となると、利益計画が大幅に狂います\n"
            f"     ②36協定の管理：特別条項の適切な運用・締結状況の確認\n"
            f"     ③ハラスメント防止体制：パワハラ・セクハラ防止規程の整備\n"
            f"     ④雇用形態の整理：有期→無期転換ルールへの対応状況\n"
            f"   ▶ 主幹事証券会社も労務コンプライアンスを引受審査で厳しく確認します。\n"
            f"     元従業員からの労基署申告が上場直前に発覚すると致命的です。")


def _ignore_overtime(company: Company) -> str:
    company.flags.unpaid_overtime = True
    company.flags.overtime_bomb_timer = random.randint(4, 10)  # 4〜10Q後に発動
    company.revenue.recognized *= 1.03  # 人件費圧縮で短期利益増
    _boost_msg = _growth_boost(company, 1)   # 残業上等の全力営業（恒久）
    return (f"💰 残業代の管理を曖昧なまま継続。短期的に人件費を圧縮できます。\n"
            f"   売上利益率+3%（一時的） / {_boost_msg}\n"
            f"   ⚠️  {company.flags.overtime_bomb_timer}Q後に労基署調査の爆弾が仕掛けられました！\n"
            f"   ▶ 【非表示リスク】元従業員が労基署に申告するリスクが潜んでいます。\n"
            f"     上場直前に発覚した場合、未払額全額の引当金計上が求められ\n"
            f"     利益計画・上場スケジュールが根本から崩れます。")


EVENT_LABOR = GameEvent(
    id="labor_management",
    title="労務コンプライアンス体制の整備（未払残業代・36協定）",
    description=(
        "人事部から相談があります。\n\n"
        "「一部の部門で残業時間の管理が曖昧で、サービス残業が常態化しています。\n"
        "法的には問題がありますが、対応するとコストが増加します。\n\n"
        "上場審査では以下が確認されます：\n"
        "  ①未払残業代の有無と対応状況\n"
        "  ②36協定（特別条項）の適切な管理・締結\n"
        "  ③ハラスメント防止体制の整備\n"
        "  ④有期→無期転換ルールへの対応\n\n"
        "特に未払残業代はショートレビューで必ず指摘される最頻発項目です。\n"
        "上場直前に引当金計上が必要となると、利益計画が崩壊します。\n"
        "主幹事証券会社も引受審査で労務コンプライアンスを厳格に確認します。」\n\n"
        "【ポイント】労務問題は『因果応報の爆弾』。N-3期から対処が重要です。"
    ),
    choices=[
        Choice(
            label="A. 勤怠管理システム導入・残業代完全支払い・36協定整備をすべて実施（¥5M）",
            description="コンプライアンス最優先。未払残業代の爆弾を完全無効化",
            immediate_effect=lambda c: (_apply_cost(c, 5.0), _fix_overtime_properly(c))[1],
            risk_hint="コスト増（¥3M/Q）。ただし上場直前の爆弾リスクを完全排除",
        ),
        Choice(
            label="B. このまま曖昧な管理を続ける（コスト削減・利益最大化）",
            description="短期利益優先。上場直前の爆弾リスクは見えていない",
            immediate_effect=_ignore_overtime,
            profit_hint="短期利益+3%",
            risk_hint="4〜10Q後に労基署調査の爆弾が発動。上場計画崩壊リスク",
        ),
    ],
    min_n_period=-3,
    max_n_period=-1,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント6: 職務分掌
# ─────────────────────────────────────────────
def _implement_job_separation(company: Company) -> str:
    company.flags.no_job_separation = False
    company.flags.embezzlement_risk_level = 0
    company.internal_control_score += 20
    company.quarterly_burn += 3.0  # 担当者追加コスト
    company.defense_score += 1     # 🏗 現場負荷（管理体制の運用負荷）
    return ("🔒 出納と記帳の職務分掌を実施しました。\n"
            f"   経理担当者を増員し、承認フローも整備。コスト¥3百万円/Q増加。\n"
            f"   内部統制スコア+20 / 横領リスクゼロに\n"
            f"   ▶ 実務: 職務分掌は内部統制の基本中の基本。\n"
            f"     1人が出納（現金管理）と記帳（会計入力）を兼ねると\n"
            f"     横領が容易になり、監査でも重大な欠陥と指摘されます。")


def _keep_single_accountant(company: Company) -> str:
    company.flags.no_job_separation = True
    company.flags.embezzlement_risk_level = 1
    return ("💰 経理担当者1人体制を維持。採用コストを抑えられます。\n"
            f"   ⚠️  横領リスクが毎Q上昇していきます（現在Lv.{company.flags.embezzlement_risk_level}）\n"
            f"   ▶ このリスクは経過するごとに発動確率が上がります。")


EVENT_JOB_SEPARATION = GameEvent(
    id="job_separation",
    title="出納と記帳の職務分掌",
    description=(
        "監査法人からのアドバイス: 「現在、出納（現金管理）と記帳（会計入力）を\n"
        "同一の経理担当者が行っています。これは横領の温床になりやすく、\n"
        "内部統制の重大な欠陥と判断される可能性があります。」\n"
        "【ポイント】職務分掌はコーポレートガバナンスの基本原則です。"
    ),
    choices=[
        Choice(
            label="A. 経理担当者を増員し、出納と記帳を分離する（¥2百万円/Q）",
            description="職務分掌の適切な実施",
            immediate_effect=_implement_job_separation,
        ),
        Choice(
            label="B. 今は採用コストがかけられないので現行体制を維持する",
            description="コスト削減優先",
            immediate_effect=_keep_single_accountant,
            profit_hint="採用コスト削減",
            risk_hint="横領リスクが毎Q上昇",
        ),
    ],
    min_n_period=-3,
    max_n_period=-1,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント7: 反社チェック（コンプライアンス）
# ─────────────────────────────────────────────
def _thorough_antisocial_check(company: Company) -> str:
    company.flags.antisocial_vendor = False
    company.compliance_score += 25
    company.has_antisocial_system = True
    company.revenue.recognized *= 0.95   # 問題取引先の契約解除で売上減
    company.defense_score += 1           # 🏗 現場負荷（取引先審査・契約見直しの負荷）
    return ("✅ 全取引先の反社会的勢力排除チェックを実施しました。\n"
            f"   専門調査機関に依頼し、問題のある取引先を契約解除。\n"
            f"   コンプライアンス+25 / 取引先解約で売上-5%（一時）\n"
            f"   ▶ 実務: 東証上場規程では反社会的勢力との関係を遮断することが\n"
            f"     上場審査の必要条件です。主幹事証券会社も厳しくチェックします。")


def _cheap_vendor_antisocial(company: Company) -> str:
    company.flags.antisocial_vendor = True
    company.flags.antisocial_bomb_timer = random.randint(3, 8)
    company.quarterly_burn -= 5.0  # 安い仕入先なのでコスト減
    return (f"💰 コスト重視で取引先を選定。仕入コスト¥5百万円/Q削減。\n"
            f"   ⚠️  {company.flags.antisocial_bomb_timer}Q後に反社チェック不備の爆弾が仕掛けられました！\n"
            f"   ▶ 安価な取引先は身元確認が不十分なことがあります。（リスク非表示）")


EVENT_ANTISOCIAL_CHECK = GameEvent(
    id="antisocial_check",
    title="取引先の反社会的勢力排除チェック",
    description=(
        "調達部門から提案: 「コスト削減のため、新しい仕入先候補があります。\n"
        "価格は現在より30%安いですが、設立間もない会社で詳しい情報がありません。\n"
        "急いで契約するか、時間をかけて審査するか判断してください。」\n"
        "【ポイント】上場規程に基づく反社チェックは主幹事証券会社の必須確認事項です。"
    ),
    choices=[
        Choice(
            label="A. 専門調査機関による反社チェックを実施してから契約する（¥3百万円）",
            description="コンプライアンス最優先",
            immediate_effect=lambda c: (_apply_cost(c, 3.0), _thorough_antisocial_check(c))[1],
            risk_hint="調査コスト発生",
        ),
        Choice(
            label="B. コスト優先で審査なしに契約する",
            description="即時コスト削減",
            immediate_effect=_cheap_vendor_antisocial,
            profit_hint="仕入コスト30%削減",
            risk_hint="反社リスク（非表示）",
        ),
    ],
    min_n_period=-3,
    max_n_period=-1,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント8: 関連当事者取引の整理
# ─────────────────────────────────────────────
def _clean_related_party(company: Company) -> str:
    company.flags.no_related_party_review = False
    company.governance_score += 20
    company.auditor_trust += 15
    return ("🤝 関連当事者取引を整理・開示しました。\n"
            f"   創業者・取締役との取引を全件洗い出し、適正な条件に見直し。\n"
            f"   ガバナンス+20 / 監査法人信頼+15\n"
            f"   ▶ 実務: 関連当事者取引は上場審査の重要チェック項目です。\n"
            f"     特に創業者個人会社との取引は、利益相反の観点から厳しく審査されます。")


def _hide_related_party(company: Company) -> str:
    company.flags.no_related_party_review = True
    company.flags.total_risk_score += 20
    # 短期的に創業者への利益誘導が続く
    company.cash += 5.0
    return ("💰 関連当事者取引の整理を先送りにしました。現状維持で短期利益¥5百万円確保。\n"
            f"   ⚠️  上場審査では関連当事者取引は必ず全件確認されます。\n"
            f"   リスクスコア+20")


EVENT_RELATED_PARTY = GameEvent(
    id="related_party_transactions",
    title="関連当事者取引の把握・整理",
    description=(
        "監査法人から確認事項: 「創業者のご親族が経営する会社と数件の取引があります。\n"
        "また、取締役が個人で所有する不動産を会社が賃借しているケースも見受けられます。\n"
        "これらは関連当事者取引として整理・開示が必要です。」\n"
        "【ポイント】関連当事者取引の未整理は上場審査での重大な指摘事項となります。"
    ),
    choices=[
        Choice(
            label="A. 全取引を洗い出し、適正条件に見直す（¥4百万円）",
            description="完全整理と適正化",
            immediate_effect=lambda c: (_apply_cost(c, 4.0), _clean_related_party(c))[1],
        ),
        Choice(
            label="B. 現状維持（見直しは後でいい）",
            description="短期的な利益優先",
            immediate_effect=_hide_related_party,
            profit_hint="現状利益確保",
            risk_hint="上場審査での重大指摘リスク",
        ),
    ],
    min_n_period=-2,
    max_n_period=0,
    one_shot=True,
    trigger_condition=lambda c: c.flags.no_related_party_review,
)


# ─────────────────────────────────────────────
# イベント9: 社外役員選任（ガバナンス）
# ─────────────────────────────────────────────
def _appoint_outside_director(company: Company) -> str:
    # 会社法第329条：取締役・監査役の選任は株主総会決議が必要。
    # 内定（CEO決断）は今期行うが、正式就任・ガバナンス効果は総会承認後の翌四半期に発現。
    company.agm_deferred_outside_director = True
    company.quarterly_burn += 4.0  # 役員報酬は内定・報酬総額承認後から発生
    company.defense_score += 1     # 🏗 現場負荷（取締役会運営・説明対応の負荷）
    return ("🏛️  独立社外取締役・社外監査役の候補者を内定しました。\n"
            f"   上場会社向けガバナンス経験のある弁護士・公認会計士を候補に選出しました。\n"
            f"   ▶ 【会社法第329条】取締役・監査役の選任は株主総会の普通決議が必要です。\n"
            f"   ▶ 次の定時（または臨時）株主総会で正式選任決議を行います。\n"
            f"   ▶ 選任決議が可決されると翌四半期から正式就任・ガバナンス機能が本格稼働します。\n"
            f"   ▶ 役員報酬（¥4百万円/Q）は内定時から継続費用に計上されます。\n"
            f"   【実務】直前期（N-1期）期首までに選任が必要。直前期を通じた運用実績が審査で確認されます。")


def _delay_outside_director(company: Company) -> str:
    company.flags.no_outside_director = True
    company.flags.total_risk_score += 15
    company.governance_score = max(0, company.governance_score - 15)
    return ("⏭️  社外役員選任を先送りにしました。\n"
            f"   ▶ 【重大注意】社外役員は直前期（N-1期）期首までに選任が必要です。\n"
            f"     直前期を通じた運用実績が上場審査で確認されるためです。\n"
            f"     N-1期中途からの選任では運用実績が不十分として指摘されます。\n"
            f"     監査役3名以上（半数以上社外）の要件も充足できない場合、\n"
            f"     上場申請そのものが受理されないリスクがあります。\n"
            f"   ▶ リスクスコア+15 / ガバナンス-15（社外役員選任遅延リスク）")


EVENT_OUTSIDE_DIRECTOR = GameEvent(
    id="outside_director",
    title="独立社外役員の選任（N-2期定時株主総会での選任が理想）",
    description=(
        "IPO準備アドバイザーから助言がありました。\n\n"
        "「社長、社外役員の選任準備を早期に進めましょう。\n\n"
        "【上場審査で求められる要件】\n"
        "  ①監査役：3名以上、半数以上は社外監査役（独立した弁護士・公認会計士等）\n"
        "  ②社外取締役：プライム市場では取締役会の1/3以上が独立社外取締役\n"
        "    スタンダード・グロース市場でも2名以上が必要\n"
        "  ③独立性：主要取引先・大株主の関係者は独立社外役員として不可\n\n"
        "【タイミングの重要性】\n"
        "  直前期（N-1期）の期首までに選任する必要があります。\n"
        "  上場審査では直前期を通じた運用実績が確認されるため、\n"
        "  N-1期途中からの選任では実績不足として指摘されます。\n\n"
        "  N-3期から候補者の選定・コンタクトを開始し、\n"
        "  N-2期の定時株主総会で正式選任を完了させるのが、最も確実でリスクのないスケジュールです。」\n\n"
        "【ポイント】社外役員はN-1期期首までに選任し、1年間の運用実績を積むことが必須です。\n"
        "早期に候補者を内定し、次の株主総会で選任決議に臨みましょう。"
    ),
    choices=[
        Choice(
            label="A. 独立社外取締役・社外監査役の候補者を内定する（役員報酬¥4百万円/Q）",
            description="弁護士・公認会計士等の専門家を候補に選出。次の定時株主総会で正式選任決議",
            immediate_effect=_appoint_outside_director,
            risk_hint="役員報酬¥4百万/Q（年¥1,600万）。ただし運用実績確保が最重要",
        ),
        Choice(
            label="B. 今は見送り、後で検討する",
            description="今は費用を抑える。ただし直前期運用実績の確保が困難になる",
            immediate_effect=_delay_outside_director,
            profit_hint="役員報酬コスト削減（今期のみ）",
            risk_hint="N-1期途中選任→運用実績不足→審査指摘。リスクスコア+15",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,  # N-1期は緊急版 EVENT_OUTSIDE_DIRECTOR_N1 に委ねる
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント9b: 監査法人候補の選定（N-3期）
# ─────────────────────────────────────────────
def _select_big_firm(company: Company) -> str:
    company.audit_firm_tier = "big"
    company.cash -= 5.0
    company.auditor_trust = min(100, company.auditor_trust + 5)
    return ("🏢 大手監査法人（Big4系）への打診を開始しました。\n\n"
            "   候補：あずさ監査法人 / EY新日本 / トーマツ / PwCあらた\n"
            "   ▶ アドバイザリー費用 ¥5M（事前打診・体制評価費用）\n"
            "   ▶ 監査法人信頼+5（大手法人への早期アプローチを評価）\n\n"
            "   【特徴】\n"
            "   ・上場審査での信頼性が極めて高い\n"
            "   ・受嘱審査が厳格（体制不備があると受嘱拒否されやすい）\n"
            "   ・監査報酬は年間¥15〜30M程度（中小企業の場合）\n\n"
            "   ▶ N-2期突入時に正式な受嘱審査（ルーレット）が行われます。\n"
            "     大手法人は体制の完成度を厳しく見ます。")


def _select_mid_firm(company: Company) -> str:
    company.audit_firm_tier = "mid"
    company.cash -= 3.0
    return ("🏢 中堅監査法人への打診を開始しました。\n\n"
            "   候補：太陽有限責任監査法人 / 仰星監査法人 / 三優監査法人 等\n"
            "   ▶ アドバイザリー費用 ¥3M\n\n"
            "   【特徴】\n"
            "   ・IPO実績が豊富でバランスの良い選択\n"
            "   ・受嘱審査は適度な厳格さ（基本的な体制が整っていれば受嘱可能）\n"
            "   ・監査報酬は年間¥10〜20M程度\n"
            "   ・担当パートナーとの距離が近く、相談しやすい\n\n"
            "   ▶ N-2期突入時に正式な受嘱審査（ルーレット）が行われます。")


def _select_small_firm(company: Company) -> str:
    company.audit_firm_tier = "small"
    company.cash -= 1.5
    company.auditor_trust = max(0, company.auditor_trust - 5)
    return ("🏢 IPO特化の小規模監査法人への打診を開始しました。\n\n"
            "   候補：IPO特化の個人事務所・新興監査法人\n"
            "   ▶ アドバイザリー費用 ¥1.5M\n"
            "   ▶ 監査法人信頼-5（大手・中堅と比べ市場での信頼性がやや劣る）\n\n"
            "   【特徴】\n"
            "   ・受嘱率が高い（人手不足の大手・中堅より柔軟に対応）\n"
            "   ・監査報酬は年間¥5〜12M程度（コスト面で有利）\n"
            "   ・ただし上場審査で監査法人の実績を問われることがある\n"
            "   ・監査法人交代リスク（上場後に大手への移行を求められる場合も）\n\n"
            "   ▶ N-2期突入時に正式な受嘱審査（ルーレット）が行われます。\n"
            "     小規模法人は比較的受嘱に前向きです。")


EVENT_AUDIT_FIRM_SELECTION = GameEvent(
    id="audit_firm_selection",
    title="監査法人候補の選定（N-2期の監査契約に向けて）",
    description=(
        "IPO準備の最重要関門——監査法人との契約に向けた準備を進めましょう。\n\n"
        "上場申請にはN-2期・N-1期の2期間にわたる財務監査が必要です。\n"
        "N-2期の期首から監査を開始するため、N-3期中に候補を選定し\n"
        "打診を始める必要があります。\n\n"
        "【監査難民問題】\n"
        "近年、監査法人の人手不足により、IPO準備会社への新規受嘱を\n"
        "断るケースが急増しています。早期の打診と体制整備が不可欠です。\n\n"
        "社長、どのクラスの監査法人を狙いますか？\n\n"
        "【ポイント】監査法人の選定はN-3期中に行い、ショートレビューの結果も踏まえて\n"
        "N-2期からの監査契約につなげることが重要です。"
    ),
    choices=[
        Choice(
            label="A. 大手監査法人（Big4系）に打診する（¥5M）",
            description="信頼性最高だが受嘱審査が厳格。体制が整っていないと受嘱拒否リスク大",
            immediate_effect=_select_big_firm,
            risk_hint="受嘱審査が厳しい。ショートレビュー・発生主義・証憑管理が必須",
        ),
        Choice(
            label="B. 中堅監査法人に打診する（¥3M）",
            description="IPO実績豊富でバランス型。適度な厳格さで実務的なサポートも期待できる",
            immediate_effect=_select_mid_firm,
        ),
        Choice(
            label="C. IPO特化の小規模法人に打診する（¥1.5M）",
            description="受嘱率は高いがブランド力に不安。コストは最小",
            immediate_effect=_select_small_firm,
            profit_hint="監査報酬��安い（年¥5〜12M）",
            risk_hint="上場審査で法人の実績を問われるリスクあり。監査法人信頼-5",
        ),
    ],
    min_n_period=-3,
    max_n_period=-3,
    one_shot=True,
    trigger_condition=lambda c: not c.audit_firm_tier,  # まだ選定していない場合のみ
)


# ─────────────────────────────────────────────
# イベント10: 資金調達（資本政策）
# ─────────────────────────────────────────────
def _raise_series_a(company: Company) -> str:
    result = raise_funding(
        company,
        "第三者割当増資（シリーズA）",
        300.0,
        1500.0,
        "VC投資家（シリーズA）",
        shareholder_boost=80,
    )
    company.investor_trust += 10
    company.has_capital_policy = True
    return (f"💼 {result}\n"
            f"   ▶ 実務: 資本政策では調達額・バリュエーション・持分比率のバランスが重要。\n"
            f"     創業者持分が上場時に3分の1を下回ると議決権が不安定になります。")


def _raise_with_ratchet(company: Company) -> str:
    result = raise_funding(
        company,
        "第三者割当増資（ラチェット条項付き）",
        400.0,
        1200.0,
        "VC投資家（ラチェット条項付き）",
        shareholder_boost=100,
    )
    company.flags.total_risk_score += 10  # ラチェット条項は上場時に問題になることがある
    company.has_capital_policy = True
    return (f"💼 {result}\n"
            f"   ⚠️  ラチェット条項により、業績未達の場合に追加株式付与義務があります。\n"
            f"     上場時に条項解消が必要になる場合があります。")


def _skip_fundraising(company: Company) -> str:
    company.investor_trust  = max(0, company.investor_trust  - 15)
    company.employee_morale = max(0, company.employee_morale - 10)
    return ("🏦 今回の調達はスキップしました。\n"
            f"   手元資金: ¥{company.cash:.1f}百万円\n"
            f"   資金の持続期間: あと約{company.runway_quarters()}四半期\n"
            f"   ⚠️  調達機会を見送ったことで投資家・主幹事からの期待感が低下しました。\n"
            f"   ▶ 投資家信頼-15 / 士気-10")


EVENT_FUNDRAISING = GameEvent(
    id="series_a_fundraising",
    title="資金調達の実施（資本政策・シリーズA）",
    description=(
        "VCから投資提案があります。\n"
        "「第三者割当増資（シリーズA）として¥3億円の調達が可能です。\n"
        "ただし、条件交渉次第ではラチェット条項（業績達成条件付き追加株式）が含まれます。」\n"
        "【ポイント】上場直前の資本政策は後から変更が難しく、慎重な設計が必要です。"
    ),
    choices=[
        Choice(
            label="A. シンプルな条件で調達する（¥3億円、Pre-money ¥15億円）",
            description="標準的な調達",
            immediate_effect=_raise_series_a,
        ),
        Choice(
            label="B. ラチェット条項付きで調達額を増やす（¥4億円、Pre-money ¥12億円）",
            description="より多く調達できるが条項リスクあり",
            immediate_effect=_raise_with_ratchet,
            profit_hint="調達額+¥1億円",
            risk_hint="ラチェット条項リスク",
        ),
        Choice(
            label="C. 今回の調達はスキップする",
            description="希薄化を避ける",
            immediate_effect=_skip_fundraising,
            profit_hint="持分希薄化なし",
            risk_hint="資金不足リスク",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=True,
    trigger_condition=lambda c: not getattr(c, 'has_capital_policy', False),
)


# ─────────────────────────────────────────────
# イベント11: 内部統制報告制度（J-SOX）
# ─────────────────────────────────────────────
def _implement_jsox_early(company: Company) -> str:
    company.internal_control_score += 25
    company.governance_score       += 15
    company.quarterly_burn         += 5.0   # 内部統制チーム人件費（継続）
    company.has_internal_control_system = True
    _tax_msg = _growth_tax(company, 2, mark=True)   # 戦略的な体制投資（恒久負荷）
    return ("📋 内部統制システム（J-SOX準備）を本格的に構築しました。\n"
            f"   内部統制スコア+25 / ガバナンス+15\n   {_tax_msg}\n"
            f"   ▶ 内部統制チームの人件費として¥5M/Q の継続コストが発生します。\n"
            f"   ▶ 【実務】内部統制の整備で作成する「3点セット」：\n"
            f"     ①業務記述書：業務プロセスの流れと担当者を文書化\n"
            f"     ②フローチャート：業務の流れを図解化（承認・牽制ポイントを明示）\n"
            f"     ③RCM（リスク・コントロール・マトリックス）：\n"
            f"       リスク項目に対する統制活動と評価方法を体系化\n"
            f"   ▶ 内部統制システムの構築は取締役会での決議が必要です。\n"
            f"   ▶ サイバーセキュリティも内部統制の対象：\n"
            f"     情報システムへのアクセス権管理・不正アクセス対策も審査で確認されます。\n"
            f"   ▶ ※一定規模以下は上場後3年間の内部統制監査が免除されますが、\n"
            f"     内部統制報告書の提出と3点セットの整備は上場後も必要です。")


def _minimal_jsox(company: Company) -> str:
    company.internal_control_score += 10
    company.quarterly_burn         += 1.0   # 最低限の文書化担当者費用
    company.has_internal_control_system = True
    company.flags.total_risk_score += 8
    _tax_msg = _growth_tax(company, 1, 1)
    return ("📋 最低限の文書化（業務記述書のみ）を実施しました。\n"
            f"   内部統制スコア+10 / ¥1M/Q の継続コストが発生します。\n   {_tax_msg}\n"
            f"   ▶ 【注意】3点セット（業務記述書・フローチャート・RCM）のうち\n"
            f"     フローチャートとRCMが未整備です。\n"
            f"     取締役会での決議も未実施のため、内部統制システムの\n"
            f"     正式な構築とは言えない状態です。上場後に追加対応が必要。\n"
            f"   リスクスコア+8（3点セット未完備）")


EVENT_JSOX = GameEvent(
    id="jsox_preparation",
    title="内部統制システムの構築（J-SOX・3点セット整備）",
    description=(
        "CFOから提案がありました。\n\n"
        "「上場後は内部統制報告書（J-SOX）の提出が義務付けられます。\n"
        "N-1期中に内部統制システムを構築し、取締役会で決議する必要があります。\n\n"
        "【整備すべき3点セット】\n"
        "  ①業務記述書：業務プロセスの流れと担当者を文書化\n"
        "  ②フローチャート：業務の流れを図解（承認・牽制ポイントを明示）\n"
        "  ③RCM（リスク・コントロール・マトリックス）：\n"
        "    リスク項目に対する統制活動と評価方法を体系化\n\n"
        "【留意点】\n"
        "  ・内部統制システムの構築は取締役会での決議が必要\n"
        "  ・サイバーセキュリティも対象：アクセス権管理・不正アクセス対策\n"
        "  ・一定規模以下は上場後3年間の内部統制監査が免除されるが、\n"
        "    内部統制報告書の提出と3点セット整備は必要」\n\n"
        "【ポイント】3点セット（業務記述書・フローチャート・RCM）が整備の核心です。"
    ),
    choices=[
        Choice(
            label="A. 3点セット全整備＋取締役会決議＋サイバーセキュリティ対応（¥15M）",
            description="業務記述書・フローチャート・RCMをフルセットで整備",
            immediate_effect=lambda c: (_apply_cost(c, 15.0), _implement_jsox_early(c))[1],
            risk_hint="コスト¥15M。上場後の内部統制監査対応が万全になる",
        ),
        Choice(
            label="B. 業務記述書のみ作成して最低限の対応にとどめる（¥5M）",
            description="フローチャート・RCMは後回し。取締役会決議も省略",
            immediate_effect=lambda c: (_apply_cost(c, 5.0), _minimal_jsox(c))[1],
            profit_hint="コスト抑制",
            risk_hint="3点セット未完備。上場後に追加対応が必要。リスク+8",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント12: CFO採用
# ─────────────────────────────────────────────
def _hire_experienced_cfo(company: Company) -> str:
    company.has_cfo = True
    company.accounting_quality += 20
    company.auditor_trust += 20
    company.quarterly_burn += 8.0
    _boost_msg = _growth_boost(company, 1)   # 資金調達力・経営管理の質向上（負荷なしの好投資）
    return ("👔 IPO経験豊富なCFOを正社員・常勤で採用しました。\n"
            f"   前職でIPOを2社経験した公認会計士をCFOとして迎えました。\n"
            f"   会計品質+20 / 監査法人信頼+20（報酬¥8百万円/Q）\n   {_boost_msg}\n"
            f"   ▶ 【実務】CFOに求められる主な役割：\n"
            f"     ①有価証券届出書（Ⅰの部）の作成・監修\n"
            f"     ②ロードショーでの投資家向け財務説明\n"
            f"     ③経理（記帳・決算）と財務（資金調達・CF管理）の分離体制の構築\n"
            f"     ④監査法人・主幹事証券会社との窓口\n"
            f"   ▶ 「常勤の正社員CFO」であることが審査上の要件です。\n"
            f"     顧問・非常勤では審査で不十分と指摘されます。\n"
            f"   ▶ 監査法人はCFOの質・資格・IPO経験を監査受嘱の判断材料にします。")


def _hire_cheap_cfo(company: Company) -> str:
    company.has_cfo = True
    company.accounting_quality += 8
    company.quarterly_burn += 4.0
    company.flags.total_risk_score += 5
    return ("👔 経理部長経験者を採用しました。\n"
            f"   IPO経験は限定的です。コストは抑えられますが課題があります。\n"
            f"   会計品質+8 / リスクスコア+5\n"
            f"   ▶ 【注意】有価証券届出書（Ⅰの部）の作成・ロードショー対応・\n"
            f"     経理と財務の分離体制構築は、CFOの実務スキルに大きく依存します。\n"
            f"     IPO未経験のCFOでは監査法人・主幹事証券会社の信頼獲得に\n"
            f"     時間がかかり、上場スケジュールに影響が出る可能性があります。")


def _hire_advisor_not_cfo(company: Company) -> str:
    company.has_cfo = False
    company.accounting_quality += 4
    company.flags.total_risk_score += 15
    return ("💼 外部CFOアドバイザー（非常勤）を契約しました。\n"
            f"   ▶ 【重大注意】上場審査では「常勤の正社員CFO」が実質的に求められます。\n"
            f"     非常勤アドバイザーは有価証券届出書の作成・監査法人対応・\n"
            f"     ロードショーへの対応が困難で、審査で『財務管理体制不備』\n"
            f"     として指摘を受けるリスクが高まります。\n"
            f"   会計品質+4のみ / リスクスコア+15（体制不備リスク）")


EVENT_CFO_HIRING = GameEvent(
    id="cfo_hiring",
    title="CFO（最高財務責任者）の採用",
    description=(
        "社長、現在、財務責任者が不在です。ヘッドハンターから候補が提示されました。\n\n"
        "CFOの主な役割：\n"
        "  ①有価証券届出書（Ⅰの部）の作成・監修\n"
        "  ②ロードショーでの投資家向け財務説明\n"
        "  ③経理（記帳・決算）と財務（資金調達・CF管理）の分離体制の構築\n"
        "  ④監査法人・主幹事証券会社との窓口\n\n"
        "【重要】審査では『常勤の正社員CFO』が実質的に求められます。\n"
        "  顧問・非常勤では体制不備として指摘されます。\n\n"
        "【ポイント】監査法人はCFOの質・資格・IPO経験も監査受嘱の判断材料にします。"
    ),
    choices=[
        Choice(
            label="A. IPO経験2社の公認会計士を正社員・常勤CFOとして採用（年俸¥3,200万）",
            description="Ⅰの部作成・ロードショー対応・経理財務分離すべて対応可能な最強布陣",
            immediate_effect=_hire_experienced_cfo,
            risk_hint="コスト¥8百万/Q（年¥3,200万）",
        ),
        Choice(
            label="B. 中小企業経理部長経験者を正社員・常勤CFOとして採用（年俸¥1,600万）",
            description="経理経験あり。IPO実績は限定的。Ⅰの部作成・ロードショー対応に不安",
            immediate_effect=_hire_cheap_cfo,
            profit_hint="コスト半減：¥4百万/Q（年¥1,600万）",
            risk_hint="IPO未経験→監査法人信頼獲得に時間。審査リスク+5",
        ),
        Choice(
            label="C. 外部CFOアドバイザー（非常勤）を活用してコストを抑える",
            description="顧問契約で対応。常勤不在は審査での体制不備リスクあり",
            immediate_effect=_hire_advisor_not_cfo,
            profit_hint="人件費最小化",
            risk_hint="常勤不在→審査で体制不備指摘。リスクスコア+15",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=True,
    trigger_condition=lambda c: not c.has_cfo,
)


# ─────────────────────────────────────────────
# イベント13: 中期経営計画の策定（事業計画・資本政策）
# ─────────────────────────────────────────────
def _build_full_midterm_plan(company: Company) -> str:
    company.investor_trust      += 20
    company.governance_score    += 15
    company.internal_control_score += 10
    company.has_mid_term_plan = True
    return ("📋 外部コンサルタントと共に中期経営計画（3ヵ年）を策定しました。\n"
            "   売上・利益・KPI・成長戦略を取締役会で承認。\n"
            "   投資家信頼+20 / ガバナンス+15 / 内部統制+10\n"
            "   ▶ 【実務】中期経営計画のポイント：\n"
            "     ①N-3期末の3ヶ月程度前から作成開始し、N-2期期首には完成が目標\n"
            "     ②ローリング方式（毎期見直し・修正）で精度を維持\n"
            "     ③計画と実績の乖離が生じた場合は、取締役会・株主への説明が必要\n"
            "     ④修正のタイミングの適切性も上場審査で確認されます\n"
            "   ▶ 主幹事証券会社・東証も「成長ストーリーの一貫性」と\n"
            "     「計画の達成可能性・根拠」を厳しく審査します。")


def _build_simple_midterm_plan(company: Company) -> str:
    company.investor_trust   += 8
    company.governance_score += 5
    company.has_mid_term_plan = True
    company.flags.total_risk_score += 8
    return ("📋 社内チームで簡易な利益計画を作成しました。\n"
            "   投資家信頼+8 / ガバナンス+5 / リスクスコア+8\n"
            "   ▶ 【注意】ローリング方式による毎期見直し体制が未構築のため、\n"
            "     計画と実績の乖離が発生した際の説明対応に不安が残ります。\n"
            "     修正タイミングの適切性・乖離原因の分析説明は上場審査の確認事項です。\n"
            "   ⚠ N-2期期首完成が理想。現状は作成時期が遅く、運用実績も浅い状態です。")


EVENT_BUSINESS_PLAN = GameEvent(
    id="business_plan",
    title="中期経営計画の策定（3ヵ年成長戦略）",
    description=(
        "CFOからの提言：「中期経営計画の策定について、タイミングが重要です。\n\n"
        "理想的なスケジュール：\n"
        "  ・N-3期末の3ヶ月程度前：作成開始\n"
        "  ・N-2期期首：完成（N-2期の監査・主幹事審査の基礎となる）\n"
        "  ・以降：ローリング方式で毎期見直し・修正\n\n"
        "上場審査では以下が確認されます：\n"
        "  ①計画の達成可能性・根拠の合理性\n"
        "  ②計画と実績の乖離が生じた場合の原因分析と株主説明\n"
        "  ③計画修正のタイミングの適切性\n\n"
        "IPO申請書（Ⅰの部）にも業績予想と根拠の記載が求められます。」\n\n"
        "【ポイント】中期経営計画は上場審査の重要確認書類。N-2期期首完成が理想です。"
    ),
    choices=[
        Choice(
            label="A. 外部コンサルと本格的な3ヵ年計画を策定する（¥8百万円）",
            description="市場分析・競合分析・KPI設計＋ローリング方式の運用体制まで整備",
            immediate_effect=lambda c: (_apply_cost(c, 8.0), _build_full_midterm_plan(c))[1],
            risk_hint="初期コスト¥8M。N-2期期首完成・ローリング運用で審査を最大化",
        ),
        Choice(
            label="B. 社内で簡易な利益計画のみ作成する（¥1百万円）",
            description="コスト抑制。最低限の数値計画のみ。ローリング方式未対応",
            immediate_effect=lambda c: (_apply_cost(c, 1.0), _build_simple_midterm_plan(c))[1],
            profit_hint="コスト削減",
            risk_hint="乖離説明・修正タイミング適切性の審査で弱点。リスク+8",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント14: 組織体制・経営管理強化
# ─────────────────────────────────────────────
def _build_strong_mgmt(company: Company) -> str:
    company.internal_control_score += 20
    company.governance_score       += 10
    company.quarterly_burn         += 3.0
    company.employee_morale        += 10
    return ("🏢 経営管理部門を強化し、管理部長・法務担当を採用しました。\n"
            "   内部統制+20 / ガバナンス+10 / 士気+10（コスト¥3百万/Q増）\n"
            "   ▶ 実務: 上場企業には経営企画・法務・IR担当の専門人材が必要です。\n"
            "     管理部門が薄いと上場審査・上場後の開示対応が困難になります。")


def _minimal_mgmt(company: Company) -> str:
    company.internal_control_score += 8
    company.quarterly_burn         += 1.0
    return ("🏢 最低限の管理部門強化にとどめました。\n"
            "   内部統制+8（コスト¥1百万/Q増）\n"
            "   ⚠ 体制の薄さは上場審査でも指摘を受ける可能性があります。")


EVENT_ORG_BUILDING = GameEvent(
    id="org_building",
    title="経営管理体制・組織強化",
    description=(
        "人事部長からの報告：「IPO準備を進める上で、経営管理部門が\n"
        "現在の体制では手薄です。経営企画・法務・内部監査の担当者が\n"
        "必要ではないでしょうか。採用計画のご判断をお願いします。」\n"
        "【ポイント】上場企業には経営管理・IR・法務の専門人材が必要です。"
    ),
    choices=[
        Choice(
            label="A. 経営管理部門を本格強化する（管理部長・法務採用）（¥3百万/Q）",
            description="IPO基準を見据えた経営管理体制の構築",
            immediate_effect=_build_strong_mgmt,
        ),
        Choice(
            label="B. 必要最低限の採用にとどめる（¥1百万/Q）",
            description="コスト抑制を優先",
            immediate_effect=_minimal_mgmt,
            profit_hint="人件費抑制",
            risk_hint="上場審査で体制不備を指摘される可能性",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント15: 会計・ERPシステム整備（決算早期化）
# ─────────────────────────────────────────────
def _implement_erp(company: Company) -> str:
    company.accounting_quality     += 20
    company.internal_control_score += 15
    company.quarterly_burn         += 5.0   # ライセンス・保守費用（継続）
    return ("💻 ERPシステムを導入しリアルタイム財務集計体制を整備しました。\n"
            "   会計品質+20 / 内部統制+15\n"
            "   ▶ ライセンス・保守費用として¥5M/Q の継続コストが発生します。\n"
            "   ▶ 実務: 上場会社は四半期報告書を45日以内に提出する義務があります。\n"
            "     リアルタイムで財務データを集計できるシステムが不可欠です。")


def _implement_cloud_acc(company: Company) -> str:
    company.accounting_quality     += 10
    company.internal_control_score += 8
    company.quarterly_burn         += 2.0   # SaaSライセンス費（継続）
    return ("💻 クラウド会計システムに移行しました。\n"
            "   会計品質+10 / 内部統制+8\n"
            "   ▶ SaaSライセンス費用として¥2M/Q の継続コストが発生します。\n"
            "   （ERPに比べ機能に制限がありますが、コスト効率は高いです）")


def _keep_manual_acc(company: Company) -> str:
    company.flags.total_risk_score += 10
    return ("📊 手動の会計処理を継続します。\n"
            "   リスクスコア+10\n"
            "   ⚠ 四半期報告の迅速化が困難に。監査法人からの指摘リスクあり。")


EVENT_IT_SYSTEMS = GameEvent(
    id="it_systems",
    title="会計・ERPシステム整備（決算早期化）",
    description=(
        "CFOからの報告：「現在の会計システムは上場会社水準には不十分です。\n"
        "四半期報告書の45日以内提出義務に対応するには、\n"
        "リアルタイムで財務情報を集計できるシステムが必要です。\n"
        "またショートレビューでも決算早期化が課題として指摘されています。」\n"
        "【ポイント】上場後は四半期報告書の迅速な作成が義務付けられます。"
    ),
    choices=[
        Choice(
            label="A. ERP（統合基幹システム）を導入する（¥20百万円）",
            description="全社横断のリアルタイム財務管理基盤を構築",
            immediate_effect=lambda c: (_apply_cost(c, 20.0), _implement_erp(c))[1],
            risk_hint="初期投資¥20M",
        ),
        Choice(
            label="B. クラウド会計システムに切り替える（¥5百万円）",
            description="コスト効率重視で基本機能を確保",
            immediate_effect=lambda c: (_apply_cost(c, 5.0), _implement_cloud_acc(c))[1],
            profit_hint="コスト抑制",
            risk_hint="機能制限あり",
        ),
        Choice(
            label="C. 現行の手動管理を継続する（コストゼロ）",
            description="投資を先送り",
            immediate_effect=_keep_manual_acc,
            profit_hint="投資なし",
            risk_hint="四半期報告対応が困難になるリスク",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント16: 主幹事証券会社の選定・引受契約
# ─────────────────────────────────────────────
def _select_major_uw(company: Company) -> str:
    company.has_underwriter  = True
    company.has_share_admin  = True   # 主幹事選定に伴い株主名簿管理人を設置
    company.investor_trust  += 25
    company.governance_score += 10
    return ("🏦 大手主幹事証券会社と引受契約を締結しました！\n"
            "   上場審査支援・公開指導・機関投資家ネットワーク・ロードショー支援を受けられます。\n"
            "   投資家信頼+25 / ガバナンス+10\n"
            "   ▶ 【実務】主幹事証券会社の役割：\n"
            "     ①上場準備全体を主導する最重要プレイヤー\n"
            "     ②「公開指導（引受審査）」として管理体制・財務内容を精査\n"
            "     ③引受審査の結果を「公開指導・引受審査の内容に関する報告書」として\n"
            "       証券取引所に提出（東証審査の重要参考資料）\n"
            "     ④ロードショー・ブックビルディング・公募・売出しを主導\n"
            "   ▶ 主幹事は一度選定したら原則変更しません。\n"
            "     途中変更すると証券取引所から経緯の説明を求められ、\n"
            "     上場スケジュールが大幅に遅延します。\n"
            "   ▶ 大手証券会社は審査が厳格な分、東証審査でも信頼性の担保になります。")


def _select_mid_uw(company: Company) -> str:
    company.has_underwriter = True
    company.has_share_admin = True    # 主幹事選定に伴い株主名簿管理人を設置
    company.investor_trust += 12
    return ("🏦 中堅証券会社と引受契約を締結しました。\n"
            "   投資家信頼+12\n"
            "   ▶ 【実務】主幹事証券会社は上場準備全体を主導する最重要プレイヤーです。\n"
            "     公開指導（引受審査）の内容は報告書として証券取引所に提出されます。\n"
            "     中堅証券会社は機関投資家ネットワーク・ロードショー網が大手に比べ限定的です。\n"
            "   ▶ 主幹事変更は証券取引所への説明義務が生じ、上場延期につながります。\n"
            "     一度選定したら最後まで協力関係を維持することが重要です。")


def _delay_underwriter(company: Company) -> str:
    company.flags.total_risk_score += 15
    company.investor_trust          = max(0, company.investor_trust   - 10)
    company.auditor_trust           = max(0, company.auditor_trust    - 8)
    company.governance_score        = max(0, company.governance_score - 5)
    company.flags.underwriter_intentionally_skipped = True  # N-1Q2 再機会トリガー
    return ("⏭️  主幹事証券会社の選定を意図的に先送りにしました。\n"
            "   ▶ 【重大警告】主幹事選定はN-3期が理想、N-2期が最遅です。\n"
            "     N-1期以降では公開指導期間が極めて短くなります。\n"
            "   ▶ 投資家信頼-10 / 監査法人信頼-8 / ガバナンス-5\n"
            "   ▶ リスクスコア+15（主幹事選定遅延リスク）\n"
            "   📋 N-1期Q1に改めて主幹事選定の機会が提供されます。")


EVENT_UNDERWRITER = GameEvent(
    id="underwriter_selection",
    title="主幹事証券会社の選定・引受契約",
    description=(
        "CFOからの報告：「主幹事証券会社の選定について、タイミングが極めて重要です。\n"
        "（N-3期が理想、N-2期が最遅）\n\n"
        "【主幹事の役割】\n"
        "  ①上場準備全体を主導する最重要プレイヤー\n"
        "  ②『公開指導（引受審査）』として管理体制・財務内容を精査\n"
        "  ③引受審査の結果を『報告書』として証券取引所に提出\n"
        "  ④ロードショー・ブックビルディング・公募・売出しを主導\n\n"
        "【重要】主幹事は原則変更しません。\n"
        "  途中変更は証券取引所から経緯説明を求められ、\n"
        "  上場スケジュールが大幅に遅延します。慎重な選定が必要です。\n\n"
        "【理想タイミング】N-3期（最遅でもN-2期）\n"
        "  N-2期以降の選定では公開指導期間が短くなり、\n"
        "  指摘事項の改善が間に合わないリスクがあります。」\n\n"
        "【ポイント】主幹事選定はN-3が理想、N-2が最遅。早期選定が上場成功の鍵です。"
    ),
    choices=[
        Choice(
            label="A. 大手主幹事証券会社を選定する（審査厳格・ネットワーク最強）",
            description="野村・大和・SMBC日興等。公開指導報告書の評価が高く東証審査で有利",
            immediate_effect=_select_major_uw,
            risk_hint="引受審査が厳しい（内部管理体制の整備が前提）",
        ),
        Choice(
            label="B. 中堅証券会社を選定する（機動的・コスト効率重視）",
            description="スピード重視。公開指導・ネットワークは大手に劣る",
            immediate_effect=_select_mid_uw,
            profit_hint="審査・コスト負担が軽減",
            risk_hint="機関投資家ネットワーク・ロードショー網が限定的",
        ),
        Choice(
            label="C. 今期は選定を見送り、N-1期以降に対応する",
            description="準備が整ってから選定する方針。ただし公開指導期間が短縮",
            immediate_effect=_delay_underwriter,
            risk_hint="公開指導期間短縮 → 指摘改善不足 → リスクスコア+15",
        ),
    ],
    min_n_period=-3,
    max_n_period=-1,
    one_shot=True,
    trigger_condition=lambda c: not c.has_underwriter,
)


# ─────────────────────────────────────────────
# イベント17: 売上成長施策（前半 N-3〜N-2）
# ─────────────────────────────────────────────
def _aggressive_sales_early(company: Company) -> str:
    if random.random() < 0.60:
        company.revenue.recognized *= 1.25
        company.cash -= 10.0
        _boost_msg = _growth_boost(company, 3, mark=True)   # 戦略的な事業投資（恒久）
        company.flags.total_risk_score += 5      # 急拡大の歪み（与信・品質管理）
        return ("📈 積極的な新規顧客開拓が実を結びました！売上+25%\n"
                f"   ¥10M投資 / 新規顧客獲得に成功\n   {_boost_msg} / リスクスコア+5（急拡大の歪み）\n"
                "   ▶ IPO審査では2期以上の継続的売上成長（年率20%以上）が高評価です。")
    else:
        company.cash -= 10.0
        _boost_msg = _growth_boost(company, 1, mark=True)
        return ("📉 新規顧客開拓への投資は今期は成果が出ませんでした。¥10M支出\n"
                f"   売上変化なし（次期以降に期待） / {_boost_msg}")


def _steady_sales_early(company: Company) -> str:
    company.revenue.recognized *= 1.10
    company.employee_morale    += 5
    _boost_msg = _growth_boost(company, 1, mark=True)
    return ("📊 既存顧客深耕で着実に成長しました。売上+10%\n"
            f"   従業員士気+5 / 安定した事業運営 / {_boost_msg}\n"
            "   ▶ 継続的な売上成長の実績はIPO審査での評価に直結します。")


def _cut_cost_early(company: Company) -> str:
    company.revenue.recognized *= 1.02
    company.cash += 8.0
    _tax_msg = _growth_tax(company, 1, 2, mark=False)   # 管理負荷ではなく成長ブレーキ
    return ("💰 コスト削減を優先しました。手元資金+¥8M / 売上+2%（成長鈍化）\n"
            f"   {_tax_msg}\n"
            "   ⚠ 成長率の低下はIPO審査での評価・公募価格に影響します。")


EVENT_SALES_GROWTH_EARLY = GameEvent(
    id="sales_growth_early",
    title="売上成長戦略の実行（社長判断）",
    description=(
        "営業部長からの報告：「今期の売上進捗は計画比80%です。\n"
        "残りの期間での打ち手について、社長のご判断をお願いします。\n"
        "どの方向性で経営資源を投入しますか？\n"
        "【ポイント】IPO審査では継続的な売上成長と成長の再現性が重視されます。"
    ),
    choices=[
        Choice(
            label="A. 積極的な新規顧客開拓に投資する（¥10百万円・成功率60%）",
            description="マーケティング強化・営業体制増強。高成長を狙うが不確実性あり",
            immediate_effect=_aggressive_sales_early,
            risk_hint="投資効果に不確実性（成功率60%）",
        ),
        Choice(
            label="B. 既存顧客深耕で堅実に成長する",
            description="顧客単価向上・継続率改善で着実に拡大",
            immediate_effect=_steady_sales_early,
            profit_hint="安定的な成長実績を積み上げ",
        ),
        Choice(
            label="C. 今期はコストを抑えキャッシュを優先する",
            description="資金繰り優先の守りの経営",
            immediate_effect=_cut_cost_early,
            profit_hint="短期キャッシュ+¥8M",
            risk_hint="成長鈍化でIPO評価・公募価格に影響",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=False,  # 1N期に1回まで発火
)


# ─────────────────────────────────────────────
# イベント18: 売上成長施策（後半 N-1〜N）
# ─────────────────────────────────────────────
def _sprint_sales_late(company: Company) -> str:
    if random.random() < 0.55:
        company.revenue.recognized *= 1.20
        company.cash -= 15.0
        company.investor_trust += 10
        _boost_msg = _growth_boost(company, 2, mark=True)
        company.flags.total_risk_score += 8   # 駆け込み計上への監査の眼
        return ("📈 申請直前の集中投資が功を奏しました！売上+20% / 投資家信頼+10\n"
                f"   {_boost_msg} / リスクスコア+8（駆け込み計上への監査の眼）\n"
                "   ▶ 上場前の業績は公募価格・時価総額に直接影響します。")
    else:
        company.cash -= 15.0
        company.offense_score += 1
        return ("📉 集中投資を実施しましたが、今期は成果が出ませんでした。¥15M支出\n"
                "   売上変化なし")


def _steady_sales_late(company: Company) -> str:
    company.revenue.recognized *= 1.08
    company.investor_trust     += 5
    _boost_msg = _growth_boost(company, 1, mark=True)
    return ("📊 堅実な成長を継続しました。売上+8% / 投資家信頼+5\n"
            f"   {_boost_msg}\n"
            "   ▶ 安定した業績は上場審査での信頼性を高めます。")


def _cut_cost_late(company: Company) -> str:
    company.revenue.recognized *= 1.02
    company.cash           += 12.0
    company.investor_trust -= 5
    _tax_msg = _growth_tax(company, 1, 2, mark=False)   # 管理負荷ではなく成長ブレーキ
    return ("💰 コスト削減・利益確保を優先しました。手元資金+¥12M / 投資家信頼-5\n"
            f"   {_tax_msg}\n"
            "   ⚠ 直前期の成長鈍化は公募価格・IPO評価に悪影響を与えます。")


EVENT_SALES_GROWTH_LATE = GameEvent(
    id="sales_growth_late",
    title="上場直前の成長戦略（社長判断）",
    description=(
        "営業部長からの報告：「今期の売上進捗をご報告します。\n"
        "上場審査・公募価格に影響するこの時期の業績について、\n"
        "社長として経営方針をご判断ください。\n"
        "【ポイント】申請期の業績は公募価格と時価総額に直接影響します。"
    ),
    choices=[
        Choice(
            label="A. 集中投資で上場前に業績を最大化する（¥15百万円・成功率55%）",
            description="上場前スプリント。リスクはあるが公募価格最大化を狙う",
            immediate_effect=_sprint_sales_late,
            risk_hint="投資効果に不確実性（成功率55%）",
        ),
        Choice(
            label="B. 着実な成長路線を維持する",
            description="安定した業績で審査官の信頼を獲得",
            immediate_effect=_steady_sales_late,
            profit_hint="安定した業績で審査評価アップ",
        ),
        Choice(
            label="C. コスト削減・利益率を優先する",
            description="収益性の高さをアピール",
            immediate_effect=_cut_cost_late,
            profit_hint="手元資金+¥12M",
            risk_hint="成長性が弱いとIPO評価・公募価格に悪影響",
        ),
    ],
    min_n_period=-1,
    max_n_period=0,
    one_shot=False,  # 1N期に1回まで発火
)


# ─────────────────────────────────────────────
# イベント19: 株式事務・定款・ディスクロジャー体制整備
# ─────────────────────────────────────────────
def _full_stock_admin(company: Company) -> str:
    company.compliance_score    += 15
    company.governance_score    += 15
    company.investor_trust      += 10
    company.has_share_admin = True
    # 定款変更（譲渡制限廃止・単元株設定等）は株主総会の特別決議が必要（会社法466条）
    # この時点では定款変更案を準備・総会上程する方針を固めた段階（N期最終手続で登記）
    return ("📑 株式事務代行機関の選定・定款変更準備・ディスクロジャー支援会社との契約を完了。\n"
            "   コンプライアンス+15 / ガバナンス+15 / 投資家信頼+10\n"
            "   ▶ 実務: 株式事務代行機関（信託銀行等）は上場前に選定が必要です。\n"
            "   ▶ 【会社法466条】定款変更（譲渡制限廃止・単元株設定・授権株式数増加等）は\n"
            "     株主総会の特別決議（2/3以上の賛成）が必要です。\n"
            "     N期の定時株主総会での特別決議を経て、法務局への登記で効力が発生します。")


def _minimal_stock_admin(company: Company) -> str:
    company.compliance_score += 7
    company.governance_score += 7
    company.has_share_admin = True
    company.has_articles_amendment = True
    return ("📑 定款変更と株式事務の基本対応のみ実施しました。\n"
            "   コンプライアンス+7 / ガバナンス+7\n"
            "   （ディスクロジャー支援会社との連携が未整備のため、上場後の開示対応に課題が残ります）")


EVENT_STOCK_ADMIN = GameEvent(
    id="stock_admin",
    title="株式事務・定款・ディスクロジャー体制の整備",
    description=(
        "法務担当からの報告：「上場準備の事務手続きとして以下が必要です。\n"
        "① 株式事務代行機関（信託銀行等）の選定・契約\n"
        "② 定款の変更（授権株式数・公告方法・役員任期等）\n"
        "③ ディスクロジャー支援会社との連携\n"
        "社長、対応方針のご判断をお願いします。」\n"
        "【ポイント】株式事務代行機関は上場申請前に選定が必要な必須項目です。"
    ),
    choices=[
        Choice(
            label="A. 株式事務・定款・ディスクロジャー体制をフルセットで整備する（¥8百万円）",
            description="専門家チームで全項目を網羅的に対応",
            immediate_effect=lambda c: (_apply_cost(c, 8.0), _full_stock_admin(c))[1],
            risk_hint="整備コスト¥8M",
        ),
        Choice(
            label="B. 定款変更と株式事務の基本対応のみ行う（¥3百万円）",
            description="最低限の対応のみ",
            immediate_effect=lambda c: (_apply_cost(c, 3.0), _minimal_stock_admin(c))[1],
            profit_hint="コスト削減",
            risk_hint="上場後のディスクロジャー対応に追加コストが発生",
        ),
    ],
    min_n_period=-1,
    max_n_period=0,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント20: IR・適時開示体制の整備
# ─────────────────────────────────────────────
def _build_full_ir(company: Company) -> str:
    company.investor_trust   += 25
    company.governance_score += 15
    company.quarterly_burn   += 3.0   # IR担当者人件費（継続）
    company.has_disclosure_system = True
    return ("📣 IR体制・適時開示体制を本格的に整備しました。\n"
            "   IR担当者採用・IRサイト構築・決算説明会資料テンプレート作成完了。\n"
            "   投資家信頼+25 / ガバナンス+15\n"
            "   ▶ IR担当者人件費として¥3M/Q の継続コストが発生します。\n"
            "   ▶ 実務: 上場後は適時開示規則に基づき、重要情報を遅滞なく\n"
            "     開示する義務があります。上場廃止要件にも該当するため最重要です。")


def _minimal_ir(company: Company) -> str:
    company.investor_trust   += 10
    company.governance_score +=  5
    company.quarterly_burn   += 1.5   # 最低限のIR担当者費用（継続）
    company.has_disclosure_system = True
    return ("📣 最低限のIR体制を整備しました。\n"
            "   投資家信頼+10 / ガバナンス+5\n"
            "   ▶ IR担当費用として¥1.5M/Q の継続コストが発生します。\n"
            "   （上場後の本格IR運営には追加対応が必要です）")


EVENT_IR_SETUP = GameEvent(
    id="ir_setup",
    title="IR・適時開示体制の整備",
    description=(
        "CFOからの提言：「上場後は適時開示規則に基づき、重要情報を\n"
        "遅滞なく開示する義務があります。IR担当者の採用と\n"
        "開示体制の整備を今から進めておくべきです。\n"
        "主幹事証券会社からも体制整備を強く求められています。」\n"
        "【ポイント】適時開示の遅延・漏れは上場廃止要件にも該当します。"
    ),
    choices=[
        Choice(
            label="A. IR担当者採用・IRサイト構築で本格体制を整える（¥6百万円）",
            description="決算説明会資料・適時開示フロー・IRサイトをフルセット整備",
            immediate_effect=lambda c: (_apply_cost(c, 6.0), _build_full_ir(c))[1],
            risk_hint="整備コスト¥6M",
        ),
        Choice(
            label="B. 最低限の開示対応だけ行う（¥2百万円）",
            description="必要最小限の体制のみ",
            immediate_effect=lambda c: (_apply_cost(c, 2.0), _minimal_ir(c))[1],
            profit_hint="コスト削減",
            risk_hint="上場後の開示対応で追加コストが発生",
        ),
    ],
    min_n_period=-1,
    max_n_period=0,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント21: 有価証券届出書・目論見書の準備
# ─────────────────────────────────────────────
def _thorough_prospectus(company: Company) -> str:
    company.compliance_score       += 20
    company.auditor_trust          += 15
    company.flags.total_risk_score  = max(0, company.flags.total_risk_score - 10)
    return ("📄 有価証券届出書・目論見書の準備を本格的に開始しました。\n"
            "   法律事務所・証券会社と連携し、開示書類のドラフトを作成中。\n"
            "   コンプライアンス+20 / 監査法人信頼+15 / リスクスコア-10\n"
            "   ▶ 実務: 目論見書（有価証券届出書）はIPO申請の核心書類です。\n"
            "     事業内容・リスク要因・財務情報を正確に記載する必要があります。\n"
            "     虚偽記載は民事・刑事の両責任を負います。")


def _basic_prospectus(company: Company) -> str:
    company.compliance_score += 10
    company.auditor_trust    +=  5
    return ("📄 有価証券届出書の基本的な準備を開始しました。\n"
            "   コンプライアンス+10 / 監査法人信頼+5\n"
            "   ⚠ 開示書類の品質向上には追加の専門家関与が必要です。")


EVENT_PROSPECTUS = GameEvent(
    id="prospectus_preparation",
    title="有価証券届出書・目論見書の準備",
    description=(
        "法務担当からの報告：「IPO申請には有価証券届出書（目論見書）の提出が必要です。\n"
        "事業リスク・財務情報・コーポレートガバナンスについて\n"
        "正確かつ網羅的な記載が求められます。\n"
        "申請書類（Iの部・IIの部）の作成も並行して進める必要があります。」\n"
        "【ポイント】虚偽記載は刑事罰の対象。記載内容は上場後も投資家判断の基礎となります。"
    ),
    choices=[
        Choice(
            label="A. 法律事務所・証券会社と連携し本格的に準備する（¥15百万円）",
            description="専門家チームが全項目を徹底レビュー。記載の正確性を確保",
            immediate_effect=lambda c: (_apply_cost(c, 15.0), _thorough_prospectus(c))[1],
            risk_hint="専門家費用¥15M",
        ),
        Choice(
            label="B. 社内主体で準備し、要所のみ専門家を活用する（¥6百万円）",
            description="コスト抑制。重要箇所のみ専門家レビュー",
            immediate_effect=lambda c: (_apply_cost(c, 6.0), _basic_prospectus(c))[1],
            profit_hint="コスト削減",
            risk_hint="記載漏れ・誤記リスクが残る",
        ),
    ],
    min_n_period=-1,
    max_n_period=0,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント22: 公開価格・公募戦略の決定（N期）
# ─────────────────────────────────────────────
def _high_price_strategy(company: Company) -> str:
    if random.random() < 0.5:
        company.market_cap_million *= 1.30
        company.investor_trust     += 15
        return ("💹 強気の公募価格設定が市場に好意的に受け入れられました！\n"
                "   時価総額+30% / 投資家信頼+15\n"
                "   ▶ IPOの公募価格は需要動向（ブックビルディング）をもとに決定されます。")
    else:
        company.market_cap_million *= 0.90
        company.investor_trust     -= 10
        return ("📉 強気の公募価格が市場に受け入れられず、上場後に株価が下落しました。\n"
                "   時価総額-10% / 投資家信頼-10\n"
                "   ⚠ 公募価格と市場評価のバランスが重要です。")


def _balanced_price_strategy(company: Company) -> str:
    company.market_cap_million *= 1.15
    company.investor_trust     += 10
    return ("💹 適切な公募価格設定で安定した上場を実現しました。\n"
            "   時価総額+15% / 投資家信頼+10\n"
            "   ▶ 公募価格は高すぎると上場後に下落リスク、\n"
            "     低すぎると既存株主への損失となります。バランスが重要です。")


EVENT_IPO_PRICING = GameEvent(
    id="ipo_pricing",
    title="公開価格・ロードショー戦略の決定（N期）",
    description=(
        "主幹事証券会社からの報告：「ブックビルディングの結果、\n"
        "公開価格の設定について社長のご判断をお願いします。\n"
        "強気の設定か、安定重視の設定かで上場後の株価動向が変わります。\n"
        "機関投資家へのロードショーでの反応は良好です。」\n"
        "【ポイント】公開価格は企業価値評価（EV/EBITDA等）と需要動向を基に決定します。"
    ),
    choices=[
        Choice(
            label="A. 強気の公募価格を設定する（時価総額最大化・成功率50%）",
            description="高いバリュエーションで調達額・時価総額を最大化",
            immediate_effect=_high_price_strategy,
            profit_hint="成功時：時価総額+30%",
            risk_hint="失敗時：上場後に株価下落リスク（確率50%）",
        ),
        Choice(
            label="B. バランスの取れた公募価格で安定上場を優先する",
            description="適切なバリュエーションで上場後の株価安定を重視",
            immediate_effect=_balanced_price_strategy,
            profit_hint="上場後の株価安定・投資家信頼確保",
        ),
    ],
    min_n_period=0,
    max_n_period=0,
    one_shot=True,
    trigger_condition=lambda c: c.has_underwriter,
)


# ─────────────────────────────────────────────
# イベント23: 株主総会（Q4ごとに発生）― 自動イベント
# ─────────────────────────────────────────────
def shareholder_meeting_event(company: Company, n_period: int) -> str:
    """定時株主総会イベント（Q4ごと）― 議案投票・ルーレット・株主の声付き"""
    import random as _r
    results = []
    rev = company.revenue.recognized
    trust = company.investor_trust

    period_labels = {-3: "N-3期", -2: "N-2期（直前々期）", -1: "N-1期（直前期）", 0: "N期（申請期）"}
    plabel = period_labels.get(n_period, "")

    results.append(f"━━━ {plabel} 定時株主総会 開会 ━━━\n")

    # ══════════════════════════════
    # 議案投票（期ごとに異なる議案）
    # ══════════════════════════════
    # 投票通過確率：スコアと業績に基づいて計算
    def _pass_prob(base: float, trust_boost: float = 0.3, score_boost: float = 0.0) -> float:
        t_bonus = max(0.0, (trust - 50) / 100) * trust_boost
        return min(0.95, max(0.10, base + t_bonus + score_boost))

    def _vote(proposal: str, pass_prob: float,
              pass_effect_fn, fail_effect_fn,
              pass_msg: str, fail_msg: str) -> str:
        """ルーレット投票。結果テキストを返す。"""
        roll = _r.random()
        if roll < pass_prob:
            effect_text = pass_effect_fn()
            return (f"  📋 第{_vote._n}号議案：{proposal}\n"
                    f"  🗳  賛成多数で【可決】（賛成率約{int(pass_prob*100)}%）\n"
                    f"  ✅ {pass_msg}\n"
                    f"  {effect_text}")
        else:
            effect_text = fail_effect_fn()
            return (f"  📋 第{_vote._n}号議案：{proposal}\n"
                    f"  🗳  反対多数で【否決】（賛成率{int(pass_prob*100)}%に届かず）\n"
                    f"  ❌ {fail_msg}\n"
                    f"  {effect_text}")
    _vote._n = 0

    def vote(proposal, pass_prob, pass_eff, fail_eff, pass_msg, fail_msg):
        _vote._n += 1
        return _vote(proposal, pass_prob, pass_eff, fail_eff, pass_msg, fail_msg)

    results.append("【今期の議案一覧と投票結果】\n")

    if n_period == -3:
        # N-3期：体制構築フェーズの議案
        results.append(vote(
            "取締役報酬規程の改定（業績連動報酬の導入）",
            _pass_prob(0.65, 0.25),
            lambda: (setattr(company, 'governance_score',
                             min(100, company.governance_score + 8)),
                     "  ▶ ガバナンス+8（業績連動でインセンティブ設計を評価）")[1],
            lambda: (setattr(company, 'governance_score',
                             max(0, company.governance_score - 5)),
                     "  ▶ ガバナンス-5（役員報酬への不満が募る）")[1],
            "業績連動報酬制度が導入されました。",
            "株主から「自社株買いを優先すべき」との反論が出て否決されました。"
        ))
        results.append("")
        results.append(vote(
            "新ストックオプション付与計画の承認（役員・従業員向け）",
            _pass_prob(0.70, 0.20),
            lambda: (setattr(company, 'employee_morale',
                             min(100, company.employee_morale + 10)),
                     "  ▶ 士気+10（SOが従業員のモチベーションを向上）")[1],
            lambda: (setattr(company, 'investor_trust',
                             max(0, company.investor_trust - 8)),
                     "  ▶ 投資家信頼-8（希薄化懸念から反対票が多数）")[1],
            "ストックオプション計画が承認されました。従業員の士気向上に期待。",
            "希薄化を懸念するVC株主が反対し否決されました。"
        ))

    elif n_period == -2:
        # N-2期：監査・体制強化フェーズ
        results.append(vote(
            "監査等委員会設置会社への移行の承認",
            _pass_prob(0.60, 0.30,
                       score_boost=0.1 if company.governance_score >= 50 else -0.1),
            lambda: (setattr(company, 'governance_score',
                             min(100, company.governance_score + 12)),
                     "  ▶ ガバナンス+12（コーポレートガバナンス強化として高評価）")[1],
            lambda: (setattr(company, 'governance_score',
                             max(0, company.governance_score - 3)),
                     "  ▶ ガバナンス-3（移行の手続きを再検討することに）")[1],
            "監査等委員会設置会社への移行が承認されました。",
            "「時期尚早」との意見が多数を占め、否決されました。"
        ))
        results.append("")
        results.append(vote(
            "第三者割当増資（VC追加投資ラウンド）の承認",
            _pass_prob(0.55, 0.40),
            lambda: (setattr(company, 'cash', company.cash + 50.0),
                     setattr(company, 'investor_trust',
                             min(100, company.investor_trust + 10)),
                     "  ▶ 資金+50M ／ 投資家信頼+10（成長資金確保を評価）")[2],
            lambda: (setattr(company, 'investor_trust',
                             max(0, company.investor_trust - 12)),
                     "  ▶ 投資家信頼-12（既存株主が希薄化に強く反対）")[1],
            "増資が可決。追加資金50Mを調達しました。",
            "既存株主の希薄化反対が票を制し否決されました。"
        ))
        results.append("")
        # ガバナンス指摘（候補内定済み or 否決後の臨時総会待ち or 既選任 は発言しない）
        _has_candidate = company.agm_deferred_outside_director
        _vote_failed   = company.outside_director_rejected_needs_eogm
        if _has_candidate:
            # 候補者が内定済み → 本総会の閉会前に選任議案として決議する（_od_vote_in_agm が実施）
            results.append(
                "📋 社外役員選任議案（本総会内で決議 ― 閉会前に議決します）\n"
                "   ✅ 候補者（独立社外取締役・社外監査役）は前期中に内定済みです。"
            )
        elif company.flags.no_outside_director and not _vote_failed:
            company.investor_trust = max(0, company.investor_trust - 18)
            results.append(
                "💬 独立社外取締役候補・弁護士 木村氏（株主提案）:\n"
                "   「御社にはまだ独立社外取締役がいらっしゃいませんね。\n"
                "   東証上場審査で最初に確認される項目です。\n"
                "   今期（N-2期）中に候補者を内定し、来期（N-1期）の定時株主総会で\n"
                "   正式選任されるスケジュールが最低限必要です。早急にご対応ください。」\n"
                "   ▶ 投資家信頼-18（ガバナンス欠陥として強く指摘）"
            )

    elif n_period == -1:
        # N-1期：IPO直前期
        results.append(vote(
            "内部統制報告制度（J-SOX）対応費用・予算計上の承認",
            _pass_prob(0.65, 0.25,
                       score_boost=0.15 if company.internal_control_score >= 50 else -0.05),
            lambda: (setattr(company, 'internal_control_score',
                             min(100, company.internal_control_score + 8)),
                     "  ▶ 内部統制+8（J-SOX対応が進捗し評価される）")[1],
            lambda: (setattr(company, 'internal_control_score',
                             max(0, company.internal_control_score - 5)),
                     "  ▶ 内部統制-5（J-SOX対応遅延への懸念が表明される）")[1],
            "J-SOX対応予算が承認されました。上場審査に向け着実な進捗です。",
            "「費用対効果が不明確」と株主から反発を受け否決されました。"
        ))
        results.append("")
        results.append(vote(
            "上場申請に向けた役員体制の強化（CFO・CCO選任）の承認",
            _pass_prob(0.60, 0.30),
            lambda: (setattr(company, 'governance_score',
                             min(100, company.governance_score + 10)),
                     setattr(company, 'compliance_score',
                             min(100, company.compliance_score + 8)),
                     "  ▶ ガバナンス+10 ／ コンプラ+8（経営体制強化を高評価）")[2],
            lambda: (setattr(company, 'governance_score',
                             max(0, company.governance_score - 5)),
                     "  ▶ ガバナンス-5（役員増員コストへの反発）")[1],
            "役員体制強化が承認されました。CFO・CCO選任により経営管理が強化されます。",
            "「役員報酬の増加は株主価値を毀損する」として否決されました。"
        ))
        results.append("")
        # VC質問タイム
        if trust < 70:
            company.investor_trust -= 12
            results.append(
                "💬 VC代表・鈴木氏（株主質問タイム）:\n"
                "   「社長、一点だけ確認させてください。\n"
                "   N期（来期）での上場申請というスケジュールに、今も変わりはありませんか？\n"
                "   正直に言えば、現状のスコアでは審査通過に黄信号が灯っています。\n"
                "   私たちは経営を信じたい。でも数字は正直です。来期の覚悟を示してください。」\n"
                "   ▶ 投資家信頼-12（VCによる厳しい質問）"
            )
        else:
            company.investor_trust += 8
            results.append(
                "💬 VC代表・鈴木氏（株主質問タイム）:\n"
                "   「素晴らしい進捗です。N期（当期）の上場申請に向けて\n"
                "   私たちVC一同、全力でバックアップします。\n"
                "   主幹事証券との連携も順調と聞いています。ぜひ鐘を鳴らしてください！」\n"
                "   ▶ 投資家信頼+8（VCが上場への期待を表明）"
            )

    elif n_period == 0:
        # N期：申請期・最終総会
        results.append(vote(
            "上場申請・株式公開に関する決議",
            _pass_prob(0.70, 0.25,
                       score_boost=0.15 if company.internal_control_score >= 60 else -0.15),
            lambda: (setattr(company, 'investor_trust',
                             min(100, company.investor_trust + 15)),
                     "  ▶ 投資家信頼+15（上場決議が圧倒的多数で可決！）")[1],
            lambda: (setattr(company, 'investor_trust',
                             max(0, company.investor_trust - 20)),
                     setattr(company.flags, 'total_risk_score',
                             min(100, company.flags.total_risk_score + 10)),
                     "  ▶ 投資家信頼-20 ／ リスク+10（株主の不信任が爆発）")[2],
            "上場決議が圧倒的多数で可決されました！東証審査へ進みます。",
            "一部株主が上場準備の不備を指摘し、決議に異論が生じました。"
        ))
        results.append("")
        results.append(
            "💬 主幹事証券会社・引受部長:\n"
            "   「本日の株主総会は無事に終えられました。お疲れ様です。\n"
            "   これから東証の審査が始まります。審査官は非常に厳しい目で\n"
            "   御社の内部体制・財務・ガバナンスを確認します。\n"
            "   社長自ら全ての数字と体制を把握・説明できる状態を維持してください。」\n"
            "   ▶ 上場審査まで最終段階です"
        )

    # ══════════════════════════════
    # 期ごと共通：エンジェル投資家の反応
    # ══════════════════════════════
    if n_period <= -2 and rev < 80:
        company.investor_trust -= 15
        results.append(
            "\n💬 エンジェル投資家・田中氏（シード出資者）:\n"
            "   「社長、正直に聞かせてください。このペースで本当にIPOできると\n"
            "   思っているんですか？私は夢を買ったはずなんですが…\n"
            "   売上がこれでは、次回ファイナンスで希薄化されるのはわかりますよね？」\n"
            "   ▶ 投資家信頼-15（エンジェルの不満が高まっています）"
        )
    elif n_period <= -1 and rev >= 150:
        company.investor_trust += 12
        results.append(
            "\n💬 エンジェル投資家・田中氏:\n"
            "   「いやぁ、社長、これは期待以上ですよ！\n"
            "   私も周りの投資家仲間に胸を張って紹介できます。\n"
            "   引き続き、よろしくお願いします！」\n"
            "   ▶ 投資家信頼+12"
        )

    # ══════════════════════════════
    # VC反応（N-3・N-2限定のルーレットなし軽量版）
    # ══════════════════════════════
    if n_period in (-3, -2):
        if trust < 60:
            company.investor_trust -= 8
            results.append(
                "\n💬 VC・グロースキャピタル担当者:\n"
                "   「取締役会でも申し上げましたが、KPIの達成率が著しく低いです。\n"
                "   このままでは追加投資の判断ができません。\n"
                "   来期Q1までに改善策を取締役会に提出していただけますか？」\n"
                "   ▶ 投資家信頼-8（VCから改善要求）"
            )
        elif trust >= 80 and rev >= 100:
            company.investor_trust += 8
            results.append(
                "\n💬 VC・グロースキャピタル担当者:\n"
                "   「KPI・売上ともに計画を上回っています。\n"
                "   上場後のセカンダリー市場でも良い評価が期待できますね。\n"
                "   引き続き、ガバナンス強化をお願いします。」\n"
                "   ▶ 投資家信頼+8"
            )

    results.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
    return "\n".join(results)


# ─────────────────────────────────────────────
# イベント23b: 株主総会インタラクティブイベント生成（Q4ターン毎）
# ─────────────────────────────────────────────
def create_agm_event(company: Company, n_period: int) -> "GameEvent":
    """定時株主総会インタラクティブGameEventを動的に生成する。
    Q4ターンの _begin_turn から呼び出され、通常イベントとして表示される。
    ALL_EVENTS には登録しない（毎回動的生成）。"""
    import random as _r

    period_labels = {-3: "N-3期", -2: "N-2期（直前々期）", -1: "N-1期（直前期）", 0: "N期（申請期）"}
    plabel = period_labels.get(n_period, f"N{n_period}期")

    def _pp(base: float, trust_boost: float = 0.3, score_boost: float = 0.0) -> float:
        t_bonus = max(0.0, (company.investor_trust - 50) / 100) * trust_boost
        return min(0.95, max(0.10, base + t_bonus + score_boost))

    def _run_standing_items(c: Company, results: list) -> None:
        """毎期AGMに共通する必須常設議案を自動処理し結果を results に追記する。
        会社法の各条文に対応した正確な議案名・決議要件を学習用に表示。"""
        results.append("━━ ＜必須常設議案＞ ━━")

        # ① 計算書類・事業報告の承認（会社法第438条）
        _agenda1 = "  📋 第1号議案：計算書類・事業報告 承認の件（会社法438条・普通決議）"
        if _r.random() < 0.92:
            c.accounting_quality = min(100, c.accounting_quality + 3)
            results.append(_agenda1 + "\n  🗳 賛成多数【可決】▶ 会計品質+3（透明な決算開示を株主が評価）")
        else:
            results.append(_agenda1 + "\n  🗳 否決（一部株主が決算数値に疑義を呈しました。要因分析が必要です）")

        # ② 取締役・監査役の選任（年次更新）（会社法第329条）
        _agenda2 = "  📋 第2号議案：取締役・監査役の選任（会社法329条・普通決議）"
        dir_pp = min(0.95, max(0.50, 0.72 + (c.investor_trust - 50) / 200))
        if _r.random() < dir_pp:
            results.append(_agenda2 + f"\n  🗳 賛成多数【可決】（賛成率約{int(dir_pp*100)}%）▶ 役員体制継続確認")
        else:
            c.governance_score = max(0, c.governance_score - 5)
            results.append(_agenda2 + f"\n  🗳 一部候補が否決【否決】▶ ガバナンス-5（役員信任に陰りが見えます）")

        # ③ 取締役報酬総額の決定（会社法第361条）※ N-2期以降
        if n_period >= -2:
            _agenda3 = "  📋 第3号議案：取締役報酬総額限度額の決定（会社法361条・普通決議）"
            rp = min(0.90, max(0.55, 0.72 + (c.governance_score - 30) / 200))
            if _r.random() < rp:
                c.governance_score = min(100, c.governance_score + 4)
                results.append(_agenda3 + f"\n  🗳 賛成多数【可決】 ▶ ガバナンス+4（役員報酬の透明性が確保されました）")
            else:
                results.append(_agenda3 + f"\n  🗳 否決【否決】（「報酬額が業績に見合わない」との反発）")

        # ④ 剰余金の配当（無配）決議（会社法第454条）※ N-1期以降
        if n_period >= -1:
            _agenda4 = "  📋 第4号議案：剰余金の配当（1株0円・無配継続）の件（会社法454条・普通決議）"
            if _r.random() < 0.85:
                results.append(_agenda4 + "\n  🗳 賛成多数【可決】▶ 無配方針を確認（上場前3期間は内部留保優先が原則）")
            else:
                c.investor_trust = max(0, c.investor_trust - 8)
                results.append(_agenda4 + "\n  🗳 一部株主が配当要求【否決】▶ 投資家信頼-8（無配継続への不満が顕在化）")

        # ⑤ 社外役員の選任は Q1 _begin_turn で実施（前期に内定した候補者を翌期Q1 AGM で議決）
        # → _run_standing_items ではフラグ確認のみ行い、ここでは処理しない

        # ⑥ 会計監査人の選任：監査法人内諾後の正式選任（会社法第329条2項）
        if c.audit_firm_agreed and not c.has_audit_contract:
            _agenda6 = ("  📋 臨時議案：会計監査人（監査法人）の選任（会社法329条2項・普通決議）\n"
                        "  　　監査法人から準金商法監査契約の内諾を得ています。")
            if _r.random() < 0.95:  # 内諾済みなので高確率で可決
                c.has_audit_contract = True
                c.has_accounting_auditor = True
                c.auditor_trust    = min(100, c.auditor_trust + 15)
                c.compliance_score = min(100, c.compliance_score + 10)
                c.governance_score = min(100, c.governance_score + 10)
                results.append(
                    _agenda6 + "\n  🗳 賛成多数【可決】\n"
                    "  ✅ 会計監査人が正式選任・本日就任（登記申請済）。\n"
                    "  ✅ 準金商法監査契約が正式に締結されました。\n"
                    "  ▶ 監査法人信頼+15・コンプラ+10・ガバナンス+10"
                )
            else:
                c.flags.total_risk_score += 8
                results.append(
                    _agenda6 + "\n  🗳 否決【否決】▶ 会計監査人選任が否決されました。リスク+8\n"
                    "  ⚠️ 次回の定時株主総会で再度選任を諮る必要があります。"
                )

        # ⑥-2 会計監査人の選任（N-1期イベントからの deferred）（会社法第329条2項）
        if c.agm_deferred_auditor_appt:
            _agenda6b = "  📋 臨時議案：会計監査人（監査法人）の選任（会社法329条2項・普通決議）"
            if _r.random() < 0.92:
                c.agm_deferred_auditor_appt = False
                c.has_accounting_auditor = True
                c.auditor_trust    = min(100, c.auditor_trust + 15)
                c.compliance_score = min(100, c.compliance_score + 10)
                c.governance_score = min(100, c.governance_score + 10)
                results.append(
                    _agenda6b + "\n  🗳 賛成多数【可決】\n"
                    "  ✅ 会計監査人が正式選任・本日就任（登記申請済）。\n"
                    "  ▶ 監査法人信頼+15・コンプラ+10・ガバナンス+10"
                )
            else:
                c.agm_deferred_auditor_appt = False
                c.flags.total_risk_score += 8
                results.append(
                    _agenda6b + "\n  🗳 否決【否決】▶ 会計監査人選任が否決されました。リスク+8（上場申請要件未充足）"
                )

        # ⑦ 定款変更の承認（株主総会承認待ち）（会社法第466条）
        if c.agm_deferred_articles_amendment:
            _agenda7 = "  📋 臨時議案：定款一部変更の件（会社法466条・特別決議 2/3以上）"
            if _r.random() < 0.88:
                results.append(
                    _agenda7 + "\n  🗳 特別決議【可決】（2/3以上の賛成）\n"
                    "  ✅ 定款変更が承認されました。本総会決議後、速やかに法務局への登記手続きを完了します。"
                )
                # deferred flag stays True → processed in _begin_turn next Q
            else:
                c.agm_deferred_articles_amendment = False
                c.flags.total_risk_score += 15
                c.compliance_score = max(0, c.compliance_score - 8)
                results.append(
                    _agenda7 + "\n  🗳 否決【否決】（2/3に届かず）\n"
                    "  ❌ 定款変更が否決されました。上場審査リスク+15・コンプラ-8"
                )

        # ⑦-N1 定款変更（N-1期AGMでの自動上程：上場に必要な5項目）（会社法466条・特別決議）
        if n_period == -1 and not c.has_articles_amendment and not c.agm_deferred_articles_amendment:
            _agenda7n1 = (
                "  📋 特別議案：定款一部変更の件（会社法466条・特別決議 2/3以上）\n"
                "  上場に必要な定款変更5項目を上程します：\n"
                "    ①譲渡制限規定の削除（公開会社への移行）\n"
                "    ②株主名簿管理人（信託銀行等）に関する条項の追加\n"
                "    ③公告方法の変更（官報→電子公告）\n"
                "    ④単元株式数100株の規定追加（東証の原則）\n"
                "    ⑤株券不発行に関する規定（振替制度対応）"
            )
            if _r.random() < 0.85:
                c.agm_deferred_articles_amendment = True
                results.append(
                    _agenda7n1 + "\n  🗳 特別決議【可決】（2/3以上の賛成）\n"
                    "  ✅ 定款変更が承認されました。本総会決議後、速やかに法務局への登記手続きを完了します。"
                )
            else:
                c.flags.total_risk_score += 12
                c.compliance_score = max(0, c.compliance_score - 5)
                c.articles_amendment_rejected_needs_eogm = True
                results.append(
                    _agenda7n1 + "\n  🗳 否決【否決】（2/3に届かず）\n"
                    "  ❌ 定款変更が否決されました。リスク+12・コンプラ-5\n"
                    "  ⚠ N-1期総会での定款変更未承認は上場審査に重大な支障を来します。\n"
                    "    会社法第297条に基づきN期に【臨時株主総会】を招集し、定款変更を再上程する必要があります。"
                )

        results.append("")  # 空行区切り

    def _secondary(c: Company, results: list) -> None:
        """VC・エンジェル反応など自動二次効果。原則として毎AGMで必ず1件以上の株主反応を出す。
        社外役員の議決は Q1 _begin_turn で行われるため、ここでは「未選任かつ候補者未内定」の場合のみ木村氏が発言する。
        候補者内定済み（agm_deferred_outside_director=True）なら Q1 AGM で選任投票が行われるので発言しない。"""
        results.append("  ── 株主反応 ──")
        _initial_len = len(results)
        rev = c.revenue.recognized
        trust = c.investor_trust

        # 木村氏発言条件：未選任 AND 候補者未内定 AND Q1投票否決後の臨時総会待ちでもない
        _od_rejected = getattr(c, 'outside_director_rejected_needs_eogm', False)
        if (n_period == -2 and c.flags.no_outside_director
                and not c.agm_deferred_outside_director and not _od_rejected):
            c.investor_trust = max(0, c.investor_trust - 18)
            results.append(
                "💬 独立社外取締役候補・弁護士 木村氏（株主提案）:\n"
                "   「御社にはまだ独立社外取締役がいらっしゃいませんね。\n"
                "   東証上場審査で最初に確認される項目です。\n"
                "   今期（N-2期）中に候補者を内定し、来期（N-1期）の定時株主総会で\n"
                "   正式選任されるスケジュールが最低限必要です。遅れれば遅れるほど\n"
                "   上場審査でのリスクが高まります。早急にご対応ください。」\n"
                "   ▶ 投資家信頼-18（ガバナンス欠陥として強く指摘）"
            )
        elif (n_period == -1 and c.flags.no_outside_director
                and not c.agm_deferred_outside_director and not _od_rejected):
            c.investor_trust = max(0, c.investor_trust - 25)
            results.append(
                "💬 独立社外取締役候補・弁護士 木村氏（株主提案・緊急動議）:\n"
                "   「社長、これは上場審査に直結する緊急事態です。\n"
                "   N-2期中に選任を完了できず、N-1期（直前期）の今になっても\n"
                "   独立社外取締役が不在とは、東証審査官への説明が困難です。\n"
                "   本総会後、直ちに臨時株主総会を開催し、今期中に必ず選任を\n"
                "   完了させてください。N期（当期）の上場申請には間に合わせてください。」\n"
                "   ▶ 投資家信頼-25（ガバナンス欠陥・上場申請リスクとして強く警告）"
            )

        if n_period == -1:
            if trust < 70:
                c.investor_trust = max(0, c.investor_trust - 12)
                results.append(
                    "💬 VC代表・鈴木氏（株主質問タイム）:\n"
                    "   「現状のスコアでは審査通過に黄信号が灯っています。\n"
                    "   来期の覚悟を示してください。」\n"
                    "   ▶ 投資家信頼-12（VCによる厳しい質問）"
                )
            else:
                c.investor_trust = min(100, c.investor_trust + 8)
                results.append(
                    "💬 VC代表・鈴木氏（株主質問タイム）:\n"
                    "   「素晴らしい進捗です。N期（当期）の上場申請に向けて\n"
                    "   私たちVC一同、全力でバックアップします！」\n"
                    "   ▶ 投資家信頼+8（VCが上場への期待を表明）"
                )

        if n_period <= -2 and rev < 80:
            c.investor_trust = max(0, c.investor_trust - 15)
            results.append(
                "💬 エンジェル投資家・田中氏（シード出資者）:\n"
                "   「社長、このペースで本当にIPOできると思っているんですか？」\n"
                "   ▶ 投資家信頼-15（エンジェルの不満）"
            )
        elif n_period <= -1 and rev >= 150:
            c.investor_trust = min(100, c.investor_trust + 12)
            results.append(
                "💬 エンジェル投資家・田中氏:\n"
                "   「いやぁ、社長、これは期待以上ですよ！」\n"
                "   ▶ 投資家信頼+12"
            )

        if n_period in (-3, -2):
            if trust < 60:
                c.investor_trust = max(0, c.investor_trust - 8)
                results.append(
                    "💬 VC・グロースキャピタル担当者:\n"
                    "   「KPIの達成率が著しく低いです。来期Q1までに改善策を提出してください。」\n"
                    "   ▶ 投資家信頼-8（VCから改善要求）"
                )
            elif trust >= 80 and rev >= 100:
                c.investor_trust = min(100, c.investor_trust + 8)
                results.append(
                    "💬 VC・グロースキャピタル担当者:\n"
                    "   「KPI・売上ともに計画を上回っています。引き続きガバナンス強化を。」\n"
                    "   ▶ 投資家信頼+8"
                )

        # ── 株主反応のフォールバック（1件も出なかった場合）──
        if len(results) == _initial_len:
            import random as _r_fb
            if trust >= 85 and rev >= 120:
                c.investor_trust = min(100, c.investor_trust + 3)
                results.append(
                    "💬 個人株主代表:\n"
                    "   「順調な進捗と感じます。引き続き透明性ある経営をお願いします。」\n"
                    "   ▶ 投資家信頼+3（株主満足度の高まり）"
                )
            elif trust < 50:
                c.investor_trust = max(0, c.investor_trust - 5)
                results.append(
                    "💬 個人株主代表:\n"
                    "   「経営陣の説明には不安が残ります。次期はより具体的な進捗を示してください。」\n"
                    "   ▶ 投資家信頼-5（株主からの注文）"
                )
            else:
                _generic = _r_fb.choice([
                    ("💬 個人株主代表:\n"
                     "   「議案の内容は理解しました。今後も四半期ごとの開示を丁寧にお願いします。」\n"
                     "   ▶ 株主との対話継続（数値変動なし）"),
                    ("💬 VC・グロースキャピタル担当者:\n"
                     "   「上場準備は計画通りですね。ガバナンス・内部統制の整備を引き続き進めてください。」\n"
                     "   ▶ 株主の期待表明（数値変動なし）"),
                    ("💬 エンジェル投資家・田中氏:\n"
                     "   「社長、ここまでよく踏ん張ってきた。次の四半期も期待しているよ。」\n"
                     "   ▶ 株主からの励まし（数値変動なし）"),
                ])
                results.append(_generic)

    def _od_vote_in_agm(c: Company, res: list) -> None:
        """前期に内定した社外役員候補の選任投票を本AGM内（閉会前）で実施。
        agm_deferred_outside_director=True のときのみ実行し、フラグをリセット。"""
        if not c.agm_deferred_outside_director:
            return
        _prev_label = {
            -3: "N-3期", -2: "N-2期（直前々期）", -1: "N-1期（直前期）"
        }.get(n_period, "前期")
        od_pp = min(0.93, max(0.55, 0.76 + (c.investor_trust - 50) / 200))
        _od_hdr = (
            f"\n━━ 【重点議案：ガバナンス】━━\n"
            f"  📋 社外役員選任議案（前期内定 → 本総会で正式決議）\n"
            f"       独立社外取締役・社外監査役の選任（会社法329条・普通決議）\n"
            f"       （{_prev_label}中に内定した候補者の正式選任決議）"
        )
        if _r.random() < od_pp:
            c.agm_deferred_outside_director = False
            c.flags.no_outside_director = False
            c.governance_score = min(100, c.governance_score + 18)
            c.investor_trust   = min(100, c.investor_trust   + 12)
            res.append(
                _od_hdr
                + f"\n  🗳 賛成多数【可決】（賛成率約{int(od_pp * 100)}%）"
                + "\n  ✅ 社外役員が正式選任・本日即日就任しました。"
                + "\n  ▶ ガバナンス+18・投資家信頼+12（監視機能が本格稼働）"
            )
        else:
            c.agm_deferred_outside_director = False
            c.flags.total_risk_score += 10
            c.outside_director_rejected_needs_eogm = True
            res.append(
                _od_hdr
                + f"\n  🗳 否決【否決】（賛成率{int(od_pp * 100)}%に届かず）"
                + "\n  ❌ 社外役員選任議案が否決されました。リスク+10"
                + "\n  ▶ 会社法第297条による臨時株主総会の招集が必要です。"
            )

    # ══════════════════ N-3期 ══════════════════
    if n_period == -3:
        def _eff_perf_pay(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会 ━━━\n"]
            _run_standing_items(c, res)
            res.append("📋 【重点議案・社長選択】取締役報酬の業績連動化\n")
            pp = _pp(0.70, 0.25)
            if _r.random() < pp:
                c.governance_score = min(100, c.governance_score + 10)
                c.employee_morale  = min(100, c.employee_morale + 5)
                res.append(f"  🗳  賛成多数で【可決】（賛成率約{int(pp*100)}%）\n"
                           "  ✅ 業績連動報酬制度が正式に導入されました。\n"
                           "  ▶ ガバナンス+10・士気+5")
            else:
                c.governance_score = max(0, c.governance_score - 3)
                res.append(f"  🗳  反対多数で【否決】（賛成率{int(pp*100)}%に届かず）\n"
                           "  ❌ 「自社株買いを優先すべき」との反論で否決されました。\n"
                           "  ▶ ガバナンス-3")
            sp = _pp(0.65, 0.20)
            res.append(
                "📋 第2号：ストックオプション付与枠設定（会社法238条・309条2項・特別決議）\n"
                "   ▷ 非公開会社のSO付与は株主総会の特別決議（2/3以上）が必要。\n"
                "   ▷ SOは行使まで潜在株主。上場審査の実株主数要件には直接カウントされません。"
            )
            if _r.random() < sp:
                added = 40
                c.employee_morale        = min(100, c.employee_morale + 8)
                c.potential_shareholders += added
                c.cash                  -= 3.0
                res.append(f"  🗳 特別決議【可決】 ▶ 潜在株主数+{added}・士気+8・費用¥3M")
            else:
                c.investor_trust = max(0, c.investor_trust - 6)
                res.append("  🗳 特別決議【否決】 ▶ 投資家信頼-6（希薄化懸念で2/3未達）")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        def _eff_so_plan(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会 ━━━\n"]
            _run_standing_items(c, res)
            res.append(
                "📋 【重点議案・社長選択】ストックオプション（SO）付与枠の設定（特別決議）\n"
                "   ⚖️ 【会社法238条・309条2項】\n"
                "   非公開会社では役員・従業員いずれへのSO付与も\n"
                "   株主総会の特別決議（議決権の2/3以上）が原則必要です。\n"
                "   総会で付与枠の上限・行使条件を決議し、\n"
                "   具体的な付与先・時期の決定は取締役会に委任（最長1年）できます。\n"
                "   ⚠️  SOは行使されて初めて株主となるため、\n"
                "   上場審査の実株主数要件（グロース150名等）には直接カウントされません。\n"
                "   実株主数を増やすには別途『従業員持株会』の設立が必要です。\n"
            )
            pp = _pp(0.72, 0.20)
            if _r.random() < pp:
                added = 70
                c.employee_morale        = min(100, c.employee_morale + 12)
                c.governance_score       = min(100, c.governance_score + 5)
                c.potential_shareholders += added
                c.cash                  -= 5.0
                c.has_so_program         = True   # SO付与枠が総会で可決済み
                res.append(
                    f"  🗳  特別決議【可決】（賛成率約{int(pp*100)}%・2/3以上）\n"
                    f"  ✅ SOプログラム（全社員・役員{added}名分の付与枠）が承認されました。\n"
                    f"  ▶ 潜在株主数+{added}・士気+12・ガバナンス+5・設計費¥5M\n"
                    "  💡 付与後も株主ではないため、上場審査の実株主数とは別にカウントされます。\n"
                    "   税制適格SOは原則として上場後行使。行使価額・付与期間の設計が重要です。"
                )
            else:
                c.investor_trust = max(0, c.investor_trust - 10)
                res.append(
                    f"  🗳  特別決議【否決】（賛成率{int(pp*100)}%・2/3に届かず）\n"
                    "  ❌ VC株主から「希薄化により既存株主の利益が損なわれる」との反対が集まり否決。\n"
                    "  ▶ 投資家信頼-10\n"
                    "  💡 次期以降の総会で再上程する際は、付与枠を絞るか\n"
                    "   希薄化率の試算を事前に株主へ説明することが重要です。"
                )
            gp = _pp(0.62, 0.25)
            res.append("📋 第2号：役員報酬規程改定（会社法361条・普通決議）")
            if _r.random() < gp:
                c.governance_score = min(100, c.governance_score + 6)
                res.append("  🗳 賛成多数【可決】 ▶ ガバナンス+6")
            else:
                res.append("  🗳 反対多数【否決】（継続審議へ）")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        def _eff_cg_policy(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会 ━━━\n"]
            _run_standing_items(c, res)
            res.append("📋 【重点議案・社長選択】コーポレートガバナンス指針の制定\n")
            pp = _pp(0.75, 0.20)
            if _r.random() < pp:
                c.governance_score = min(100, c.governance_score + 15)
                c.investor_trust   = min(100, c.investor_trust + 7)
                res.append(f"  🗳  賛成多数で【可決】（賛成率約{int(pp*100)}%）\n"
                           "  ✅ CG指針が正式に制定されました。\n"
                           "  ▶ ガバナンス+15・投資家信頼+7（上場審査で好印象）")
            else:
                c.governance_score = max(0, c.governance_score - 2)
                res.append(f"  🗳  反対多数で【否決】（賛成率{int(pp*100)}%に届かず）\n"
                           "  ❌ 「実効性が不明確」として否決されました。\n"
                           "  ▶ ガバナンス-2")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        return GameEvent(
            id="agm_n3",
            title=f"{plabel} 定時株主総会 — 主要議案の選択",
            description=(
                "年に一度の定時株主総会が近づいています。\n"
                "上場準備をスタートしたN-3期、今年の総会では\n"
                "投資家・VCに「本気でIPOを目指している」と伝える議案選びが重要です。\n\n"
                "【IPO先生からのアドバイス】\n"
                "「N-3期の株主総会では、ガバナンスの本気度を示す議案が評価されます。\n"
                "議案の選択が投資家との信頼関係を大きく左右します。\n\n"
                "  Ａ：役員報酬の業績連動化 → ガバナンス強化の明確なシグナル\n"
                "  Ｂ：ストックオプション計画 → 従業員・経営陣の動機付けに直結\n"
                "  Ｃ：CG指針の制定 → 上場後のガバナンス体制の青写真を示す\n\n"
                "どれも重要ですが、社長が重点的に推進する議案を一つ選んでください。\n"
                "選ばれた議案に全力で賛同を取り付けます。他の議案は自動で処理されます。」"
            ),
            choices=[
                Choice(label="A. 役員報酬の業績連動化を重点議案とする",
                       description="経営インセンティブの透明化を株主にアピール",
                       immediate_effect=_eff_perf_pay),
                Choice(label="B. 新ストックオプション計画を重点議案とする",
                       description="従業員・経営陣の動機付けを強化",
                       immediate_effect=_eff_so_plan),
                Choice(label="C. コーポレートガバナンス指針の制定を重点議案とする",
                       description="上場準備本格化のシグナルを発信",
                       immediate_effect=_eff_cg_policy),
            ],
        )

    # ══════════════════ N-2期 ══════════════════
    elif n_period == -2:
        def _eff_audit_committee(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会 ━━━\n"]
            _run_standing_items(c, res)
            res.append("📋 【重点議案・社長選択】監査等委員会設置会社への移行\n")
            pp = _pp(0.62, 0.30, 0.10 if c.governance_score >= 50 else -0.10)
            if _r.random() < pp:
                c.governance_score = min(100, c.governance_score + 15)
                c.compliance_score = min(100, c.compliance_score + 8)
                res.append(f"  🗳  賛成多数で【可決】（賛成率約{int(pp*100)}%）\n"
                           "  ✅ 監査等委員会設置会社への移行が承認されました。\n"
                           "  ▶ ガバナンス+15・コンプラ+8（コーポレートガバナンス強化として高評価）")
            else:
                c.governance_score = max(0, c.governance_score - 4)
                res.append(f"  🗳  反対多数で【否決】（賛成率{int(pp*100)}%に届かず）\n"
                           "  ❌ 「時期尚早」との意見が多数を占め否決されました。\n"
                           "  ▶ ガバナンス-4")
            ip = _pp(0.55, 0.40)
            res.append("\n📋 第2号：第三者割当増資承認")
            if _r.random() < ip:
                c.cash += 50.0
                c.investor_trust = min(100, c.investor_trust + 8)
                res.append("  🗳 【可決】 ▶ 資金+¥50M・投資家信頼+8")
            else:
                c.investor_trust = max(0, c.investor_trust - 10)
                res.append("  🗳 【否決】 ▶ 投資家信頼-10（希薄化反対）")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        def _eff_fundraise(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会 ━━━\n"]
            _run_standing_items(c, res)
            res.append("📋 【重点議案・社長選択】第三者割当増資（VC追加投資ラウンド）\n")
            pp = _pp(0.60, 0.40)
            if _r.random() < pp:
                c.cash += 60.0
                c.investor_trust = min(100, c.investor_trust + 12)
                res.append(f"  🗳  賛成多数で【可決】（賛成率約{int(pp*100)}%）\n"
                           "  ✅ 追加資金¥60Mを確保しました。\n"
                           "  ▶ 資金+¥60M・投資家信頼+12（成長資金確保を高評価）")
            else:
                c.investor_trust = max(0, c.investor_trust - 15)
                res.append(f"  🗳  反対多数で【否決】（賛成率{int(pp*100)}%に届かず）\n"
                           "  ❌ 既存株主の希薄化反対が票を制しました。\n"
                           "  ▶ 投資家信頼-15")
            gp = _pp(0.60, 0.30)
            res.append("\n📋 第2号：監査等委員会設置承認")
            if _r.random() < gp:
                c.governance_score = min(100, c.governance_score + 10)
                res.append("  🗳 【可決】 ▶ ガバナンス+10")
            else:
                res.append("  🗳 【否決】（次期再提案へ）")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        def _eff_ic_budget(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会 ━━━\n"]
            _run_standing_items(c, res)
            res.append("📋 【重点議案・社長選択】内部統制整備予算の承認\n")
            pp = _pp(0.68, 0.25)
            if _r.random() < pp:
                c.internal_control_score = min(100, c.internal_control_score + 12)
                c.accounting_quality     = min(100, c.accounting_quality + 8)
                res.append(f"  🗳  賛成多数で【可決】（賛成率約{int(pp*100)}%）\n"
                           "  ✅ 内部統制整備予算が承認されました。\n"
                           "  ▶ 内部統制+12・会計品質+8（上場審査準備に直結）")
            else:
                c.internal_control_score = max(0, c.internal_control_score - 3)
                res.append(f"  🗳  反対多数で【否決】（賛成率{int(pp*100)}%に届かず）\n"
                           "  ❌ 費用対効果への懸念で否決されました。\n"
                           "  ▶ 内部統制-3")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        return GameEvent(
            id="agm_n2",
            title=f"{plabel} 定時株主総会 — 主要議案の選択",
            description=(
                "N-2期（直前々期）の定時株主総会を迎えます。\n"
                "監査法人との契約も締結し、上場準備が本格化するこの時期、\n"
                "総会での意思決定が極めて重要な意味を持ちます。\n\n"
                "【IPO先生からのアドバイス】\n"
                "「N-2期の総会は、上場準備の核心に触れる議案を選ぶ場です。\n\n"
                "  Ａ：監査等委員会設置会社への移行\n"
                "    → 上場審査でのガバナンス評価が大幅に向上します\n"
                "    → ガバナンス60未満だと否決リスクが高まります\n"
                "  Ｂ：第三者割当増資（VC追加ラウンド）\n"
                "    → 体制整備の資金を確保できますが希薄化で否決リスクも\n"
                "  Ｃ：内部統制整備予算の承認\n"
                "    → 監査法人からの評価向上に直結します\n\n"
                "なお、社外役員が未選任の場合、株主から強い指摘が入ります。\n"
                "総会前に確認しておいてください。」"
            ),
            choices=[
                Choice(label="A. 監査等委員会設置会社への移行を重点議案とする",
                       description="上場審査でのガバナンス評価を引き上げる布石",
                       immediate_effect=_eff_audit_committee),
                Choice(label="B. 第三者割当増資（VC追加ラウンド）を重点議案とする",
                       description="体制整備の資金を確保（希薄化反対の否決リスクあり）",
                       immediate_effect=_eff_fundraise),
                Choice(label="C. 内部統制整備予算の承認を重点議案とする",
                       description="監査対応の基盤を固める投資",
                       immediate_effect=_eff_ic_budget),
            ],
        )

    # ══════════════════ N-1期 ══════════════════
    elif n_period == -1:
        def _eff_jsox_budget(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会 ━━━\n"]
            _run_standing_items(c, res)
            res.append("📋 【重点議案・社長選択】J-SOX対応費用・予算計上\n")
            pp = _pp(0.66, 0.25, 0.15 if c.internal_control_score >= 50 else -0.05)
            if _r.random() < pp:
                c.internal_control_score = min(100, c.internal_control_score + 10)
                c.compliance_score       = min(100, c.compliance_score + 6)
                res.append(f"  🗳  賛成多数で【可決】（賛成率約{int(pp*100)}%）\n"
                           "  ✅ J-SOX対応予算が承認されました。\n"
                           "  ▶ 内部統制+10・コンプラ+6（上場審査に向けた着実な進捗）")
            else:
                c.internal_control_score = max(0, c.internal_control_score - 5)
                res.append(f"  🗳  反対多数で【否決】（賛成率{int(pp*100)}%に届かず）\n"
                           "  ❌ 「費用対効果が不明確」と反発を受け否決されました。\n"
                           "  ▶ 内部統制-5（J-SOX対応遅延への懸念）")
            ep = _pp(0.58, 0.30)
            res.append("\n📋 第2号：役員体制強化（CFO・CCO選任）")
            if _r.random() < ep:
                c.governance_score = min(100, c.governance_score + 8)
                res.append("  🗳 【可決】 ▶ ガバナンス+8")
            else:
                c.governance_score = max(0, c.governance_score - 3)
                res.append("  🗳 【否決】 ▶ ガバナンス-3（役員増員コストへの反発）")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        def _eff_officer_reform(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会 ━━━\n"]
            _run_standing_items(c, res)
            res.append("📋 【重点議案・社長選択】役員体制強化（CFO・CCO選任）\n")
            pp = _pp(0.62, 0.30)
            if _r.random() < pp:
                c.governance_score = min(100, c.governance_score + 12)
                c.compliance_score = min(100, c.compliance_score + 10)
                if not c.has_cfo:
                    c.has_cfo = True
                res.append(f"  🗳  賛成多数で【可決】（賛成率約{int(pp*100)}%）\n"
                           "  ✅ 役員体制強化が承認。CFOが正式に選任されました。\n"
                           "  ▶ ガバナンス+12・コンプラ+10・CFO就任（上場審査の経営管理基準を満たす）")
            else:
                c.governance_score = max(0, c.governance_score - 5)
                res.append(f"  🗳  反対多数で【否決】（賛成率{int(pp*100)}%に届かず）\n"
                           "  ❌ 「役員報酬増加は株主価値を毀損する」として否決されました。\n"
                           "  ▶ ガバナンス-5")
            jp = _pp(0.64, 0.25)
            res.append("\n📋 第2号：J-SOX対応予算")
            if _r.random() < jp:
                c.internal_control_score = min(100, c.internal_control_score + 7)
                res.append("  🗳 【可決】 ▶ 内部統制+7")
            else:
                res.append("  🗳 【否決】（予算削減方針）")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        def _eff_disclosure_system(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会 ━━━\n"]
            _run_standing_items(c, res)
            res.append("📋 【重点議案・社長選択】適時開示体制の整備承認\n")
            pp = _pp(0.70, 0.25)
            if _r.random() < pp:
                c.has_disclosure_system = True
                c.compliance_score  = min(100, c.compliance_score + 10)
                c.investor_trust    = min(100, c.investor_trust + 8)
                res.append(f"  🗳  賛成多数で【可決】（賛成率約{int(pp*100)}%）\n"
                           "  ✅ 適時開示体制整備が承認されました。\n"
                           "  ▶ コンプラ+10・投資家信頼+8・適時開示体制 ✅")
            else:
                c.compliance_score = max(0, c.compliance_score - 3)
                res.append(f"  🗳  反対多数で【否決】（賛成率{int(pp*100)}%に届かず）\n"
                           "  ❌ 「体制構築コストが高い」として否決されました。\n"
                           "  ▶ コンプラ-3")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        return GameEvent(
            id="agm_n1",
            title=f"{plabel} 定時株主総会 — 主要議案の選択",
            description=(
                "N-1期（直前期）の定時株主総会です。\n"
                "いよいよ上場申請まで1年を切りました。この総会の選択が上場審査の合否を左右します。\n\n"
                "【IPO先生からのアドバイス】\n"
                "「N-1期の総会は、審査官が最も注目する時期の総会です。\n"
                "議案の内容と可決率が、ガバナンス成熟度の証拠として審査されます。\n\n"
                "  Ａ：J-SOX対応費用・予算計上\n"
                "    → 内部統制報告書の作成に直結。東証審査の核心テーマです\n"
                "    → 内部統制50以上なら可決確率が上がります\n"
                "  Ｂ：役員体制強化（CFO・CCO選任）\n"
                "    → CFO不在は上場審査の重大懸念事項です\n"
                "    → 可決でCFOが正式就任します\n"
                "  Ｃ：適時開示体制の整備\n"
                "    → 上場後義務となる適時開示への準備。N-1期に整備が必要です\n\n"
                "投資家信頼スコアが70未満だとVCから厳しい質問が飛んできます。\n"
                "準備は整っていますか？」"
            ),
            choices=[
                Choice(label="A. J-SOX対応費用・予算計上を重点議案とする",
                       description="東証審査の核心テーマ（内部統制報告書）に直結",
                       immediate_effect=_eff_jsox_budget),
                Choice(label="B. 役員体制強化（CFO・CCO選任）を重点議案とする",
                       description="経営管理体制を確立（可決時CFO就任）",
                       immediate_effect=_eff_officer_reform),
                Choice(label="C. 適時開示体制の整備を重点議案とする",
                       description="上場後義務となる適時開示への準備",
                       immediate_effect=_eff_disclosure_system),
            ],
        )

    # ══════════════════ N期 ══════════════════
    else:
        def _eff_strong_resolution(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会（上場審査前・最終）━━━\n"]
            _run_standing_items(c, res)
            res.append("📋 【上場決議・社長選択】事前説明を徹底して圧倒的な賛同を取り付ける\n")
            pp = _pp(0.78, 0.20, 0.12 if c.internal_control_score >= 60 else -0.10)
            if _r.random() < pp:
                c.investor_trust   = min(100, c.investor_trust + 18)
                c.governance_score = min(100, c.governance_score + 8)
                res.append(f"  🗳  賛成多数で【可決】（賛成率約{int(pp*100)}%・圧倒的支持）\n"
                           "  ✅ 上場決議が圧倒的多数で可決されました！\n"
                           "  ▶ 投資家信頼+18・ガバナンス+8\n"
                           "  💬 主幹事証券：「完璧な総会でした。審査に自信を持って臨めます。」")
            else:
                c.investor_trust        = max(0, c.investor_trust - 15)
                c.flags.total_risk_score += 8
                res.append(f"  🗳  反対票あり（賛成率{int(pp*100)}%に届かず）\n"
                           "  ❌ 一部株主が準備不足を指摘し異論が生じました。\n"
                           "  ▶ 投資家信頼-15・リスク+8\n"
                           "  💬 主幹事証券：「審査前に懸念株主への追加説明が必要です。」")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        def _eff_standard_resolution(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会（上場審査前・最終）━━━\n"]
            _run_standing_items(c, res)
            res.append("📋 【上場決議・社長選択】標準的な手続きで上場決議を進める\n")
            pp = _pp(0.68, 0.25, 0.15 if c.internal_control_score >= 60 else -0.15)
            if _r.random() < pp:
                c.investor_trust = min(100, c.investor_trust + 12)
                res.append(f"  🗳  賛成多数で【可決】（賛成率約{int(pp*100)}%）\n"
                           "  ✅ 上場決議が可決されました。東証審査へ進みます。\n"
                           "  ▶ 投資家信頼+12\n"
                           "  💬 主幹事証券：「審査官の確認事項に備えておいてください。」")
            else:
                c.investor_trust        = max(0, c.investor_trust - 18)
                c.flags.total_risk_score += 12
                res.append(f"  🗳  反対多数で【否決】（賛成率{int(pp*100)}%に届かず）\n"
                           "  ❌ 準備不足を指摘する声が多数を占めました。\n"
                           "  ▶ 投資家信頼-18・リスク+12（上場スケジュール再検討が必要）")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        def _eff_cautious_resolution(c: Company) -> str:

            res = [f"━━━ {plabel} 定時株主総会（上場審査前・最終）━━━\n"]
            _run_standing_items(c, res)
            res.append("📋 【上場決議・社長選択】少数株主への丁寧な対話でリスク管理を優先\n")
            pp = _pp(0.73, 0.22)
            if _r.random() < pp:
                c.investor_trust        = min(100, c.investor_trust + 10)
                c.compliance_score      = min(100, c.compliance_score + 6)
                c.flags.total_risk_score = max(0, c.flags.total_risk_score - 5)
                res.append(f"  🗳  賛成多数で【可決】（賛成率約{int(pp*100)}%）\n"
                           "  ✅ 上場決議が可決。少数株主の不満も払拭できました。\n"
                           "  ▶ 投資家信頼+10・コンプラ+6・リスクスコア-5\n"
                           "  💬 主幹事証券：「丁寧な株主対話が審査官にも伝わります。」")
            else:
                c.investor_trust = max(0, c.investor_trust - 10)
                res.append(f"  🗳  反対票あり（賛成率{int(pp*100)}%に届かず）\n"
                           "  ❌ 慎重な姿勢が「準備不足のシグナル」と受け取られました。\n"
                           "  ▶ 投資家信頼-10（決断力不足との批判）")
            _od_vote_in_agm(c, res)
            _secondary(c, res)
            res.append(f"\n━━━ {plabel} 定時株主総会 閉会 ━━━")
            return "\n".join(res)

        return GameEvent(
            id="agm_n0",
            title=f"{plabel} 定時株主総会 — 上場決議の進め方",
            description=(
                "いよいよN期（申請期）の定時株主総会です。\n"
                "この総会の上場決議が通れば、東証上場審査へと進みます。\n"
                "ここが上場への最後の関門です。\n\n"
                "【IPO先生からのアドバイス】\n"
                "「この上場決議の進め方が、株主・東証審査官への最終メッセージになります。\n\n"
                "  Ａ：事前説明を徹底して圧倒的な賛同を取り付ける\n"
                "    → 投資家信頼とガバナンスが大きく上昇\n"
                "    → 内部統制60以上なら可決確率がさらに上がります\n"
                "  Ｂ：標準的な手続きで上場決議を進める\n"
                "    → 可決確率は中程度。否決すると審査スケジュールに影響\n"
                "  Ｃ：少数株主への丁寧な対話でリスク管理を優先\n"
                "    → コンプライアンスとリスクスコアが改善します\n\n"
                "内部統制スコアが60以上だと審査も有利に。\n"
                "全スコアを最終確認してから決断してください！」"
            ),
            choices=[
                Choice(label="A. 事前説明を徹底して圧倒的な賛同を取り付ける",
                       description="審査官への最強の証拠となる圧倒的賛同",
                       immediate_effect=_eff_strong_resolution),
                Choice(label="B. 標準的な手続きで上場決議を進める",
                       description="シンプルに進む（否決時は審査スケジュールに影響）",
                       immediate_effect=_eff_standard_resolution),
                Choice(label="C. 少数株主への丁寧な対話を徹底してリスク管理を優先",
                       description="コンプライアンス・リスク管理を重視した堅実路線",
                       immediate_effect=_eff_cautious_resolution),
            ],
        )


# ─────────────────────────────────────────────
# イベント23: 株主総会 ― エンジェル出口要求
# ─────────────────────────────────────────────
def _agm_angel_negotiate(company: Company) -> str:
    company.investor_trust -= 5
    company.cash           -= 10.0
    return (
        "🤝 エンジェル投資家との個別交渉を設定し、現状と将来計画を説明しました。\n"
        "   「わかりました。IPOまで保有を続けます。ただし、スケジュールは厳守を。」\n"
        "   ▶ 投資家信頼-5（若干の不信感）/ 交渉費用¥10M\n"
        "   ▶ 【学習ポイント】エンジェルは感情も絡む。定期的な情報共有が信頼維持の鍵です。"
    )

def _agm_angel_secondary(company: Company) -> str:
    company.investor_trust += 10
    company.cash           -= 30.0
    return (
        "💴 セカンダリー取引を部分的に認め、エンジェルの一部持分を他VCへ譲渡しました。\n"
        "   ▶ 投資家信頼+10（出口の一部を提供）/ キャッシュ-¥30M（買取費用）\n"
        "   ▶ 【学習ポイント】セカンダリー市場での株式譲渡は資本政策の重要ツールです。"
    )

def _agm_angel_ignore(company: Company) -> str:
    company.investor_trust -= 20
    company.flags.total_risk_score += 5
    return (
        "⚠️  出口要求を無視したため、エンジェルが他の株主に不満を広めています。\n"
        "   ▶ 投資家信頼-20 / リスクスコア+5\n"
        "   ▶ 【学習ポイント】株主間の不満放置は上場審査で問題化することがあります。"
    )

EVENT_AGM_ANGEL_EXIT = GameEvent(
    id="agm_angel_exit",
    title="株主総会関係：エンジェル投資家からの出口要求",
    description=(
        "定時株主総会の直前、シード期から支援してきたエンジェル投資家・田中氏から\n"
        "緊急連絡が入りました。\n\n"
        "「社長、私はもう5年間御社を応援してきました。そろそろ私も出口が欲しい。\n"
        "IPOまで待てますが、その間に株式の一部を他の投資家に売却できませんか？\n"
        "それが無理なら、今後の投資方針を再考せざるを得ない。」\n\n"
        "【ポイント】セカンダリー取引・株主間調整は資本政策の重要課題。\n"
        "早期に対処しないと株主総会での紛糾リスクがあります。"
    ),
    choices=[
        Choice(
            label="A. 個別に交渉し、IPOまで待ってもらう（¥10M）",
            description="将来の上場益を強調し、説得する",
            immediate_effect=_agm_angel_negotiate,
            profit_hint="",
            risk_hint="不信感は残る。スケジュール遅延は厳禁",
        ),
        Choice(
            label="B. セカンダリー取引を認め、一部売却を支援する（¥30M）",
            description="他のVCへの株式譲渡を仲介・支援する",
            immediate_effect=_agm_angel_secondary,
            profit_hint="投資家信頼+10・関係改善",
            risk_hint="キャッシュ負担あり",
        ),
        Choice(
            label="C. 「今は対応できない」と先送りする",
            description="優先度が高い業務を理由に対応を保留",
            immediate_effect=_agm_angel_ignore,
            risk_hint="信頼-20・上場審査リスク",
        ),
    ],
    min_n_period=-3,
    max_n_period=-1,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント24: 株主総会 ― VCによる業績追及
# ─────────────────────────────────────────────
def _agm_vc_full_data(company: Company) -> str:
    company.investor_trust += 12
    company.accounting_quality += 5
    return (
        "📊 KPIダッシュボードと詳細な業績データを提示。質疑を乗り切りました。\n"
        "   「ここまで透明性を高めてもらえれば、我々も安心できます。」\n"
        "   ▶ 投資家信頼+12 / 会計品質+5\n"
        "   ▶ 【学習ポイント】KPIの定量管理と開示は上場企業の基本姿勢です。"
    )

def _agm_vc_vague(company: Company) -> str:
    company.investor_trust -= 8
    return (
        "😤 曖昧な説明でその場を凌ごうとしましたが、VCは納得していません。\n"
        "   「数字の根拠が弱い。次の取締役会でちゃんと説明してください。」\n"
        "   ▶ 投資家信頼-8（信頼低下）\n"
        "   ▶ 【学習ポイント】VCは数字のプロ。定性的な言い訳は逆効果です。"
    )

def _agm_vc_plan_revision(company: Company) -> str:
    company.investor_trust += 5
    company.flags.total_risk_score -= 3
    return (
        "📋 計画を修正し、保守的な予測に基づき再提示しました。\n"
        "   「現実的な計画の方が信頼できる。方向性は支持します。」\n"
        "   ▶ 投資家信頼+5 / リスクスコア-3\n"
        "   ▶ 【学習ポイント】事業計画の修正は弱さではなく、経営の誠実さの証明です。"
    )

EVENT_AGM_VC_GRILLING = GameEvent(
    id="agm_vc_grilling",
    title="株主総会関係：VCからの業績・KPI追及",
    description=(
        "株主総会で、創業期から出資しているVC・グロースキャピタルの担当者が\n"
        "厳しい質問を突きつけてきました。\n\n"
        "「社長、今期の売上はKPI比で20%未達です。\n"
        "我々は御社に期待して投資しました。このズレの原因と\n"
        "来期の具体的な改善施策を、今ここで説明してください。\n"
        "納得できなければ、取締役会での議決権行使を考えます。」\n\n"
        "【ポイント】VCは議決権を持つ株主。KPI管理と説明責任が問われます。"
    ),
    choices=[
        Choice(
            label="A. KPIダッシュボードを開示し、データで誠実に説明する",
            description="詳細な数字と改善施策を示して信頼を回復",
            immediate_effect=_agm_vc_full_data,
            profit_hint="信頼+12・会計品質+5",
        ),
        Choice(
            label="B. 「市場環境が厳しかった」と定性的に説明する",
            description="外部要因を強調してその場を乗り切る",
            immediate_effect=_agm_vc_vague,
            risk_hint="VCは数字で判断する。説明不足は信頼低下",
        ),
        Choice(
            label="C. 計画を下方修正し、保守的な新目標を提示する",
            description="現実的な計画に修正し、達成可能な目標を示す",
            immediate_effect=_agm_vc_plan_revision,
            profit_hint="リスク低減・信頼小幅回復",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
    trigger_condition=lambda c: c.investor_trust < 70,
)


# ─────────────────────────────────────────────
# イベント25: 株主総会 ― 希薄化・持分構成議論
# ─────────────────────────────────────────────
def _agm_dilution_explain(company: Company) -> str:
    company.investor_trust += 8
    return (
        "📑 資本政策の設計方針を丁寧に説明し、希薄化の合理性を理解してもらいました。\n"
        "   「社長が長期視点で考えていることはわかりました。引き続き説明を続けてください。」\n"
        "   ▶ 投資家信頼+8\n"
        "   ▶ 【学習ポイント】資本政策は一度固まると変更困難。説明と合意形成が不可欠です。"
    )

def _agm_dilution_esop(company: Company) -> str:
    company.investor_trust += 15
    company.cash -= 5.0
    return (
        "🎯 ストックオプション計画を提示し、役員・従業員のモチベーション向上策を説明。\n"
        "   「それなら上場後も一丸となって頑張れますね。賛成です。」\n"
        "   ▶ 投資家信頼+15 / ストックオプション設計費用¥5M\n"
        "   ▶ 【学習ポイント】SOは採用・リテンションの強力ツール。税制適格SOは特に有効です。"
    )

def _agm_dilution_defer(company: Company) -> str:
    company.investor_trust -= 12
    company.flags.total_risk_score += 3
    return (
        "⚠️  議論を先送りしたことで、株主間に不信感が広がりました。\n"
        "   ▶ 投資家信頼-12 / リスクスコア+3\n"
        "   ▶ 【学習ポイント】資本政策の不透明さは上場審査での重大な懸念事項になります。"
    )

EVENT_AGM_DILUTION = GameEvent(
    id="agm_dilution",
    title="株主総会関係：持分希薄化・資本政策への質問",
    description=(
        "株主総会を前に、複数の株主から資本政策について事前質問が届いています。\n\n"
        "エンジェル投資家・田中氏:\n"
        "「追加の資金調達で私たちの持分が希薄化します。\n"
        "  なぜ今のタイミングで増資が必要なのか、説明してください。」\n\n"
        "VC担当者:\n"
        "「上場時の公募株数と既存株主の売出しの比率を教えてください。\n"
        "  役員・従業員のストックオプションはどうなっていますか？」\n\n"
        "【ポイント】資本政策は一度固まると変更困難。早期の設計と説明が求められます。"
    ),
    choices=[
        Choice(
            label="A. 資本政策の方針を丁寧に説明し理解を求める",
            description="希薄化の合理性・上場後の価値向上を説明",
            immediate_effect=_agm_dilution_explain,
            profit_hint="投資家信頼+8",
        ),
        Choice(
            label="B. ストックオプション計画を提示し、全員が恩恵を受けると示す（¥5M）",
            description="SO設計を前倒しで発表し、ステークホルダーを巻き込む",
            immediate_effect=_agm_dilution_esop,
            profit_hint="信頼+15・採用力強化",
            risk_hint="費用¥5M",
        ),
        Choice(
            label="C. 「詳細は次回取締役会で」と先送りする",
            description="今は詳細を開示せず、準備を優先する",
            immediate_effect=_agm_dilution_defer,
            risk_hint="信頼-12・不透明感が高まる",
        ),
    ],
    min_n_period=-2,
    max_n_period=0,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント26: 取締役会 ― 戦略・事業計画レビュー
# ─────────────────────────────────────────────
def _board_aggressive_plan(company: Company) -> str:
    if random.random() < 0.55:
        company.revenue.recognized *= 1.20
        company.investor_trust += 10
        return (
            "📈 積極戦略が功を奏し、売上が伸長しました。\n"
            "   ▶ 売上+20% / 投資家信頼+10\n"
            "   ▶ 【学習ポイント】取締役会での大胆な意思決定が成長を引き出すことがあります。"
        )
    else:
        company.cash -= 20.0
        company.investor_trust -= 8
        return (
            "📉 積極投資が思うように回収できず、キャッシュが想定以上に減少しました。\n"
            "   ▶ キャッシュ-¥20M / 投資家信頼-8\n"
            "   ▶ 【学習ポイント】攻めの戦略はリスク管理とセットで議論すべきです。"
        )

def _board_conservative_plan(company: Company) -> str:
    company.investor_trust += 5
    company.accounting_quality += 3
    return (
        "📊 堅実な計画を承認。達成可能な目標設定で全員が納得しました。\n"
        "   ▶ 投資家信頼+5 / 会計品質+3（計画精度向上）\n"
        "   ▶ 【学習ポイント】保守的な計画は信頼性の観点で上場審査でも評価されます。"
    )

def _board_kpi_system(company: Company) -> str:
    company.internal_control_score += 8
    company.investor_trust += 7
    company.cash -= 8.0
    return (
        "📋 KPI管理ダッシュボードを導入。月次での進捗管理体制が整いました。\n"
        "   ▶ 内部統制スコア+8 / 投資家信頼+7 / 導入費用¥8M\n"
        "   ▶ 【学習ポイント】KPIの可視化は上場後の適時開示の基盤にもなります。"
    )

EVENT_BOARD_STRATEGY = GameEvent(
    id="board_strategy",
    title="取締役会：事業計画・戦略の方向性議論",
    description=(
        "取締役会にて、社外取締役の鈴木氏（元大手コンサル）から\n"
        "来期の事業戦略に関して発言がありました。\n\n"
        "「社長、中期経営計画の進捗が気になります。\n"
        "現状のKPIを見ると、売上目標には届いていますが、\n"
        "利益率の改善が遅れています。来期の戦略の方向性について、\n"
        "取締役会としての意思決定をお願いします。\n"
        "積極投資か、収益改善優先か、管理体制強化か。」\n\n"
        "【ポイント】取締役会は経営の最高意思決定機関。社長の方針が試されます。"
    ),
    choices=[
        Choice(
            label="A. 積極的な事業投資で売上を伸ばす方針を採択（成功率55%）",
            description="新規市場・人材投資で成長を加速",
            immediate_effect=_board_aggressive_plan,
            profit_hint="成功時：売上+20%・信頼+10",
            risk_hint="失敗時：キャッシュ-¥20M・信頼-8",
        ),
        Choice(
            label="B. 保守的な計画で確実な達成を優先する",
            description="達成可能なKPIを設定し、信頼性を高める",
            immediate_effect=_board_conservative_plan,
            profit_hint="信頼+5・計画精度向上",
        ),
        Choice(
            label="C. KPI管理ダッシュボードを導入し、管理体制を強化する（¥8M）",
            description="データドリブンな経営管理体制を整備",
            immediate_effect=_board_kpi_system,
            profit_hint="内部統制+8・信頼+7",
            risk_hint="費用¥8M",
        ),
    ],
    min_n_period=-3,
    max_n_period=-1,
    one_shot=False,
)


# ─────────────────────────────────────────────
# イベント27: 取締役会 ― 役員報酬制度の整備
# ─────────────────────────────────────────────
def _board_comp_performance(company: Company) -> str:
    company.investor_trust += 12
    company.internal_control_score += 5
    company.cash -= 5.0
    return (
        "📊 業績連動型報酬制度を設計・承認しました。\n"
        "   「役員が業績にコミットする仕組みは投資家から高く評価されます。」\n"
        "   ▶ 投資家信頼+12 / 内部統制+5 / 設計費用¥5M\n"
        "   ▶ 【学習ポイント】上場企業では報酬委員会の設置と業績連動報酬が標準です。"
    )

def _board_comp_fixed(company: Company) -> str:
    company.investor_trust -= 5
    return (
        "💴 固定報酬のみに留めました。短期的にはシンプルですが、\n"
        "   上場審査でガバナンスの不備として指摘される可能性があります。\n"
        "   ▶ 投資家信頼-5\n"
        "   ▶ 【学習ポイント】報酬の透明性は上場後の開示義務にも関わります。"
    )

def _board_comp_options(company: Company) -> str:
    """取締役会でSO方針を決議し、次回の株主総会に特別決議として上程準備を開始する。
    ⚖️ 会社法上、非公開会社ではSO付与そのものには株主総会の特別決議（2/3以上）が必要。
    取締役会はあくまで『上程方針の決定』にとどまり、実際の付与は総会決議後となる。"""
    # 既にSOプログラムが総会で承認済みの場合は追加設計として処理
    if getattr(company, 'has_so_program', False):
        company.investor_trust += 12
        company.cash -= 3.0
        return (
            "🎯 取締役会で追加ストックオプション（SO）の付与方針を決議しました。\n"
            "   既存のSOプログラムの枠内で、新たなキーパーソン向け付与枠の設計を開始します。\n"
            "   ▶ 投資家信頼+12 / 設計費用¥3M\n"
            "   ▶ 【実務】追加付与は既存の付与枠の範囲内で取締役会決議のみで可能。\n"
            "     枠を超える場合は再度の株主総会特別決議が必要です。"
        )
    else:
        # 総会未承認 → 次回総会への上程準備として処理（付与は発生しない）
        company.investor_trust += 8
        company.cash -= 2.0
        company.has_so_program = False   # 付与枠はまだ確定していない
        return (
            "📋 取締役会でストックオプション（SO）付与プログラムの方針を決議しました。\n"
            "   ただし、⚖️ 非公開会社では役員・従業員へのSO付与には\n"
            "   株主総会の特別決議（議決権の2/3以上）が必要です（会社法238条・309条2項）。\n\n"
            "   本決議は『次回の定時株主総会への上程方針』の確認にとどまります。\n"
            "   付与枠・行使条件の上限を総会に付議し、可決された後に\n"
            "   具体的な付与先・時期は取締役会で決定（委任）できます（最長1年）。\n\n"
            "   ▶ 投資家信頼+8 / 準備費用¥2M\n"
            "   ▶ 次回の定時株主総会で特別決議として上程予定です。\n"
            "   ▶ 【学習ポイント】SOは行使後に初めて株主となるため、\n"
            "     上場審査の実株主数要件（グロース150名等）には直接カウントされません。"
        )

EVENT_BOARD_COMPENSATION = GameEvent(
    id="board_compensation",
    title="取締役会：役員報酬・インセンティブ制度の設計",
    description=(
        "社外取締役の鈴木氏から役員報酬について提議がありました。\n\n"
        "「社長、上場を目指すにあたり、役員報酬の設計が\n"
        "ガバナンスの観点から重要な課題です。\n"
        "現在は社長の判断で固定報酬のみですが、\n"
        "業績連動型報酬やストックオプションの導入を\n"
        "取締役会として議論すべきではないでしょうか。\n"
        "投資家からも透明性ある報酬体系を求められています。」\n\n"
        "【ポイント】役員報酬の透明性・業績連動性は上場審査の重要チェック項目です。"
    ),
    choices=[
        Choice(
            label="A. 業績連動型報酬制度を設計・導入する（¥5M）",
            description="KPI達成に連動した報酬体系を整備",
            immediate_effect=_board_comp_performance,
            profit_hint="信頼+12・ガバナンス強化",
            risk_hint="設計費用¥5M",
        ),
        Choice(
            label="B. 現状の固定報酬を維持し、シンプルな体系を継続する",
            description="変更コストを抑え、現状維持を選択",
            immediate_effect=_board_comp_fixed,
            risk_hint="ガバナンス指摘リスク",
        ),
        Choice(
            label="C. ストックオプション（SO）方針を決議し、次回株主総会に特別決議として上程する",
            description="SO付与には株主総会の特別決議（2/3以上）が必要。今期は上程方針を固める",
            immediate_effect=_board_comp_options,
            profit_hint="信頼+8〜12・長期インセンティブ設計",
            risk_hint="総会否決リスクあり・付与は総会承認後",
        ),
    ],
    min_n_period=-2,
    max_n_period=0,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント28: 監査役 ― 内部統制の重大指摘
# ─────────────────────────────────────────────
def _kansayaku_immediate_fix(company: Company) -> str:
    company.internal_control_score += 15
    company.cash -= 12.0
    return (
        "🔧 監査役の指摘を真摯に受け止め、内部統制の整備を緊急実施しました。\n"
        "   ▶ 内部統制スコア+15 / 整備費用¥12M\n"
        "   ▶ 【学習ポイント】監査役の指摘事項を放置すると監査意見に影響します。\n"
        "     早期対応が上場審査でのプラス評価につながります。"
    )

def _kansayaku_partial_fix(company: Company) -> str:
    company.internal_control_score += 6
    company.cash -= 5.0
    return (
        "⚠️  重要な指摘項目のみ対処し、軽微な項目は次期に先送りしました。\n"
        "   ▶ 内部統制スコア+6 / 費用¥5M\n"
        "   ▶ 【学習ポイント】監査役は毎期の改善状況を追跡します。\n"
        "     先送りした項目は次期に再指摘されるリスクがあります。"
    )

def _kansayaku_ignore(company: Company) -> str:
    company.internal_control_score -= 10
    company.flags.total_risk_score += 8
    company.auditor_trust -= 15
    return (
        "❌ 監査役の指摘を軽視したため、監査役の信頼が大きく低下しました。\n"
        "   ▶ 内部統制スコア-10 / リスクスコア+8 / 監査人信頼-15\n"
        "   ▶ 【学習ポイント】監査役は法的に独立した機関。指摘の無視は上場審査で致命的です。"
    )

EVENT_KANSAYAKU_REPORT = GameEvent(
    id="kansayaku_report",
    title="監査役からの内部統制に関する重大指摘",
    description=(
        "常勤監査役・佐藤氏から緊急の報告書が提出されました。\n\n"
        "「社長、今期の監査において以下の問題を確認しました。\n"
        " ① 経費精算の承認フローが機能していない部門がある\n"
        " ② 一部の契約書に代表者印以外の印章が使用されている\n"
        " ③ システムアクセス権限の棚卸が実施されていない\n\n"
        "これらは内部統制上の重大な懸念事項です。\n"
        "上場審査でも必ず問われる項目です。至急、改善策をご指示ください。」\n\n"
        "【ポイント】監査役は取締役の職務執行を監査する法的機関。報告は無視できません。"
    ),
    choices=[
        Choice(
            label="A. 全指摘事項を緊急対処する（¥12M）",
            description="全ての指摘に対して改善計画を立案・即実施",
            immediate_effect=_kansayaku_immediate_fix,
            profit_hint="内部統制+15・上場審査への信頼性確保",
            risk_hint="費用¥12M",
        ),
        Choice(
            label="B. 重要な指摘のみ優先対処する（¥5M）",
            description="リスク高の項目のみ対処し、軽微項目は次期",
            immediate_effect=_kansayaku_partial_fix,
            profit_hint="内部統制+6",
            risk_hint="残存リスクあり・再指摘の可能性",
        ),
        Choice(
            label="C. 「対処中」と回答し、実質的に先送りする",
            description="忙しいことを理由に形式的な回答のみ",
            immediate_effect=_kansayaku_ignore,
            risk_hint="内部統制-10・信頼大幅低下・上場審査リスク",
        ),
    ],
    min_n_period=-2,
    max_n_period=0,
    one_shot=False,
    trigger_condition=lambda c: c.internal_control_score < 60,
)


# ─────────────────────────────────────────────
# イベント29: 監査役 ― 監査役の独立性問題
# ─────────────────────────────────────────────
def _kansayaku_independent(company: Company) -> str:
    company.investor_trust += 15
    company.internal_control_score += 8
    company.cash -= 10.0
    return (
        "✅ 独立した外部専門家を常勤監査役として選任しました。\n"
        "   「弁護士・公認会計士が監査役に就任することで、\n"
        "   上場審査でのガバナンス評価が大きく向上します。」\n"
        "   ▶ 投資家信頼+15 / 内部統制+8 / 採用費用¥10M\n"
        "   ▶ 【学習ポイント】東証は監査役の独立性を厳格に審査します。\n"
        "     社内出身者だけの監査役会は問題視されます。"
    )

def _kansayaku_social(company: Company) -> str:
    company.investor_trust += 5
    company.cash -= 5.0
    return (
        "👥 知人の弁護士に非常勤監査役として就任してもらいました。\n"
        "   完全な独立性には疑問が残りますが、形式要件は満たします。\n"
        "   ▶ 投資家信頼+5 / 費用¥5M\n"
        "   ▶ 【学習ポイント】監査役の実質的な独立性が重要。\n"
        "     知人・元社員では審査で指摘を受ける可能性があります。"
    )

def _kansayaku_status_quo(company: Company) -> str:
    company.investor_trust -= 15
    company.flags.total_risk_score += 10
    return (
        "❌ 独立した監査役を選任せず、現状の体制を維持しました。\n"
        "   ▶ 投資家信頼-15 / リスクスコア+10\n"
        "   ▶ 【学習ポイント】監査役の独立性は形式要件。\n"
        "     上場申請前に必ず解決が必要な問題です。"
    )

EVENT_KANSAYAKU_INDEPENDENCE = GameEvent(
    id="kansayaku_independence",
    title="監査役の独立性問題：社外監査役の選任",
    description=(
        "主幹事証券会社の担当者から連絡がありました。\n\n"
        "「社長、上場審査に向けて監査役体制を確認させてください。\n"
        "現在、監査役は全員が創業期からの社内関係者と聞いています。\n"
        "東証の上場審査では、独立した社外監査役の選任が\n"
        "実質的に求められます。\n"
        "特に、弁護士や公認会計士などの専門家を\n"
        "独立した立場で選任することが重要です。\n"
        "このままでは審査で大きな問題になる可能性があります。」\n\n"
        "【ポイント】監査役の独立性は上場審査の実質要件。早期対応が必須です。"
    ),
    choices=[
        Choice(
            label="A. 独立した外部専門家（弁護士/公認会計士）を監査役に選任（¥10M）",
            description="完全に独立した専門家を常勤監査役として迎える",
            immediate_effect=_kansayaku_independent,
            profit_hint="信頼+15・ガバナンス大幅強化",
            risk_hint="費用¥10M",
        ),
        Choice(
            label="B. 知人の弁護士に非常勤監査役を依頼する（¥5M）",
            description="ネットワーク経由で弁護士に就任してもらう",
            immediate_effect=_kansayaku_social,
            profit_hint="形式要件は満たす",
            risk_hint="実質的独立性に疑問・審査で指摘リスク",
        ),
        Choice(
            label="C. 現状の監査役体制を維持する",
            description="コスト優先で現状維持",
            immediate_effect=_kansayaku_status_quo,
            risk_hint="信頼-15・審査リスク+10",
        ),
    ],
    min_n_period=-2,
    max_n_period=0,
    one_shot=True,
    trigger_condition=lambda c: c.flags.no_outside_director and not getattr(c, 'agm_deferred_outside_director', False),
)


# ─────────────────────────────────────────────
# イベント30: ストックオプション（SO）プログラム
# ─────────────────────────────────────────────
# 非公開会社（譲渡制限会社）では役員・従業員いずれのSO付与も
# 会社法238条・309条2項により株主総会の特別決議が原則必要。
# このイベントは「取締役会での方針決定→総会上程準備」として設計。
# 総会委任（1年有効）の枠内で付与条件を取締役会が決定できるが、
# 枠の設定自体は総会特別決議が前提となる。

def _so_broad_program(company: Company) -> str:
    import random as _r
    added = 70
    company.potential_shareholders += added   # SOは潜在株主。実株主ではない
    company.employee_morale        += 15
    company.cash                   -= 5.0
    approved = _r.random() < 0.75
    agm_result = "承認されました" if approved else "一部VC株主の希薄化懸念で否決されました"
    if approved:
        company.has_so_program = True   # SO付与枠が総会で可決済み
    return (
        "🗳️ 取締役会でSOプログラム（全社員・役員対象）の方針を決議し、株主総会に特別決議として上程しました。\n"
        f"   総会結果：{agm_result}。\n"
        f"   承認後、{added}名へのSO付与枠を設定（潜在株主数 +{added}）。\n"
        "   ▶ 潜在株主数 +70 / 従業員士気+15 / 設計・登記費用¥5M\n"
        "   ▶ 【実務】非公開会社では役員・従業員向けSOともに株主総会の特別決議（2/3以上）が原則必要（会社法238条・309条2項）。\n"
        "     総会で付与枠・条件の上限を決議し、具体的付与先・時期の決定を取締役会に委任できます（委任期間：最長1年）。\n"
        "     SOは行使されて初めて株主となるため、上場審査の実株主数要件には直接カウントされません。"
    )

def _so_management_only(company: Company) -> str:
    import random as _r
    added = 25
    company.potential_shareholders += added   # SOは潜在株主。実株主ではない
    company.investor_trust         += 8
    company.cash                   -= 3.0
    approved = _r.random() < 0.82
    agm_result = "承認されました" if approved else "否決されました（希薄化懸念）"
    if approved:
        company.has_so_program = True   # SO付与枠が総会で可決済み
    return (
        "🗳️ 取締役会でSOプログラム（役員・マネージャー層対象）の方針を決議し、株主総会に特別決議として上程しました。\n"
        f"   総会結果：{agm_result}。\n"
        f"   承認後、上位管理職{added}名へのSO付与枠を設定（潜在株主数 +{added}）。\n"
        "   ▶ 潜在株主数 +25 / 投資家信頼+8 / 費用¥3M\n"
        "   ▶ 【実務】非公開会社では役員・従業員向けSOともに株主総会の特別決議が原則必要（会社法238条・309条2項）。\n"
        "     対象者が限定的なため希薄化への反対は少なく、可決しやすい設計です。\n"
        "     SOは実株主ではないため上場審査の株主数要件に直接貢献しません。"
    )

def _so_skip(company: Company) -> str:
    company.employee_morale -= 5
    return (
        "⏭️  今回はSOプログラムの総会上程を見送りました。\n"
        "   ▶ 従業員士気-5（インセンティブを期待していた社員の失望）\n"
        "   ⚠  人材定着リスクが高まります。次期以降の株主総会で再検討が必要です。"
    )

EVENT_SO_PROGRAM = GameEvent(
    id="so_program",
    title="ストックオプション（SO）プログラムの設計・総会上程準備",
    description=(
        "CFOからの提案：「役員・従業員へのインセンティブ設計が急務です。\n"
        "ストックオプション（SO）は長期インセンティブとして有効ですが、\n"
        "注意点があります。SOは行使されて初めて株主となるため、\n"
        "上場審査の実株主数要件（グロース150名等）には直接カウントされません。\n"
        "実株主数を増やすには、別途『従業員持株会』の設立が必要です。\n\n"
        "⚖️ 法的手続き：当社は非公開会社（譲渡制限会社）のため、\n"
        "役員・従業員いずれへのSO付与も株主総会の特別決議（2/3以上）が原則必要です。\n"
        "今回の取締役会では『どの規模で総会に上程するか』の方針を決定します。」\n\n"
        "【実務ポイント】税制適格SOは上場後行使が原則。\n"
        "総会で付与枠の上限・条件を承認後、具体的付与先は取締役会に委任（最長1年）できます。"
    ),
    choices=[
        Choice(
            label="A. 全社員・役員を対象とした広範なSO計画を総会に上程（設計費¥5M）",
            description="人材定着・モチベーション向上を優先。実株主数は別途確保が必要",
            immediate_effect=_so_broad_program,
            profit_hint="潜在株主数+70・従業員士気+15",
            risk_hint="費用¥5M・総会での希薄化懸念・実株主数への直接効果なし",
        ),
        Choice(
            label="B. 役員・マネージャー層のみのSO計画を総会に上程（設計費¥3M）",
            description="主要人材への集中付与でコスト効率重視。希薄化が限定的で可決しやすい",
            immediate_effect=_so_management_only,
            profit_hint="潜在株主数+25・信頼+8",
            risk_hint="費用¥3M・実株主数への直接効果なし",
        ),
        Choice(
            label="C. 今回はSOプログラムの総会上程を見送る",
            description="コストと複雑性を避けて先送り",
            immediate_effect=_so_skip,
            risk_hint="インセンティブ不足・士気低下リスク",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント30b: 従業員持株会の設立
# ─────────────────────────────────────────────
def _esop_establish(company: Company) -> str:
    company.cash          -= 3.0
    company.has_esop       = True
    company.employee_morale += 8
    return (
        "🏢 従業員持株会を設立しました。社員が毎月一定額を積み立て現物株を取得します。\n"
        "   ▶ 設立費用¥3M / 従業員士気+8\n"
        "   ▶ 毎四半期、持株会を通じた実株主が少しずつ増加します。\n"
        "   ▶ 【実務】持株会は現物株取得のため上場審査の実株主数に直接カウントされます。\n"
        "     一気に増えるわけではなく、毎月の積立で着実に積み上がります。"
    )

def _esop_skip(company: Company) -> str:
    return (
        "⏭️  従業員持株会の設立を見送りました。\n"
        "   ▶ 実株主数の積み上げはロードショーや増資ラウンドに依存することになります。"
    )

EVENT_ESOP = GameEvent(
    id="esop_setup",
    title="従業員持株会の設立",
    description=(
        "CFO：「上場審査の実株主数要件を充足するため、従業員持株会の設立を提案します。\n"
        "持株会では社員が毎月一定額を積み立て、現物株を取得します。\n"
        "ストックオプションと異なり、持株会員は即座に実株主となるため、\n"
        "上場審査の形式要件（株主数）に直接カウントされます。\n"
        "一気に増えるわけではなく、毎月コツコツと積み上がります。\n\n"
        "【実務ポイント】持株会はN-2期以降に設立すれば、\n"
        "上場審査時までに数十名規模の実株主を着実に確保できます。"
    ),
    choices=[
        Choice(
            label="A. 従業員持株会を設立する（¥3M）",
            description="現物株の毎月積立で実株主を着実に積み上げる王道ルート",
            immediate_effect=_esop_establish,
            profit_hint="毎Q+3名の実株主増加・士気+8",
            risk_hint="費用¥3M・管理運営コスト",
        ),
        Choice(
            label="B. 今回は設立しない",
            description="コストと手続きを避けて先送り",
            immediate_effect=_esop_skip,
            risk_hint="実株主数の積み上げが遅れる",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント30c: N期 SO上場前行使（潜在株主が実株主へ）
# ─────────────────────────────────────────────
def _n_so_exercise_allow(company: Company) -> str:
    pot = getattr(company, 'potential_shareholders', 0)
    if pot > 0:
        # 税制リスクを許容できる役職員のみ ≒ 潜在株主の約12%
        exercised = max(3, int(pot * 0.12))
        company.shareholder_count      += exercised
        company.potential_shareholders  = max(0, pot - exercised)
        company.cash                   -= 1.0
        return (
            f"📋 {exercised}名の役職員が上場前にSOを行使し、正式な株主となりました。\n"
            f"   ▶ 実株主数 +{exercised} / 潜在株主数 -{exercised}\n"
            "   ▶ 【実務】上場前SO行使は税制非適格SOや行使期間到来のSO保有者のみ可能。\n"
            "     行使価額での払込が必要なため、自己資金のある一部の役職員に限られます。"
        )
    return "📋 SO保有者（潜在株主）がいないため、上場前行使は行われませんでした。"

def _n_so_exercise_decline(company: Company) -> str:
    return (
        "⏭️  上場前のSO行使は推奨せず、全員上場後の行使を案内しました。\n"
        "   ▶ 上場後に株価が確定してから行使するため、税制面でも有利です。"
    )

EVENT_N_SO_EXERCISE = GameEvent(
    id="n_so_exercise",
    title="上場前ストックオプション行使の判断（N期）",
    description=(
        "主幹事担当者：「N期に入り、一部役職員から上場前にSOを行使したいとの申し出があります。\n"
        "上場後は株価変動リスクがあるため、現在の価格で確実に取得したいとのことです。\n\n"
        "ただし、税制適格SOは原則として上場後の行使です。\n"
        "上場前に行使できるのは、税制リスクを理解した一部の役職員のみとなります。\n"
        "行使により実株主数が増加し、上場審査の株主数要件の充足に貢献します。」"
    ),
    choices=[
        Choice(
            label="A. 希望する役職員のSO行使を許可する",
            description="税制リスクを理解した役職員のみ行使可。実株主数が増加",
            immediate_effect=_n_so_exercise_allow,
            profit_hint="実株主数増加（潜在株主の約12%）",
            risk_hint="費用¥1M・税制リスクは行使者負担",
        ),
        Choice(
            label="B. 上場後の行使を推奨し、今回は認めない",
            description="税制面で有利な上場後行使を全員に推奨",
            immediate_effect=_n_so_exercise_decline,
            risk_hint="実株主数が増えず、株主数要件充足が遅れる可能性",
        ),
    ],
    trigger_condition=lambda c: getattr(c, 'potential_shareholders', 0) > 0,
    min_n_period=0,
    max_n_period=0,
    one_shot=True,
)


# ─────────────────────────────────────────────
# イベント31: シリーズB/C 大型ファイナンス
# ─────────────────────────────────────────────
def _series_bc_institutional(company: Company) -> str:
    result = raise_funding(
        company,
        "シリーズB",
        800.0,
        5000.0,
        "機関投資家連合（シリーズB）",
        shareholder_boost=180,
    )
    company.investor_trust += 20
    company.market_cap_million = max(company.market_cap_million, 5000.0)
    return (
        f"🏦 {result}\n"
        "   機関投資家・年金ファンド・事業会社から広く資金調達に成功！\n"
        "   ▶ 時価総額評価が最低¥5,000Mに引き上げられました\n"
        "   ▶ 投資家信頼+20\n"
        "   ▶ 【実務】大型ラウンドには機関投資家DD（デューデリジェンス）が入ります。\n"
        "     財務・法務・事業DD対応が上場審査の予行演習にもなります。"
    )

def _series_bc_targeted(company: Company) -> str:
    result = raise_funding(
        company,
        "シリーズB（選択的調達）",
        500.0,
        4000.0,
        "戦略投資家・CVC（シリーズB）",
        shareholder_boost=80,
    )
    company.investor_trust += 12
    return (
        f"💼 {result}\n"
        "   戦略パートナー・CVC中心の選択的ファイナンス。\n"
        "   ▶ 投資家信頼+12\n"
        "   ⚠  株主数の増加は限定的です。追加の株主確保策が必要かもしれません。"
    )

def _series_bc_skip(company: Company) -> str:
    company.investor_trust -= 8
    return (
        "⏭️  シリーズBラウンドを見送りました。\n"
        "   ▶ 投資家信頼-8（成長意欲に疑問符）\n"
        "   ⚠  株主数・時価総額の要件充足が難しくなる可能性があります。"
    )

EVENT_SERIES_BC = GameEvent(
    id="series_bc_fundraising",
    title="シリーズB 大型ファイナンスの実施",
    description=(
        "主幹事証券会社からの連絡：「上場審査に向けて、流通株式時価総額と\n"
        "財務基盤の強化が重要です。\n"
        "シリーズBラウンドで機関投資家・年金ファンドを招くことで、\n"
        "時価総額評価の向上と資金調達が同時に実現できます。\n"
        "なお、上場審査の株主数要件は上場時の公募・売出しで充足するため、\n"
        "プレIPOラウンドでの株主数は補完的な役割にとどまります。」\n\n"
        "【ポイント】上場審査では流通株式時価総額（グロース¥500M以上、\n"
        "スタンダード¥1,000M以上、プライム¥10,000M以上）が厳しく審査されます。"
    ),
    choices=[
        Choice(
            label="A. 機関投資家・年金ファンドを広く呼び込む大型ラウンド（¥800M調達）",
            description="広範な機関投資家参加で株主数+180・時価総額評価アップ",
            immediate_effect=_series_bc_institutional,
            profit_hint="株主数+180・時価総額¥5,000M保証・信頼+20",
            risk_hint="希薄化大・機関投資家DDの負担",
        ),
        Choice(
            label="B. 戦略パートナー・CVCを中心に選択的に調達（¥500M）",
            description="関係性重視のファイナンス。希薄化を抑えつつ調達",
            immediate_effect=_series_bc_targeted,
            profit_hint="株主数+80・戦略シナジー",
            risk_hint="株主数増加が少ない",
        ),
        Choice(
            label="C. 今回のラウンドは見送る",
            description="既存資金で上場を目指す",
            immediate_effect=_series_bc_skip,
            risk_hint="株主数・時価総額要件の未達リスク",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
    # trigger_condition なし → N-2〜N-1期に必ず発火（株主数確保のため）
)


# ─────────────────────────────────────────────
# イベント32: ロードショー（会社が魅力を示す；主幹事が需要を集める）
# ─────────────────────────────────────────────
def _roadshow_full(company: Company) -> str:
    company.investor_trust     += 25
    company.market_cap_million *= 1.20
    company.cash               -= 20.0
    return (
        "📣 主幹事の販売網を通じた国内外ロードショーを充実させました。\n"
        "   社長自らが事業計画・成長ストーリーを投資家に直接説明。需要は非常に旺盛です。\n"
        "   ▶ 投資家信頼+25 / 時価総額+20%（ブックビルディング需要強化）/ 費用¥20M\n"
        "   ▶ 【実務】会社の役割：事業の魅力を示すこと。\n"
        "     主幹事の役割：販売網で需要を集め、1人1単元ずつ配分し株主を形成すること。"
    )

def _roadshow_domestic(company: Company) -> str:
    company.investor_trust     += 15
    company.market_cap_million *= 1.10
    company.cash               -= 10.0
    return (
        "📣 主幹事主導の国内機関投資家向けロードショーに経営陣が参加しました。\n"
        "   国内需要を確認。ブックビルディングの公開価格目線が固まりました。\n"
        "   ▶ 投資家信頼+15 / 時価総額+10% / 費用¥10M\n"
        "   ▶ プライム市場ではグローバル機関投資家への説明も求められます。"
    )

def _roadshow_minimal(company: Company) -> str:
    company.investor_trust     += 3
    company.flags.total_risk_score += 5
    company.cash               -= 3.0
    return (
        "📣 経営陣の参加が限定的で、ロードショーは主幹事任せになりました。\n"
        "   ▶ 投資家信頼+3 / 費用¥3M / リスクスコア+5\n"
        "   ⚠  需要喚起が不十分だとブックビルディングで希望価格を下回り、\n"
        "     公開価格の引き下げや上場後の株価低迷につながります。"
    )

EVENT_PREIPO_ROADSHOW = GameEvent(
    id="preipo_roadshow",
    title="ロードショー・投資家への事業説明（上場需要喚起）",
    description=(
        "主幹事証券会社からの報告がありました。\n\n"
        "「社長、いよいよロードショーの実施段階です。\n"
        "会社側の役割は、事業計画・成長ストーリー・財務見通しを\n"
        "投資家に魅力的に伝えることです。\n"
        "需要喚起・配分・株主形成は当社（主幹事）が販売網を通じて行います。\n\n"
        "なお、上場審査の株主数要件はロードショー後の公募・売出しで充足します。\n"
        "申請時点の株主数が少ないのは通例であり、上場日時点の見込み数で判定されます。\n"
        "会社が自ら投資家を個別に勧誘することは金融商品取引法上の制約があるため、\n"
        "主幹事の販売網に委ねるのが原則です。」\n\n"
        "【学習ポイント】会社＝「魅力を示す主体」、主幹事＝「販売・株主形成の主体」。\n"
        "経営陣のロードショーへの真剣な取り組みが公開価格・初値に直結します。"
    ),
    choices=[
        Choice(
            label="A. 経営陣全員参加。国内外フルスケールのロードショーで需要を最大化（¥20M）",
            description="会社の魅力を最大限にアピール。主幹事の需要集めをバックアップ",
            immediate_effect=_roadshow_full,
            profit_hint="信頼+25・時価総額+20%（公開価格最大化）",
            risk_hint="費用¥20M・経営陣の負担大",
        ),
        Choice(
            label="B. 国内機関投資家中心にコンパクトに実施（¥10M）",
            description="コスト効率重視。国内需要を確認して公開価格を固める",
            immediate_effect=_roadshow_domestic,
            profit_hint="信頼+15・時価総額+10%",
            risk_hint="海外投資家へのアプローチが薄い",
        ),
        Choice(
            label="C. 経営陣の参加を最小限にとどめ、主幹事に任せる（¥3M）",
            description="コスト最優先。ただし需要喚起が弱まるリスクがある",
            immediate_effect=_roadshow_minimal,
            risk_hint="需要不足・公開価格低下・上場後株価低迷リスク",
        ),
    ],
    min_n_period=-1,
    max_n_period=0,
    one_shot=True,
    trigger_condition=lambda c: c.has_underwriter,   # 主幹事選定済みの場合のみ発火
)


# ─────────────────────────────────────────────
# イベント32b: 公募・売出し規模の主幹事との協議（N期）
# 株主数要件は主幹事が配分設計することで上場日に充足される
# ─────────────────────────────────────────────
def _offering_large(company: Company) -> str:
    # 大規模公募：実務では最低要件の数倍となるよう設計
    added = random.randint(900, 1300)
    company.shareholder_count  += added
    company.investor_trust     += 15
    company.market_cap_million *= 1.12
    company.cash               -= 8.0   # 手数料・目論見書等の費用
    return (
        f"🎉 主幹事と協議の上、流動性を最大化する大規模公募・売出しに合意しました。\n"
        f"   主幹事の販売網を通じ、{added}名の個人投資家に1人1単元（100株）ずつ配分。\n"
        f"   名寄せ後も株主数要件を大きく上回る見込みです。\n"
        f"   ▶ 上場日実株主数 +{added}名 / 投資家信頼+15 / 時価総額+12%\n"
        f"   ▶ 【実務】株主数要件は上場日見込み数で判定。主幹事が配分設計し、\n"
        f"     公募で{added//2}名・既存株主売出しで残りを充足するのが通例です。\n"
        f"     定款で単元株式数100株を定めることが東証の原則です。"
    )

def _offering_standard(company: Company) -> str:
    added = random.randint(450, 700)
    company.shareholder_count  += added
    company.investor_trust     += 8
    company.market_cap_million *= 1.06
    company.cash               -= 4.0
    return (
        f"📣 主幹事推奨の標準規模で公募・売出しを実施することに合意しました。\n"
        f"   主幹事の販売網を通じ、{added}名の個人投資家に1人1単元ずつ配分。\n"
        f"   ▶ 上場日実株主数 +{added}名 / 投資家信頼+8 / 時価総額+6%\n"
        f"   ▶ 【実務】実務では最低要件を大きく上回るよう公募・売出株数を設計。\n"
        f"     特定少数への偏在を避け、上場後の流通性を確保するのが主幹事の責務です。"
    )

def _offering_small(company: Company) -> str:
    added = random.randint(100, 180)
    company.shareholder_count  += added
    company.investor_trust     -= 5
    company.flags.total_risk_score += 10
    company.cash               -= 1.0
    return (
        f"⚠️  希薄化懸念を優先し、主幹事の推奨より小規模な公募・売出しを選択しました。\n"
        f"   {added}名への配分にとどまります。\n"
        f"   ▶ 上場日実株主数 +{added}名 / 投資家信頼-5 / リスクスコア+10\n"
        f"   ⚠  グロース150名はかろうじて充足できますが、\n"
        f"     スタンダード400名・プライム800名は達成困難です。\n"
        f"   ⚠  流動性が低く上場後の株価が不安定になりやすい。\n"
        f"     主幹事から「上場後の流通性が懸念される」と指摘を受けました。"
    )

EVENT_PUBLIC_OFFERING = GameEvent(
    id="public_offering",
    title="主幹事との公募・売出し規模の協議（株主数充足の本丸）",
    description=(
        "主幹事証券会社から、公募・売出しの規模設計について協議の申し入れがありました。\n\n"
        "「社長、上場申請後から上場日前日までに公募・売出しを実施することで、\n"
        "上場審査の株主数要件（上場日における見込み数）を充足します。\n\n"
        "当社（主幹事）の販売網を通じて個人投資家・機関投資家に配分し、\n"
        "1人1単元（100株）の購入を基本として広く株主を形成します。\n"
        "名寄せ後の株主数・特定少数への偏在回避・上場後の流通性を\n"
        "考慮して配分設計するのが主幹事の責務です。\n\n"
        "会社が自ら投資家を勧誘することは金融商品取引法上の制約がありますが、\n"
        "希薄化を抑えつつ十分な流通性を確保するために、\n"
        "公募・売出しの規模について社長と協議したいと思います。」\n\n"
        "【学習ポイント】会社＝「公募規模・条件を主幹事と協議する主体」\n"
        "主幹事＝「販売・配分を行い株主数要件を実現する主体」"
    ),
    choices=[
        Choice(
            label="A. 主幹事推奨：流動性・知名度を最大化する大規模配分に合意する",
            description="最低要件の数倍の株主を形成。上場後の株価安定・流動性を重視",
            immediate_effect=_offering_large,
            profit_hint="実株主数+900〜1300名・信頼+15・時価総額+12%",
            risk_hint="希薄化大（既存株主持分が薄まる）",
        ),
        Choice(
            label="B. バランス重視の標準規模で実施することに合意する",
            description="要件充足と希薄化のバランスを主幹事と協議して決定",
            immediate_effect=_offering_standard,
            profit_hint="実株主数+450〜700名・信頼+8",
            risk_hint="プライム市場では株主数がギリギリの可能性",
        ),
        Choice(
            label="C. 希薄化を最小化するよう主幹事に要請し、小規模公募に絞る",
            description="既存株主の持分を守るが、主幹事から流通性懸念の指摘あり",
            immediate_effect=_offering_small,
            risk_hint="株主数・流動性不足・スタンダード/プライムでは要件未達リスク",
        ),
    ],
    min_n_period=0,
    max_n_period=0,
    one_shot=True,
)


# ═════════════════════════════════════════════════════════════
# 【IPO実務検定試験 準拠】追加イベント群
# ── 倫理・社会的責任／コンプライアンス／市場別上場審査基準／資本政策 ──
# ═════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────
# 追加イベント①: 市場区分の選択（プライム/スタンダード/グロース）
# ─────────────────────────────────────────────
def _aim_prime(company: Company) -> str:
    company.flags.total_risk_score += 15  # 要件ハードルが高い
    company.investor_trust += 15
    company.governance_score += 10
    company.market_cap_million *= 1.10
    return ("🏆 プライム市場を目指す戦略を決定しました。\n"
            f"   流通株式時価総額100億円以上・株主数800名以上・\n"
            f"   英文開示・独立社外取締役1/3以上など高水準の要件に挑戦。\n"
            f"   時価総額+10% / ガバナンス+10 / 投資家信頼+15\n"
            f"   ⚠️  要件未達リスク大（リスクスコア+15）\n"
            f"   ▶ 実務: プライムは『グローバル投資家との建設的対話』が要求されます。")


def _aim_standard(company: Company) -> str:
    company.investor_trust += 8
    company.governance_score += 5
    return ("📊 スタンダード市場を目指す戦略を決定しました。\n"
            f"   流通株式時価総額10億円以上・株主数400名以上・\n"
            f"   公開性と信頼性を確保した中堅企業向け区分。\n"
            f"   ガバナンス+5 / 投資家信頼+8\n"
            f"   ▶ 実務: 2022年の市場再編で『安定的な事業基盤』を重視する位置付けに。")


def _aim_growth(company: Company) -> str:
    company.investor_trust += 5
    company.market_cap_million *= 0.95  # 評価倍率控えめ
    return ("🚀 グロース市場を目指す戦略を決定しました。\n"
            f"   時価総額5億円以上・株主数150名以上・高い成長可能性が要件。\n"
            f"   時価総額評価▲5%だが早期上場が可能。\n"
            f"   投資家信頼+5\n"
            f"   ▶ 実務: 事業計画と進捗状況の継続開示義務があります。")


EVENT_MARKET_SELECTION = GameEvent(
    id="market_selection",
    title="上場市場区分の選択（プライム/スタンダード/グロース）",
    description=(
        "主幹事証券会社から質問がありました:\n"
        "「2022年の市場再編後、東証は『プライム』『スタンダード』『グロース』の\n"
        "3区分となりました。御社はどの市場を目指されますか？\n"
        "市場によって形式要件・実質審査基準・その後の維持コストが大きく異なります。」\n"
        "【IPO実務検定】市場区分の選択は資本政策・ガバナンス・IR体制を決める出発点です。"
    ),
    choices=[
        Choice(
            label="A. プライム市場（株主数800名・時価総額100億円以上）",
            description="グローバル投資家向け最上位市場",
            immediate_effect=_aim_prime,
            profit_hint="信頼+15・時価総額+10%",
            risk_hint="要件ハードル大・リスク+15",
        ),
        Choice(
            label="B. スタンダード市場（株主数400名・時価総額10億円以上）",
            description="中堅実績企業向けの安定区分",
            immediate_effect=_aim_standard,
            profit_hint="バランス型",
        ),
        Choice(
            label="C. グロース市場（株主数150名・時価総額5億円以上）",
            description="成長可能性を重視した新興企業向け",
            immediate_effect=_aim_growth,
            profit_hint="要件緩め・早期上場可",
            risk_hint="時価総額評価▲5%",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
)


# ─────────────────────────────────────────────
# 追加イベント②: インサイダー取引防止体制
# ─────────────────────────────────────────────
def _insider_full_system(company: Company) -> str:
    company.compliance_score += 20
    company.internal_control_score += 10
    company.investor_trust += 8
    company.has_insider_prevention = True
    company.defense_score = getattr(company, "defense_score", 0) + 1   # 🏗 現場負荷（全社研修・事前承認運用）
    return ("🔐 インサイダー取引防止規程を制定・全社研修を実施しました。\n"
            f"   重要事実の管理責任者を指定し、役職員の自社株売買を事前承認制に。\n"
            f"   コンプライアンス+20 / 内部統制+10 / 投資家信頼+8 / 🏗 現場負荷+1\n"
            f"   ▶ 実務: 金商法166条違反は刑事罰。上場後の最頻発コンプライアンス違反の一つ。")


def _insider_minimal(company: Company) -> str:
    company.compliance_score += 5
    company.flags.total_risk_score += 8
    company.has_insider_prevention = True
    return ("📝 簡易的な規程のみ制定しました（研修は任意）。\n"
            f"   コンプライアンス+5（上場後インサイダー違反リスク残存）\n"
            f"   リスクスコア+8")


EVENT_INSIDER_TRADING = GameEvent(
    id="insider_trading_prevention",
    title="インサイダー取引防止体制の整備",
    description=(
        "コンプライアンス担当役員からの提言：「上場会社になると、役職員やその家族による\n"
        "自社株取引は金融商品取引法166条の規制対象となります。\n"
        "重要事実の管理体制・売買の事前承認制度・定期研修など\n"
        "一連のインサイダー取引防止体制の整備が上場審査前の必須事項です。」\n"
        "【IPO実務検定】インサイダー情報管理規程と役職員教育は上場審査でも確認項目です。"
    ),
    choices=[
        Choice(
            label="A. 規程制定＋全社研修＋売買事前承認システムを導入（¥3M）",
            description="体制を完全整備",
            immediate_effect=lambda c: (_apply_cost(c, 3.0), _insider_full_system(c))[1],
        ),
        Choice(
            label="B. 最低限の規程のみ制定する",
            description="費用を抑える",
            immediate_effect=_insider_minimal,
            profit_hint="コスト削減",
            risk_hint="上場後の違反リスク",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
)


# ─────────────────────────────────────────────
# 追加イベント③: 内部通報制度（公益通報者保護法）
# ─────────────────────────────────────────────
def _whistleblower_external(company: Company) -> str:
    company.compliance_score += 18
    company.governance_score += 12
    company.employee_morale += 8
    company.quarterly_burn += 0.8
    return ("📞 外部法律事務所を窓口とする内部通報制度を導入しました。\n"
            f"   通報者の匿名性と不利益取扱禁止を規程化。従業員301名以上は\n"
            f"   2022年改正公益通報者保護法で義務化されています。\n"
            f"   コンプライアンス+18 / ガバナンス+12 / 士気+8（運用費¥0.8M/Q）\n"
            f"   ▶ 実務: 不正の早期発見ルートとして上場審査でも重視されます。")


def _whistleblower_internal(company: Company) -> str:
    company.compliance_score += 5
    company.flags.total_risk_score += 5
    return ("📋 社内の人事部を窓口とする簡易的な通報制度のみ設置。\n"
            f"   コンプライアンス+5（通報者保護の実効性に疑問・リスク+5）")


EVENT_WHISTLEBLOWER = GameEvent(
    id="whistleblower_system",
    title="内部通報制度（公益通報者保護法）の整備",
    description=(
        "管理部長から相談: 「2022年の改正公益通報者保護法により、\n"
        "従業員301名以上の事業者は内部通報体制の整備が義務化されました。\n"
        "また、上場審査では『不正の早期発見ルート』として重視されます。\n"
        "外部窓口を設けるか、社内窓口で運用するか、ご判断ください。」\n"
        "【IPO実務検定】内部通報制度はコンプライアンス体制の要です。"
    ),
    choices=[
        Choice(
            label="A. 外部法律事務所に通報窓口を委託（運用費¥0.8M/Q）",
            description="独立性と実効性を確保",
            immediate_effect=_whistleblower_external,
        ),
        Choice(
            label="B. 人事部に窓口を設置するだけにとどめる",
            description="低コスト運用",
            immediate_effect=_whistleblower_internal,
            profit_hint="コスト抑制",
            risk_hint="実効性に疑問",
        ),
    ],
    min_n_period=-3,
    max_n_period=-2,
    one_shot=True,
)


# ─────────────────────────────────────────────
# 追加イベント④: ESG/サステナビリティ開示（倫理・社会的責任）
# ─────────────────────────────────────────────
def _esg_full_disclosure(company: Company) -> str:
    company.governance_score += 15
    company.investor_trust += 20
    company.market_cap_million *= 1.05
    company.quarterly_burn += 1.5
    return ("🌱 TCFD提言に基づく気候関連情報開示＋人的資本開示を実施しました。\n"
            f"   サステナビリティ委員会を設置、GHG排出量も算定・開示。\n"
            f"   ガバナンス+15 / 投資家信頼+20 / 時価総額+5%（運用費¥1.5M/Q）\n"
            f"   ▶ 実務: プライム市場はTCFD準拠開示が実質必須。ESGスコアで\n"
            f"     機関投資家の投資判断が大きく変わる時代です。")


def _esg_basic(company: Company) -> str:
    company.governance_score += 5
    company.investor_trust += 5
    return ("📄 法定の最低限のサステナビリティ記述を有報に盛り込みました。\n"
            f"   ガバナンス+5 / 投資家信頼+5\n"
            f"   ▶ 実務: 法令遵守レベルの対応。ESG評価は低めとなります。")


def _esg_skip(company: Company) -> str:
    company.flags.total_risk_score += 5
    company.investor_trust -= 3
    return ("⏭️  ESG対応は上場後に先送り。\n"
            f"   投資家信頼▲3 / リスクスコア+5\n"
            f"   ⚠️  プライム志向の場合、大きな指摘事項となります。")


EVENT_ESG_DISCLOSURE = GameEvent(
    id="esg_sustainability",
    title="ESG・サステナビリティ開示体制の整備",
    description=(
        "IRコンサルタントから提言: 「2023年3月期から有価証券報告書に\n"
        "『サステナビリティ情報』欄が新設され、気候変動・人的資本の\n"
        "開示が実質義務化されました。プライム市場ではTCFD提言に基づく\n"
        "開示も求められます。ESG評価は機関投資家の投資判断に直結します。」\n"
        "【IPO実務検定】倫理・社会的責任は上場会社の持続可能性の要です。"
    ),
    choices=[
        Choice(
            label="A. TCFD準拠のフル開示＋サステナ委員会設置（運用費¥1.5M/Q）",
            description="最上位水準のESG体制",
            immediate_effect=_esg_full_disclosure,
            profit_hint="信頼+20・時価総額+5%",
        ),
        Choice(
            label="B. 法定最低限のサステナ記述のみ",
            description="必要最小限",
            immediate_effect=_esg_basic,
        ),
        Choice(
            label="C. 先送り（上場後に対応）",
            description="今期コストゼロ",
            immediate_effect=_esg_skip,
            profit_hint="コストゼロ",
            risk_hint="投資家評価▲3・リスク+5",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
)


# ─────────────────────────────────────────────
# 追加イベント⑤: 株式分割による流動性確保（資本政策）
# ─────────────────────────────────────────────
def _stock_split_aggressive(company: Company) -> str:
    # 株主数は据え置きだが、流動性向上により時価総額評価アップ
    company.cap_table.total_shares *= 10
    for s in company.cap_table.shareholders:
        s.shares *= 10
    company.market_cap_million *= 1.08
    company.investor_trust += 10
    company.shareholder_count = int(company.shareholder_count * 1.15)
    return ("✂️  1:10の株式分割を実施しました。\n"
            f"   投資単位が下がり個人投資家の参加が容易に。\n"
            f"   時価総額+8% / 投資家信頼+10 / 株主数+15%\n"
            f"   ▶ 実務: 東証は『投資単位50万円未満』を推奨。上場直前の\n"
            f"     株式分割は典型的な流動性確保策です。")


def _stock_split_moderate(company: Company) -> str:
    company.cap_table.total_shares *= 5
    for s in company.cap_table.shareholders:
        s.shares *= 5
    company.market_cap_million *= 1.03
    company.investor_trust += 5
    company.shareholder_count = int(company.shareholder_count * 1.07)
    return ("✂️  1:5の株式分割を実施しました。\n"
            f"   時価総額+3% / 投資家信頼+5 / 株主数+7%")


def _stock_split_none(company: Company) -> str:
    return ("🚫 株式分割は見送り。現行の発行株式数で上場を目指します。\n"
            f"   ▶ 実務: 投資単位が高すぎると個人投資家の参加が限定されます。")


EVENT_STOCK_SPLIT = GameEvent(
    id="stock_split",
    title="上場前の株式分割（資本政策）",
    description=(
        "CFOから提案: 「公開価格を想定すると、現在の1株あたり単価では\n"
        "投資単位（100株）が100万円を超えてしまいます。東証は投資単位\n"
        "50万円未満を推奨しており、個人投資家参加促進のため株式分割を\n"
        "検討すべきタイミングです。」\n"
        "【IPO実務検定】株式分割は流動性・株主数・公開価格の3要素を動かす重要な資本政策。"
    ),
    choices=[
        Choice(
            label="A. 1:10の大胆な株式分割",
            description="個人投資家も参加しやすく",
            immediate_effect=_stock_split_aggressive,
            profit_hint="時価総額+8%・株主数+15%",
        ),
        Choice(
            label="B. 1:5の標準的な株式分割",
            description="バランス型",
            immediate_effect=_stock_split_moderate,
            profit_hint="時価総額+3%・株主数+7%",
        ),
        Choice(
            label="C. 株式分割は実施しない",
            description="現状維持",
            immediate_effect=_stock_split_none,
            risk_hint="投資単位が高い・流動性リスク",
        ),
    ],
    min_n_period=-1,
    max_n_period=0,
    one_shot=True,
)


# ─────────────────────────────────────────────
# 追加イベント⑥: 種類株式の普通株式への転換（資本政策）
# ─────────────────────────────────────────────
def _convert_preferred_full(company: Company) -> str:
    company.governance_score += 15
    company.investor_trust += 15
    return ("🔄 過去の資金調達で発行した優先株式をすべて普通株式に転換しました。\n"
            f"   上場時には原則『普通株式のみ』が求められます（種類株上場は例外）。\n"
            f"   VCは普通株式での上場を受け入れました。\n"
            f"   ガバナンス+15 / 投資家信頼+15\n"
            f"   ▶ 実務: 優先株→普通株の転換条項は当初契約で定めるのが通例。\n"
            f"     見落とすと上場直前で交渉紛糾のリスクあり。")


def _convert_preferred_partial(company: Company) -> str:
    company.flags.total_risk_score += 15
    company.investor_trust -= 5
    return ("⚠️  一部VCが普通株式への転換に同意せず交渉が難航。\n"
            f"   上場スケジュールに遅延リスク。投資家信頼▲5 / リスク+15\n"
            f"   ▶ 実務: 当初契約の転換条項不備が原因となる典型例です。")


EVENT_PREFERRED_CONVERSION = GameEvent(
    id="preferred_stock_conversion",
    title="種類株式の普通株式への転換（資本政策）",
    description=(
        "主幹事証券会社から確認: 「上場審査では原則として普通株式への\n"
        "一本化が求められます。過去の資金調達で発行した優先株式の転換手続を\n"
        "進める必要があります。VCとの交渉はCFOに対応させますが、\n"
        "当初契約の転換条項が曖昧な場合は難航する可能性があります。」\n"
        "【IPO実務検定】種類株式の上場時取扱いは資本政策の重要論点です。"
    ),
    choices=[
        Choice(
            label="A. 全VCと転換条項を丁寧に再確認し合意を取付ける（¥2M）",
            description="上場直前トラブルを回避",
            immediate_effect=lambda c: (_apply_cost(c, 2.0), _convert_preferred_full(c))[1],
        ),
        Choice(
            label="B. 既存契約の解釈で押し切る",
            description="スピード優先",
            immediate_effect=_convert_preferred_partial,
            risk_hint="交渉紛糾・上場遅延リスク",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
    trigger_condition=lambda c: len([s for s in c.cap_table.shareholders if s.is_vc]) > 0,
)


# ─────────────────────────────────────────────
# 追加イベント⑦: 適時開示体制の実効性テスト（コンプライアンス）
# ─────────────────────────────────────────────
def _disclosure_drill_full(company: Company) -> str:
    company.internal_control_score += 12
    company.governance_score += 8
    company.investor_trust += 10
    return ("📢 模擬適時開示ドリルを実施しました。\n"
            f"   『決算短信誤記載』『業績予想修正』『重要事実の漏えい』など\n"
            f"   10シナリオを想定し、開示担当・経営陣・広報の連携を訓練。\n"
            f"   内部統制+12 / ガバナンス+8 / 投資家信頼+10\n"
            f"   ▶ 実務: 東証の適時開示違反は再発防止策と改善報告書提出。\n"
            f"     上場後の最頻発トラブルを事前に潰せます。")


def _disclosure_drill_skip(company: Company) -> str:
    company.flags.total_risk_score += 10
    return ("⏭️  開示ドリルを省略。上場後に実地で対応する方針。\n"
            f"   リスクスコア+10（上場初年度の開示トラブルリスク増大）")


EVENT_DISCLOSURE_DRILL = GameEvent(
    id="disclosure_drill",
    title="適時開示体制の実効性テスト（コンプライアンス）",
    description=(
        "IR担当者から提言: 「上場後は決算短信・業績予想修正・M&A等の\n"
        "重要情報を東証TDnetで『決定後遅滞なく』開示する義務があります。\n"
        "開示遅延・誤開示は東証から改善報告書を要求されます。\n"
        "模擬開示ドリルで体制の実効性を確認すべきタイミングです。」\n"
        "【IPO実務検定】適時開示は上場会社最重要のコンプライアンス義務の一つです。"
    ),
    choices=[
        Choice(
            label="A. 10シナリオの模擬開示ドリルを実施（¥2M）",
            description="実効性を事前検証",
            immediate_effect=lambda c: (_apply_cost(c, 2.0), _disclosure_drill_full(c))[1],
        ),
        Choice(
            label="B. ドリルは省略し上場後に対応",
            description="コスト削減",
            immediate_effect=_disclosure_drill_skip,
            profit_hint="コストゼロ",
            risk_hint="初年度開示トラブル・リスク+10",
        ),
    ],
    min_n_period=-1,
    max_n_period=0,
    one_shot=True,
)


# ─────────────────────────────────────────────
# 追加イベント⑧: 創業者株式のロックアップ・資本政策の最終調整
# ─────────────────────────────────────────────
def _lockup_long(company: Company) -> str:
    company.investor_trust += 15
    company.market_cap_million *= 1.05
    return ("🔒 創業者・VCに180日のロックアップを設定しました。\n"
            f"   上場直後の売り圧力を抑制し、株価の安定化に寄与。\n"
            f"   投資家信頼+15 / 時価総額+5%\n"
            f"   ▶ 実務: ロックアップは公開価格算定・機関投資家の購入判断に\n"
            f"     大きく影響します。主幹事証券会社との協議事項の中核です。")


def _lockup_short(company: Company) -> str:
    company.investor_trust += 3
    company.flags.total_risk_score += 8
    return ("🔓 90日の短期ロックアップで決着。\n"
            f"   早期の株式売却が可能だが、上場直後の価格下落リスク。\n"
            f"   投資家信頼+3 / リスク+8")


EVENT_LOCKUP_POLICY = GameEvent(
    id="lockup_policy",
    title="創業者・VCロックアップ期間の設定（資本政策最終調整）",
    description=(
        "主幹事証券会社からの提案: 「公開価格決定に向け、創業者・VCの\n"
        "ロックアップ（売却制限期間）を決定します。\n"
        "長期設定は投資家心理・株価安定に有利ですが、\n"
        "VCの出口戦略と利害が対立する可能性があります。」\n"
        "【IPO実務検定】ロックアップは資本政策の最終調整事項です。"
    ),
    choices=[
        Choice(
            label="A. 180日ロックアップで投資家信頼を最大化",
            description="株価安定を最優先",
            immediate_effect=_lockup_long,
            profit_hint="信頼+15・時価総額+5%",
        ),
        Choice(
            label="B. 90日ロックアップ（VC要望を反映）",
            description="バランス型",
            immediate_effect=_lockup_short,
            risk_hint="上場直後の下落リスク・リスク+8",
        ),
    ],
    min_n_period=-1,
    max_n_period=0,
    one_shot=True,
)


# ─────────────────────────────────────────────
# 追加イベント群: 上場準備チェックポイント補完
# （職務権限規程・予算管理・内部監査・知財・会計監査人選任・ほふり等）
# ─────────────────────────────────────────────

# ── N-2期：職務権限・業務分掌規程 ───────────────────
def _full_authority_rules(c: Company) -> str:
    c.has_authority_rules = True
    c.internal_control_score += 18
    c.governance_score += 12
    return ("📜 職務権限規程・業務分掌規程を整備しました。\n"
            "   決裁権限を金額・案件別に明確化し、相互牽制を実装。\n"
            "   内部統制+18 / ガバナンス+12\n"
            "   ▶ 実務: 上場審査では「組織的な意思決定と牽制体制」が必須項目。"
            "規程運用の実績作りも重要です。")

def _minimal_authority_rules(c: Company) -> str:
    c.has_authority_rules = True
    c.internal_control_score += 6
    c.flags.total_risk_score += 5
    return ("📜 簡易な決裁規程のみ作成しました。\n"
            "   内部統制+6（運用実績不足のため審査時に不十分の指摘可能性 / リスク+5）")

EVENT_AUTHORITY_RULES = GameEvent(
    id="authority_rules",
    title="職務権限規程・業務分掌規程の整備",
    description=(
        "管理部長からの提言：「組織的な意思決定と相互牽制のため、\n"
        "職務権限規程・業務分掌規程の整備が不可欠です。\n"
        "決裁ルートと金額基準を文書化し、運用実績を積み上げる必要があります。」\n"
        "【ポイント】上場審査では規程の有無だけでなく運用実績も確認されます。"
    ),
    choices=[
        Choice(
            label="A. 専門家と協働で完全な規程整備＋運用フロー導入（¥6M）",
            description="権限表・分掌表・ワークフローシステムを整備",
            immediate_effect=lambda c: (_apply_cost(c, 6.0), _full_authority_rules(c))[1],
            risk_hint="整備コスト¥6M",
        ),
        Choice(
            label="B. 雛形ベースの簡易規程のみ作成（¥1M）",
            description="文書化のみ、運用は現状維持",
            immediate_effect=lambda c: (_apply_cost(c, 1.0), _minimal_authority_rules(c))[1],
            profit_hint="低コスト",
            risk_hint="運用実績不足リスク",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
)


# ── N-2期：予算管理制度の確立 ──────────────────────
def _full_budget_control(c: Company) -> str:
    c.has_budget_control = True
    c.accounting_quality += 15
    c.investor_trust += 12
    c.internal_control_score += 8
    return ("📊 月次予算管理制度を確立しました。\n"
            "   月次の予実差異分析→経営会議報告のサイクルを定着化。\n"
            "   会計品質+15 / 投資家信頼+12 / 内部統制+8\n"
            "   ▶ 実務: 上場審査では予算統制と予実精度（差異率±10%以内推奨）が問われます。")

def _minimal_budget_control(c: Company) -> str:
    c.has_budget_control = True
    c.accounting_quality += 5
    c.flags.total_risk_score += 5
    return ("📊 年度予算のみ作成（月次の運用はなし）。\n"
            "   会計品質+5（予実乖離管理が不十分・リスク+5）")

EVENT_BUDGET_CONTROL = GameEvent(
    id="budget_control",
    title="予算管理制度の確立（月次予実分析）",
    description=(
        "経理部長からの提案：「上場審査では事業計画の合理性と\n"
        "実績の整合性が厳しく問われます。月次予算→予実差異分析→\n"
        "経営会議へのフィードバック、というサイクルの確立が必要です。」\n"
        "【ポイント】予実精度は事業計画の信頼性を担保する重要要素です。"
    ),
    choices=[
        Choice(
            label="A. 月次予実管理サイクルを完全運用（¥4M）",
            description="部門別予算編成・月次差異分析・是正アクション運用",
            immediate_effect=lambda c: (_apply_cost(c, 4.0), _full_budget_control(c))[1],
        ),
        Choice(
            label="B. 年度予算のみ作成して終わらせる（¥1M）",
            description="形式的な対応のみ",
            immediate_effect=lambda c: (_apply_cost(c, 1.0), _minimal_budget_control(c))[1],
            profit_hint="コスト削減",
            risk_hint="予実管理不足の指摘リスク",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
)


# ── N-2期：内部監査部門の設置 ─────────────────────
def _full_internal_audit(c: Company) -> str:
    c.has_internal_audit = True
    c.internal_control_score += 20
    c.governance_score += 15
    c.auditor_trust += 10
    c.quarterly_burn += 2.0
    return ("🔍 独立した内部監査部門を設置しました。\n"
            "   社長直轄の専任2名体制で年間監査計画を策定・実施。\n"
            "   内部統制+20 / ガバナンス+15 / 監査法人信頼+10（運用費¥2M/Q）\n"
            "   ▶ 実務: 内部監査は自浄作用の根幹。上場審査の必須項目です。")

def _minimal_internal_audit(c: Company) -> str:
    c.has_internal_audit = True
    c.internal_control_score += 6
    c.flags.total_risk_score += 8
    return ("🔍 経理部員が兼務で内部監査を担当（独立性なし）。\n"
            "   内部統制+6（独立性欠如・リスク+8）")

EVENT_INTERNAL_AUDIT = GameEvent(
    id="internal_audit",
    title="独立した内部監査部門の設置",
    description=(
        "監査法人からの強い要請：「上場審査では『独立した内部監査機能』\n"
        "の存在と運用実績が必須です。社長直轄の専任部門を設け、\n"
        "年間監査計画に基づき被監査部門を客観的に検証する必要があります。」\n"
        "【ポイント】内部監査は自浄作用の要であり、上場審査の重点確認項目です。"
    ),
    choices=[
        Choice(
            label="A. 専任2名の独立内部監査室を設置（¥2M/Q継続）",
            description="社長直轄・年間監査計画運用",
            immediate_effect=_full_internal_audit,
        ),
        Choice(
            label="B. 経理部員の兼務でやり過ごす",
            description="人件費抑制",
            immediate_effect=_minimal_internal_audit,
            profit_hint="人件費抑制",
            risk_hint="独立性欠如で審査NG可能性",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
)


# ── N-2期：知的財産権の保護 ───────────────────────
def _full_ip_protection(c: Company) -> str:
    c.has_ip_protection = True
    c.investor_trust += 10
    c.compliance_score += 8
    c.governance_score += 5
    return ("™️  知財調査と権利化を完了しました。\n"
            "   特許・商標・意匠の出願＋他社権利侵害の予防調査を実施。\n"
            "   投資家信頼+10 / コンプライアンス+8 / ガバナンス+5\n"
            "   ▶ 実務: 知財関連の係争は上場後の業績下振れリスクの典型例です。")

def _minimal_ip_protection(c: Company) -> str:
    c.has_ip_protection = True
    c.compliance_score += 3
    c.flags.total_risk_score += 7
    return ("™️  既存の商標登録のみ確認しました。\n"
            "   コンプライアンス+3（権利侵害リスク残存・リスク+7）")

EVENT_IP_PROTECTION = GameEvent(
    id="ip_protection",
    title="知的財産権の保護と侵害予防調査",
    description=(
        "知財コンサルからの報告：「自社サービス・ロゴ・主要技術について\n"
        "権利化の状況確認と他社権利の侵害予防調査が必要です。\n"
        "上場目論見書の事業リスク項目にも記載が必要となります。」\n"
        "【ポイント】知財紛争は上場後の業績下振れ要因として重要視されます。"
    ),
    choices=[
        Choice(
            label="A. 弁理士と共に包括的な知財調査・権利化を実施（¥5M）",
            description="特許・商標・意匠＋FTO調査",
            immediate_effect=lambda c: (_apply_cost(c, 5.0), _full_ip_protection(c))[1],
        ),
        Choice(
            label="B. 既存商標の確認のみで済ませる（¥0.5M）",
            description="最低限の対応",
            immediate_effect=lambda c: (_apply_cost(c, 0.5), _minimal_ip_protection(c))[1],
            profit_hint="コスト削減",
            risk_hint="権利侵害・係争リスク",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
)


# ── N-1期：会計監査人 正式選任 ─────────────────────
def _full_accounting_auditor(c: Company) -> str:
    # 会社法第329条2項：会計監査人の選任は株主総会の普通決議が必要（登記事項）。
    # CEO決断は今期（N-1期の総会に上程する意思決定）だが、
    # 就任効力（監査信頼・コンプラ等のスコア改善）は総会承認後の翌四半期に発現。
    c.agm_deferred_auditor_appt = True
    return ("✅ 監査法人を会社法上の『会計監査人』として総会に上程することを決定しました。\n"
            "   ▶ 【会社法第329条2項】会計監査人の選任は株主総会の普通決議が必要です（登記事項）。\n"
            "   ▶ N-1期定時株主総会での選任決議が可決されると翌四半期から正式就任します。\n"
            "   ▶ 就任後：監査法人信頼+15・コンプライアンス+10・ガバナンス+10\n"
            "   【実務】N-2期から監査契約は締結済みでも、会社法上の正式選任はN-1期総会での決議が必要です。\n"
            "   上場申請には N-2期・N-1期ともに『無限定適正意見』が不可欠です。")

def _delay_accounting_auditor(c: Company) -> str:
    c.has_accounting_auditor = False
    c.flags.total_risk_score += 15
    return ("⚠ 会計監査人の正式選任を先送りにしました。\n"
            "   ▶ 【重大警告】N-1期の定時株主総会は会計監査人を正式選任する\n"
            "     最後のタイミングです（登記事項）。\n"
            "     N期（申請期）への持ち越しは、上場申請書類に\n"
            "     N-1期分の会計監査人による監査報告書が添付できないため\n"
            "     上場申請が受理されない重大なリスクがあります。\n"
            "     また上場申請には過去2期（N-2・N-1）の『無限定適正意見』が必要です。\n"
            "   リスクスコア+15（上場申請要件未充足リスク）")

EVENT_ACCOUNTING_AUDITOR = GameEvent(
    id="accounting_auditor",
    title="会計監査人の正式選任（N-1期定時株主総会・必須）",
    description=(
        "CFOからの提案：「現状は『監査契約』ベースの監査ですが、\n"
        "上場会社は会社法上の『会計監査人』を株主総会で正式選任する\n"
        "必要があります。N-1期の定時株主総会が対応のデッドラインです。\n\n"
        "【重要事項】\n"
        "  ・上場申請には過去2期分（N-2・N-1期）の監査報告書が必要\n"
        "  ・両期とも『無限定適正意見』でなければ申請受理されません\n"
        "  ・『限定付適正意見』や『意見不表明』は上場申請の致命的欠陥です\n\n"
        "【無限定適正意見のための条件】\n"
        "  ・発生主義移行の完了（N-2期首まで）\n"
        "  ・証憑管理体制の整備\n"
        "  ・棚卸立会の実施（棚卸資産が重要な業種）\n"
        "  ・ショートレビュー指摘事項の改善完了\n\n"
        "【ポイント】会計監査人の正式選任はN-1期定時株主総会が実質的なデッドラインです。"
    ),
    choices=[
        Choice(
            label="A. N-1期定時株主総会で会計監査人を正式選任する（¥2M）",
            description="選任決議・登記・定款変更を含む正式手続。上場申請要件を充足",
            immediate_effect=lambda c: (_apply_cost(c, 2.0), _full_accounting_auditor(c))[1],
            risk_hint="上場申請には過去2期の無限定適正意見が必要。早期対応が最重要",
        ),
        Choice(
            label="B. N期（申請期）に持ち越して対応する",
            description="後ろ倒しを選択。ただしN-1期分の監査報告書が欠如する重大リスク",
            immediate_effect=_delay_accounting_auditor,
            profit_hint="今期コスト¥0",
            risk_hint="上場申請書類のN-1期監査報告書欠如 → 申請受理リスク。+15",
        ),
    ],
    min_n_period=-1,
    max_n_period=-1,
    one_shot=True,
    trigger_condition=lambda c: c.has_audit_contract and not c.has_accounting_auditor,
)


# ── N期：ほふり参加・最終手続き ────────────────────
def _full_final_listing(c: Company) -> str:
    c.has_hofuri = True
    c.has_governance_report = True
    # 定款変更はN-1期AGMで処理済みのため、ここでは設定しない
    c.compliance_score += 12
    c.governance_score += 12
    c.investor_trust += 10
    return ("🏛 上場最終手続きの準備が完了しました！\n"
            "   コンプライアンス+12 / ガバナンス+12 / 投資家信頼+10\n"
            "   ▶ 【実務①】定款変更案5項目を作成（次回定時株主総会で特別決議）：\n"
            "     ①株式の譲渡制限に関する規定の削除（上場株式は自由譲渡が原則）\n"
            "     ②株主名簿管理人（信託銀行等）に関する条項の追加\n"
            "     ③公告方法の変更（官報→電子公告への切替）\n"
            "     ④単元株式数を100株と定める規定の追加（東証の原則）\n"
            "     ⑤株券不発行に関する規定（振替制度への対応）\n"
            "   ▶ 【実務②】証券保管振替機構（ほふり）参加手続き3段階：\n"
            "     Step1：参加申請書の提出（上場申請と並行して申請）\n"
            "     Step2：振替機関審査・参加承認（審査期間あり）\n"
            "     Step3：振替口座簿の開設・株主名簿との連動設定\n"
            "   ▶ 【実務③】コーポレートガバナンス報告書の主な記載内容：\n"
            "     ・基本的な考え方（経営理念・ガバナンス方針）\n"
            "     ・独立社外取締役・監査役の選任状況と独立性の理由\n"
            "     ・CG原則の実施状況（コンプライ・オア・エクスプレイン）\n"
            "     ・政策保有株式・関連当事者取引の方針\n"
            "     上場承認の前提条件として提出が必要な最重要書類の一つです。")

def _partial_final_listing(c: Company) -> str:
    c.has_hofuri = True
    c.has_governance_report = False
    # 定款変更はN-1期AGMで処理済みのため、ここでは設定しない
    c.compliance_score += 5
    c.flags.total_risk_score += 12
    return ("🏛 証券振替参加と定款変更案の作成のみ完了。コーポレートガバナンス報告書は未提出。\n"
            "   コンプライアンス+5 / リスクスコア+12\n"
            "   ▶ 【注意】定款変更案5項目（譲渡制限削除・株主名簿管理人・\n"
            "     公告方法・単元株100株・株券不発行）を作成しましたが、\n"
            "     コーポレートガバナンス報告書は上場承認の前提条件です。\n"
            "     CG報告書なしでは上場承認が下りません。至急対応が必要です。")

EVENT_FINAL_LISTING_PROCEDURE = GameEvent(
    id="final_listing_procedure",
    title="上場最終手続き（定款変更・証券振替参加・CG報告書）",
    description=(
        "主幹事からの最終要請：「上場承認前の必須手続きを完了させてください。\n\n"
        "【①定款変更案 5項目の作成】（次回定時株主総会で特別決議が必要）\n"
        "  ①株式の譲渡制限規定の削除\n"
        "  ②株主名簿管理人（信託銀行等）に関する条項の追加\n"
        "  ③公告方法の変更（官報→電子公告）\n"
        "  ④単元株式数100株の規定追加（東証の原則）\n"
        "  ⑤株券不発行に関する規定（振替制度対応）\n\n"
        "【②証券保管振替機構（通称ほふり）参加手続き】\n"
        "  Step1：参加申請書の提出（上場申請と並行）\n"
        "  Step2：振替機関審査・参加承認\n"
        "  Step3：振替口座簿の開設・株主名簿との連動設定\n\n"
        "【③コーポレートガバナンス報告書】\n"
        "  ・独立社外役員の選任状況と独立性の理由\n"
        "  ・CG原則の実施状況（コンプライ・オア・エクスプレイン）\n"
        "  ・政策保有株式・関連当事者取引の方針\n"
        "  ※上場承認の前提条件として提出が必須の書類です。\n\n"
        "【ポイント】これら3種類の手続きはすべて上場承認の前提条件です。"
    ),
    choices=[
        Choice(
            label="A. 定款変更・証券振替参加・CG報告書をすべて完全対応（¥10M）",
            description="専門家チームで全手続きを完了。上場承認の前提条件を完全充足",
            immediate_effect=lambda c: (_apply_cost(c, 10.0), _full_final_listing(c))[1],
            risk_hint="費用¥10M。上場承認の前提条件をすべて充足",
        ),
        Choice(
            label="B. 証券振替参加・定款変更のみ対応し、CG報告書は最小限（¥5M）",
            description="CG報告書の内容を簡素化して対応。ただし上場承認リスクあり",
            immediate_effect=lambda c: (_apply_cost(c, 5.0), _partial_final_listing(c))[1],
            profit_hint="コスト削減",
            risk_hint="CG報告書不備→上場承認前提条件未充足リスク。+12",
        ),
    ],
    min_n_period=0,
    max_n_period=0,
    one_shot=True,
)


# ─────────────────────────────────────────────
# セカンドチャンスイベント①: 社外役員 N-1期 最終機会
# ─────────────────────────────────────────────
def _appoint_outside_director_urgent(company: Company) -> str:
    """N-1期 ラストチャンス — 臨時株主総会を招集して社外役員を緊急選任
    通常 AGM ルート（ガバナンス+30）と異なり、臨時総会招集コストと
    「なぜ定時総会で選任しなかったのか」という説明責任がガバナンス評価を大きく損なう。"""
    company.flags.no_outside_director = False
    company.outside_director_late_appointment = True
    # 臨時総会招集・運営コスト + 役員報酬（年間）
    company.cash -= 8.0                      # 臨時総会費用¥8M（通知・会場・法務）
    company.quarterly_burn += 4.0            # 役員報酬¥4M/Q
    # ガバナンス：選任自体はプラスだが臨時総会招集の説明責任でネット大幅マイナス
    company.governance_score = max(0, company.governance_score - 15)
    company.investor_trust   = max(0, company.investor_trust   - 10)
    company.flags.total_risk_score += 10     # N-1期途中選任による運用実績不足
    return (
        "🏛️  臨時株主総会を招集し、独立社外取締役・社外監査役を緊急選任しました。\n"
        "   ▶ 臨時総会費用 ¥8M（通知・招集・法務）\n"
        "   ▶ 役員報酬 ¥4M/Q（継続費用）\n\n"
        "   ⚠ 【ガバナンス上の重大問題】\n"
        "   定時株主総会で選任すべき社外役員を、N-1期途中で臨時総会を招集して\n"
        "   ようやく選任した事実は、上場審査においてガバナンス体制の不備として\n"
        "   強く指摘されます。選任は完了しましたが、1年間の運用実績が\n"
        "   積み上げられないまま上場申請を迎えることになります。\n\n"
        "   ▶ ガバナンス-15 / 投資家信頼-10\n"
        "   ▶ リスクスコア+10（N-1期途中選任・運用実績不足）"
    )

def _decline_outside_director_urgent(company: Company) -> str:
    """最終チャンスも断った場合 — 致命的なガバナンス欠陥"""
    company.flags.no_outside_director = True
    company.flags.total_risk_score += 30
    company.investor_trust -= 20
    company.governance_score -= 10
    return ("❌ 社外役員の選任を見送りました。\n"
            "   上場審査で最も基本的なガバナンス要件を満たせていない状態です。\n"
            "   ▶ リスクスコア+30 / 投資家信頼-20 / ガバナンス-10\n"
            "   ▶ 【警告】このまま上場審査に臨むと、ガバナンス体制不備として審査不通過になります。")

EVENT_OUTSIDE_DIRECTOR_N1 = GameEvent(
    id="outside_director_urgent",
    title="【緊急】社外役員が未選任 — N-1期 臨時株主総会で緊急対応",
    description=(
        "主幹事証券会社から緊急連絡が入りました。\n\n"
        "「社長、大変深刻な状況です。N-1期（直前期）に入りましたが、\n"
        "まだ独立社外取締役・社外監査役が選任されていません。\n\n"
        "定時株主総会での選任は既に間に合いません。\n"
        "今からでは【臨時株主総会】を招集して選任するしか手段がありません。\n\n"
        "臨時総会は定時総会と異なり招集コストがかかるうえ、\n"
        "上場審査において『なぜ定時総会で選任しなかったのか』という\n"
        "説明責任が生じ、ガバナンス体制の不備として評価されます。\n\n"
        "上場審査では『直前期を通じた社外役員の運用実績』が必須確認事項です。\n"
        "今期中に選任しなければ、上場申請そのものができなくなります。\n"
        "非常に急を要する状況です。今すぐ対応を決断してください。」\n\n"
        "【ポイント】臨時総会経由の選任はガバナンス評価に大きなマイナスとなります。"
    ),
    choices=[
        Choice(
            label="A. 臨時株主総会を招集し、今すぐ社外役員を緊急選任する（臨時総会費用¥8M＋役員報酬¥4M/Q）",
            description="コストと評価低下を受け入れて今期中に選任。上場申請の最低条件を満たす",
            immediate_effect=_appoint_outside_director_urgent,
            risk_hint="ガバナンス-15・投資家信頼-10・リスク+10（臨時総会・運用実績不足）",
        ),
        Choice(
            label="B. それでも先送りにする（上場審査NG確定リスク）",
            description="コスト節減を優先するが、上場審査でガバナンス欠陥として指摘される",
            immediate_effect=_decline_outside_director_urgent,
            profit_hint="役員報酬コスト節減",
            risk_hint="【致命的】ガバナンス欠陥→上場審査NG。リスク+30",
        ),
    ],
    min_n_period=-1,
    max_n_period=-1,
    one_shot=True,
    trigger_condition=lambda c: c.flags.no_outside_director and not getattr(c, 'agm_deferred_outside_director', False),
)


# ─────────────────────────────────────────────
# セカンドチャンスイベント①-b: 定款変更 N期 臨時株主総会で再上程
# ─────────────────────────────────────────────
def _eogm_articles_amendment(company: Company) -> str:
    """N期 — 臨時株主総会を招集して定款変更を再上程"""
    import random as _r
    company.cash -= 8.0  # 臨時総会招集費用
    pp = min(0.92, max(0.55, 0.75 + (company.investor_trust - 50) / 200))
    if _r.random() < pp:
        company.agm_deferred_articles_amendment = True
        company.articles_amendment_rejected_needs_eogm = False
        company.governance_score = max(0, company.governance_score - 5)
        company.investor_trust   = max(0, company.investor_trust - 5)
        company.flags.total_risk_score = max(0, company.flags.total_risk_score - 8)
        return (
            "🏛️  臨時株主総会を招集し、定款変更5項目を再上程しました。\n"
            f"   ▶ 臨時総会費用 ¥8M（通知・招集・法務）\n"
            f"   🗳 特別決議【可決】（賛成率約{int(pp*100)}%・2/3以上）\n"
            "   ✅ 定款変更が可決されました。本決議後、速やかに法務局への登記手続きを完了します。\n\n"
            "   ⚠ 【ガバナンス上の指摘事項】\n"
            "   定時総会で可決できず臨時総会経由となった経緯は上場審査で指摘されますが、\n"
            "   定款変更そのものは上場までに完了する見込みです。\n"
            "   ▶ ガバナンス-5 / 投資家信頼-5（臨時総会招集の説明責任）\n"
            "   ▶ リスクスコア-8（定款変更否決リスクが解消）"
        )
    else:
        company.flags.total_risk_score += 20
        company.compliance_score = max(0, company.compliance_score - 8)
        company.investor_trust   = max(0, company.investor_trust - 12)
        return (
            "🏛️  臨時株主総会を招集し、定款変更5項目を再上程しました。\n"
            f"   ▶ 臨時総会費用 ¥8M（通知・招集・法務）\n"
            f"   🗳 特別決議【否決】（賛成率{int(pp*100)}%・2/3に届かず）\n"
            "   ❌ 再上程も否決されました。上場審査の形式要件を充足できません。\n"
            "   ▶ リスクスコア+20 / コンプラ-8 / 投資家信頼-12\n"
            "   ▶ 【警告】定款変更未承認のままでは上場申請が困難です。"
        )

def _decline_eogm_articles_amendment(company: Company) -> str:
    """臨時総会招集を見送る — 上場申請の形式要件未充足"""
    company.flags.total_risk_score += 25
    company.compliance_score = max(0, company.compliance_score - 10)
    company.governance_score = max(0, company.governance_score - 8)
    return (
        "❌ 定款変更の再上程を見送りました。\n"
        "   上場に必要な定款5項目（譲渡制限削除・株主名簿管理人等）が未整備のままです。\n"
        "   ▶ リスクスコア+25 / コンプラ-10 / ガバナンス-8\n"
        "   ▶ 【警告】上場審査では形式要件違反として審査不通過リスクが極めて高くなります。"
    )

EVENT_EOGM_ARTICLES_AMENDMENT = GameEvent(
    id="eogm_articles_amendment",
    title="【緊急】定款変更が否決 — N期 臨時株主総会で再上程",
    description=(
        "主幹事証券会社と顧問弁護士から緊急連絡が入りました。\n\n"
        "「社長、N-1期定時株主総会で定款変更5項目が否決された件、\n"
        "このままでは上場申請の形式要件を満たせません。\n\n"
        "上場には①譲渡制限規定の削除（公開会社への移行）、\n"
        "②株主名簿管理人の設置、③公告方法の変更（電子公告）、\n"
        "④単元株式数100株の規定、⑤株券不発行規定 — これら5項目の\n"
        "定款変更がすべて必須です。\n\n"
        "次回定時総会まで待つと上場スケジュールに重大な影響が出ます。\n"
        "会社法第297条に基づき【臨時株主総会】を招集し、再上程する必要があります。\n"
        "臨時総会の招集費用は約¥8M、否決リスクもありますが、\n"
        "今動かなければ上場申請自体が困難になります。」\n\n"
        "【ポイント】臨時総会経由の定款変更はガバナンス評価に影響しますが、\n"
        "上場の形式要件を満たすには不可欠です。"
    ),
    choices=[
        Choice(
            label="A. 臨時株主総会を招集し定款変更を再上程する（招集費用¥8M）",
            description="上場の形式要件充足を優先（可決確率は株主信頼に依存）",
            immediate_effect=_eogm_articles_amendment,
            risk_hint="費用¥8M。ガバナンス-5・投資家信頼-5（可決時）／リスク+20（否決時）",
        ),
        Choice(
            label="B. 再上程を見送り、次回定時総会まで待つ",
            description="費用は節減できるが上場申請の形式要件を満たせない",
            immediate_effect=_decline_eogm_articles_amendment,
            profit_hint="臨時総会費用¥8M節減",
            risk_hint="【致命的】上場審査で形式要件違反。リスク+25",
        ),
    ],
    min_n_period=0,
    max_n_period=0,
    one_shot=True,
    trigger_condition=lambda c: getattr(c, 'articles_amendment_rejected_needs_eogm', False)
                                and not c.has_articles_amendment
                                and not c.agm_deferred_articles_amendment,
)


# ─────────────────────────────────────────────
# セカンドチャンスイベント②: CG報告書 N期 修正機会
# ─────────────────────────────────────────────
def _fix_governance_report(company: Company) -> str:
    """N期 — CG報告書を完成させる（ほふり参加済み前提）"""
    company.has_governance_report = True
    company.compliance_score += 8
    company.governance_score += 8
    company.cash -= 5.0
    return ("📋 コーポレートガバナンス報告書を完成・提出しました。\n"
            "   コンプライアンス+8 / ガバナンス+8（追加費用¥5M）\n"
            "   ▶ 上場承認の前提条件をすべて充足しました。")

def _skip_governance_report(company: Company) -> str:
    """CG報告書をそれでも後回し — 上場審査で指摘確定"""
    company.flags.total_risk_score += 20
    company.governance_score -= 5
    return ("❌ コーポレートガバナンス報告書の提出を見送りました。\n"
            "   ▶ リスクスコア+20 / ガバナンス-5\n"
            "   ▶ 【警告】上場審査でCG報告書の未提出は形式要件違反として審査不通過になります。")

EVENT_GOVERNANCE_REPORT_FIX = GameEvent(
    id="governance_report_fix",
    title="【要対応】コーポレートガバナンス報告書の提出",
    description=(
        "主幹事証券会社から指摘を受けました。\n\n"
        "「社長、上場申請に向けて一つ重大な不備があります。\n"
        "コーポレートガバナンス報告書がまだ提出されていません。\n\n"
        "この報告書は上場承認の前提条件です。\n"
        "記載事項：独立社外役員の選任理由・CG原則の実施状況・\n"
        "政策保有株式と関連当事者取引の方針など。\n\n"
        "審査前に必ず提出してください。」\n\n"
        "【ポイント】CG報告書は上場承認の前提条件。未提出では審査通過不可です。"
    ),
    choices=[
        Choice(
            label="A. CG報告書を完成させて提出する（¥5M）",
            description="専門家と協力して内容を充実させ提出。上場承認の前提条件を充足",
            immediate_effect=_fix_governance_report,
            risk_hint="費用¥5M。上場承認前提条件を充足",
        ),
        Choice(
            label="B. 後回しにする（上場承認リスク）",
            description="コスト削減を優先。ただし上場審査での不通過リスクが高まる",
            immediate_effect=_skip_governance_report,
            profit_hint="コスト節減",
            risk_hint="【致命的】CG報告書未提出→上場承認不可。リスク+20",
        ),
    ],
    min_n_period=0,
    max_n_period=0,
    one_shot=True,
    trigger_condition=lambda c: c.has_hofuri and not c.has_governance_report,
)


# ─────────────────────────────────────────────
# 動的リスク回復イベント（リスクスコア60+時に挿入）
# ─────────────────────────────────────────────

def _make_risk_recovery_event(company: Company) -> GameEvent:
    """リスクスコアが高い場合に動的生成されるリスク回復イベント。
    会社の弱点領域を診断して、的を絞った改善施策の意思決定を促す。
    毎ターン再生成されるため one_shot=False でも問題なく機能する。"""

    risk = company.flags.total_risk_score

    # ── 弱点領域を特定 ────────────────────────────────────────────
    weak_areas: list[str] = []
    if company.internal_control_score < 50:
        weak_areas.append("内部管理体制")
    if company.compliance_score < 50:
        weak_areas.append("コンプライアンス体制")
    if company.accounting_quality < 50:
        weak_areas.append("決算品質")
    if company.governance_score < 50:
        weak_areas.append("ガバナンス体制")
    # スコアが比較的高くてもフラグ起因でリスクが高い場合
    if not weak_areas:
        if company.flags.no_voucher_management:
            weak_areas.append("証憑管理")
        if company.flags.unpaid_overtime:
            weak_areas.append("労務管理（未払残業）")
        if company.flags.no_job_separation:
            weak_areas.append("職務分掌（横領リスク）")
        if company.flags.no_related_party_review:
            weak_areas.append("関連当事者取引")
        if company.flags.cash_basis_accounting:
            weak_areas.append("収益認識基準")
    if not weak_areas:
        weak_areas.append("全般的な管理体制")

    weak_str = "・".join(weak_areas[:3])  # 最大3項目を列挙

    # ── リスクレベルに応じたイベント設定 ────────────────────────────
    if risk >= 80:
        tier = "critical"
        title = "【緊急対応】上場審査 危機的リスク ― 全社緊急改善計画"
        _caller = "主幹事証券会社の担当者" if company.has_underwriter else "上場準備アドバイザー"
        desc = (
            f"{_caller}が血相を変えて来社しました。"
            f"「{weak_str}の課題が審査委員会で深刻視されています。"
            f"累積リスクスコアは{risk}ポイントと危機的水準です。"
            f"このまま審査が進めば上場申請の取り下げを勧告せざるを得ません。"
            f"緊急の全社改善計画を今すぐ立案・実行してください。」"
            f"どのように対応しますか？"
        )
        choices_data = [
            ("A. 特別改善委員会を設置し外部専門家チームを総動員する（費用¥50M）", "",
             50.0, -35, 25,
             "リスク大幅低減（−35pt）・各スコア+25",
             "費用¥50M / 根本的な改善が見込める"),
            ("B. 優先度の高い領域に絞って集中的に改善する（費用¥30M）", "",
             30.0, -22, 15,
             "リスク中程度低減（−22pt）・各スコア+15",
             "費用¥30M / バランスの取れた対応"),
            ("C. 最低限の書面整備で審査をやり過ごす（費用¥15M）", "",
             15.0, -10, 7,
             "リスク軽微低減（−10pt）・各スコア+7",
             "費用¥15M / 根本解決には至らない可能性あり"),
        ]
    elif risk >= 70:
        tier = "high"
        title = "【重要改善】IPO審査 要対応リスク ― 管理体制改善委員会の設置"
        desc = (
            f"監査法人から正式な改善勧告書が届きました。"
            f"「{weak_str}に関する課題が継続しており、"
            f"累積リスクスコアは{risk}ポイントと危険域に達しています。"
            f"次回の四半期レビューまでに具体的な改善計画を提出してください。"
            f"放置すると上場審査に重大な影響を及ぼします。」"
            f"どのように対応しますか？"
        )
        choices_data = [
            ("A. 管理体制改善委員会を設置し外部コンサルを活用する（費用¥30M）", "",
             30.0, -25, 18,
             "リスク大幅低減（−25pt）・各スコア+18",
             "費用¥30M / 監査法人の評価が向上"),
            ("B. 社内プロジェクトチームを結成して改善に取り組む（費用¥15M）", "",
             15.0, -15, 10,
             "リスク中程度低減（−15pt）・各スコア+10",
             "費用¥15M / 標準的な対応"),
            ("C. 指摘事項のみ対症療法的に対応する（費用¥8M）", "",
             8.0,  -7,  4,
             "リスク軽微低減（−7pt）・各スコア+4",
             "費用¥8M / 根本原因への対処が不十分な可能性"),
        ]
    else:  # risk 60-69
        tier = "medium"
        title = "【要注意】リスク管理体制の見直し ― 外部専門家によるレビュー"
        desc = (
            f"社内監査役から報告がありました。"
            f"「{weak_str}について改善の余地があります。"
            f"累積リスクスコアが{risk}ポイントまで上昇しており、"
            f"このまま放置するとIPO審査での指摘につながる恐れがあります。"
            f"今のうちに手を打っておくことをお勧めします。」"
            f"どのように対応しますか？"
        )
        choices_data = [
            ("A. 外部専門家によるデューデリジェンスを依頼し包括的に改善する（費用¥20M）", "",
             20.0, -20, 15,
             "リスク低減（−20pt）・各スコア+15",
             "費用¥20M / 先行対応で審査リスクを抑制"),
            ("B. 社内勉強会・研修を実施し体制を見直す（費用¥8M）", "",
             8.0,  -12, 8,
             "リスク低減（−12pt）・各スコア+8",
             "費用¥8M / コストを抑えた標準対応"),
            ("C. 現状の課題を文書化し次期以降の対応を計画する（費用¥2M）", "",
             2.0,  -5,  3,
             "リスク軽微低減（−5pt）・各スコア+3",
             "費用¥2M / 改善効果は限定的"),
        ]

    # ── クロージャでChoiceを生成 ──────────────────────────────────
    def _make_choice(lbl, desc_text, cost, risk_delta, score_delta, p_hint, r_hint,
                     _wa=list(weak_areas)):
        def _effect(c: Company,
                    _cost=cost, _rd=risk_delta, _sd=score_delta, _areas=_wa):
            c.cash -= _cost
            c.flags.total_risk_score = max(0, c.flags.total_risk_score + _rd)
            # 弱点領域ごとに対応スコアを改善
            improved = set()
            if "内部管理体制" in _areas:
                c.internal_control_score = min(100, c.internal_control_score + _sd)
                improved.add("内部管理体制")
            if "コンプライアンス体制" in _areas:
                c.compliance_score = min(100, c.compliance_score + _sd)
                improved.add("コンプライアンス体制")
            if "決算品質" in _areas:
                c.accounting_quality = min(100, c.accounting_quality + _sd)
                improved.add("決算品質")
            if "ガバナンス体制" in _areas:
                c.governance_score = min(100, c.governance_score + _sd)
                improved.add("ガバナンス体制")
            if "証憑管理" in _areas:
                c.accounting_quality = min(100, c.accounting_quality + _sd)
                improved.add("証憑管理→決算品質")
            if "労務管理（未払残業）" in _areas:
                c.compliance_score = min(100, c.compliance_score + _sd)
                improved.add("労務→コンプライアンス")
            if "職務分掌（横領リスク）" in _areas:
                c.internal_control_score = min(100, c.internal_control_score + _sd)
                improved.add("職務分掌→内部管理体制")
            if "関連当事者取引" in _areas:
                c.governance_score = min(100, c.governance_score + _sd)
                improved.add("関連当事者取引→ガバナンス")
            if "収益認識基準" in _areas:
                c.accounting_quality = min(100, c.accounting_quality + _sd)
                improved.add("収益認識→決算品質")
            if "全般的な管理体制" in _areas:
                half = max(1, _sd // 2)
                c.internal_control_score = min(100, c.internal_control_score + half)
                c.compliance_score = min(100, c.compliance_score + half)
                c.accounting_quality = min(100, c.accounting_quality + half)
                c.governance_score = min(100, c.governance_score + half)
                improved.add("全スコア")
            cost_str = f"¥{int(_cost)}M"
            return (
                f"✅ 改善施策を実行しました（費用 {cost_str}）。"
                f"リスクスコアが{abs(_rd)}pt低減しました。"
                f"（改善領域: {'、'.join(improved) if improved else '全般'}）"
            )
        return Choice(
            label=lbl,
            description=desc_text,
            immediate_effect=_effect,
            profit_hint=p_hint,
            risk_hint=r_hint,
        )

    choices = [
        _make_choice(lbl, desc_text, cost, risk_delta, score_delta, p_hint, r_hint)
        for lbl, desc_text, cost, risk_delta, score_delta, p_hint, r_hint in choices_data
    ]

    return GameEvent(
        id=f"risk_recovery_{tier}",
        title=title,
        description=desc,
        choices=choices,
        min_n_period=-3,
        max_n_period=0,
        one_shot=False,  # 毎ターン発火可（get_available_events で制御）
    )


# ─────────────────────────────────────────────
# 新規イベント：月次決算早期化（N-2期）
# ─────────────────────────────────────────────
def _monthly_close_10day(company: Company) -> str:
    company.has_monthly_closing = True
    company.has_budget_control = True  # 10日締め体制には予算実績差異分析が含まれる
    company.cash -= 8.0
    company.accounting_quality = min(100, company.accounting_quality + 15)
    company.internal_control_score = min(100, company.internal_control_score + 10)
    company.quarterly_burn += 1.5  # 経理増員分
    return ("📊 月次決算10日締め体制を構築しました！（¥8M投下）\n\n"
            "   ・会計システムの自動仕訳・連携機能を整備\n"
            "   ・経理スタッフを2名増員（経常費用+¥1.5M/Q）\n"
            "   ・翌月10日確定 → 15日取締役会で予算実績差異分析を報告\n\n"
            "   ▶ 会計品質+15 / 内部統制+10\n"
            "   ▶ 【実務】上場会社は四半期決算の適時開示が義務です。\n"
            "     月次決算の早期化は、適時開示の「インフラ」であり、\n"
            "     P/L・B/S・C/F三表連動の管理体制が審査で評価されます。")


def _monthly_close_20day(company: Company) -> str:
    company.has_monthly_closing = True
    company.cash -= 3.0
    company.accounting_quality = min(100, company.accounting_quality + 8)
    return ("📊 月次決算20日締め体制を整備しました。（¥3M投下）\n\n"
            "   ・既存の会計ソフトを活用した効率化\n"
            "   ・翌月20日前後に月次決算確定\n\n"
            "   ▶ 会計品質+8\n"
            "   ▶ 【注意】上場審査では「翌月10〜15日以内」の確定が理想です。\n"
            "     20日締めでは、取締役会での予算実績差異分析報告が\n"
            "     月末にずれ込み、適時開示体制の実効性に疑義が残ります。")


def _monthly_close_skip(company: Company) -> str:
    company.flags.total_risk_score += 8
    company.accounting_quality = max(0, company.accounting_quality - 5)
    return ("⏭️  月次決算の早期化を見送りました。\n\n"
            "   ▶ 現状の月末ギリギリ決算体制を継続\n"
            "   ▶ 会計品質-5 / リスクスコア+8\n"
            "   ▶ 【警告】月次決算が遅い企業は上場審査で\n"
            "     「適時開示能力に重大な疑義あり」と判断されます。\n"
            "     監査法人からも「管理体制が不十分」として\n"
            "     監査意見に影響する可能性があります。")


EVENT_MONTHLY_CLOSING = GameEvent(
    id="monthly_closing",
    title="月次決算の早期化と経営管理レポート体制",
    description=(
        "CFOからの報告：「社長、月次決算の早期化が急務です。\n\n"
        "上場会社には適時開示（タイムリー・ディスクロージャー）の義務があり、\n"
        "その基盤となるのが月次決算の迅速性です。\n\n"
        "【上場審査で求められる水準】\n"
        "  ・翌月10日以内に月次決算を確定\n"
        "  ・翌月15日前後の取締役会で予算実績差異分析を報告\n"
        "  ・P/L・B/S・C/F三表連動の管理レポート\n\n"
        "現在の当社は月末ギリギリの決算体制です。\n"
        "体制強化にはシステム改修と経理増員が必要ですが、\n"
        "適時開示のインフラとして投資する価値があります。」\n\n"
        "【ポイント】月次決算の速度は上場審査の「管理体制の実効性」評価に直結します。\n"
        "遅い月次決算は適時開示能力の欠如と見なされます。"
    ),
    choices=[
        Choice(
            label="A. 10日締め体制を構築する（¥8M + 経常費用¥1.5M/Q増）",
            description="会計システム改修＋経理増員で最高水準の月次決算体制を構築",
            immediate_effect=_monthly_close_10day,
            risk_hint="コスト大だが審査での評価は最高",
        ),
        Choice(
            label="B. 20日締めで妥協する（¥3M）",
            description="既存システムの効率化で対応。最低限はクリアだが指摘リスクあり",
            immediate_effect=_monthly_close_20day,
            profit_hint="コスト抑制",
            risk_hint="審査で「改善余地あり」と指摘される可能性",
        ),
        Choice(
            label="C. 現状維持（月末ギリギリ決算）",
            description="投資を見送るが、適時開示能力への重大な疑義を招く",
            immediate_effect=_monthly_close_skip,
            risk_hint="審査で「適時開示能力に疑義」と判断。リスク+8",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
)


# ─────────────────────────────────────────────
# 新規イベント：事業部門との軋轢（N-2〜N-1期）
# ─────────────────────────────────────────────
def _org_conflict_full_push(company: Company) -> str:
    company.employee_morale = max(0, company.employee_morale - 12)
    company.internal_control_score = min(100, company.internal_control_score + 15)
    company.compliance_score = min(100, company.compliance_score + 10)
    company.cash -= 5.0
    _tax_msg = _growth_tax(company, 2, mark=True)   # 管理優先の経営判断＝体制投資（恒久負荷）
    return ("🏢 社長のリーダーシップで全社IPOプロジェクトを発足しました！（¥5M投下）\n\n"
            "   ・全部門長参加のIPO推進委員会を毎月開催\n"
            "   ・営業部門に専任の管理担当者を配置\n"
            "   ・「上場準備は全社の成長投資」というメッセージを全社発信\n\n"
            "   ▶ 内部統制+15 / コンプラ+10\n"
            "   ▶ 従業員士気-12（短期的に現場の不満が高まる）\n"
            f"   ▶ {_tax_msg}\n\n"
            "   💬 営業部長：「正直、手続きが増えて大変です。でも社長が本気なら\n"
            "     我々もやるしかありません。上場後の成長に期待します。」\n\n"
            "   ▶ 【実務】IPO準備の最大の障壁は「社内の抵抗」です。\n"
            "     営業活動を優先したい現場にとって、承認手続きの厳格化は\n"
            "     「スピードを削ぐコスト」と映ります。\n"
            "     社長・CFOが前面に立って推進しなければ形骸化します。")


def _org_conflict_gradual(company: Company) -> str:
    company.employee_morale = max(0, company.employee_morale - 4)
    company.internal_control_score = min(100, company.internal_control_score + 5)
    company.cash -= 2.0
    _tax_msg = _growth_tax(company, 1, 2)
    return ("🏢 営業部門に配慮しつつ段階的に管理強化を進めます。（¥2M投下）\n\n"
            "   ・まずは経理・総務部門の業務フロー整備から着手\n"
            "   ・営業部門への導入は半年後を目処に計画\n\n"
            f"   ▶ 内部統制+5 / 従業員士気-4 / {_tax_msg}\n\n"
            "   💬 営業部長：「急に変えないでくれてありがたいです。\n"
            "     ただ、準備が間に合うか心配ですね…」\n\n"
            "   ▶ 【注意】段階的導入では、N-1期までに管理体制が\n"
            "     十分に浸透しないリスクがあります。\n"
            "     上場審査では「1年以上の安定運用実績」が求められます。")


def _org_conflict_backoff(company: Company) -> str:
    company.employee_morale = min(100, company.employee_morale + 5)
    company.internal_control_score = max(0, company.internal_control_score - 8)
    company.flags.total_risk_score += 10
    _boost_msg = _growth_boost(company, 2, 2, mark=True)   # 営業優先の経営判断＝事業投資
    return ("⏭️  営業成長を優先し、管理強化は後回しにしました。\n\n"
            "   ▶ 従業員士気+5（現場は歓迎）\n"
            f"   ▶ 内部統制-8 / リスクスコア+10 / {_boost_msg}\n\n"
            "   💬 CFO：「社長…このままでは上場審査に間に合いません。\n"
            "     営業の数字は良いかもしれませんが、管理体制がザルでは\n"
            "     監査法人も主幹事も首を縦に振りませんよ。」\n\n"
            "   ▶ 【警告】管理体制の未整備は上場審査で最も厳しく指摘されます。\n"
            "     「属人的な運用」から「規程に基づく組織的な運用」への\n"
            "     移行が未完了では、上場は認められません。")


EVENT_ORG_CONFLICT = GameEvent(
    id="org_conflict",
    title="営業部門からの抵抗：管理強化と成長スピードの両立",
    description=(
        "営業本部長から直訴がありました。\n\n"
        "「社長、正直に申し上げます。最近の管理強化で\n"
        "営業の機動力が著しく落ちています。\n\n"
        "・見積書の承認に3日かかるようになった（以前は即日）\n"
        "・経費精算の手続きが煩雑になり、出張申請だけで半日消える\n"
        "・稟議書の形式不備で差し戻しが続出、営業マンが疲弊\n"
        "・顧客対応のスピードが落ち、競合に案件を取られかけている\n\n"
        "このままでは売上目標の達成が厳しいです。\n"
        "上場準備も大事ですが、売上がなければ会社が持ちません。」\n\n"
        "一方、CFOからは：\n"
        "「管理体制の強化は上場審査の生命線です。\n"
        "ここで妥協すれば、N期の審査で全てが水の泡になります。」\n\n"
        "【ポイント】IPO準備の最大の課題は事業部門の反発です。\n"
        "社長の決断が問われています。"
    ),
    choices=[
        Choice(
            label="A. 全社プロジェクトとして推進する（社長主導 / ¥5M）",
            description="短期的に士気は下がるが、管理体制を確実に整備。上場審査での高評価",
            immediate_effect=_org_conflict_full_push,
            risk_hint="従業員士気-12（短期的な現場不満）",
        ),
        Choice(
            label="B. 営業部門に配慮して段階的に導入（¥2M）",
            description="士気への影響を最小化するが、整備が遅れ審査で指摘リスク",
            immediate_effect=_org_conflict_gradual,
            profit_hint="士気への影響小",
            risk_hint="管理体制の浸透が遅れるリスク",
        ),
        Choice(
            label="C. 営業優先で管理強化を後回しにする",
            description="短期の売上を守るが、上場審査の根幹が揺らぐ",
            immediate_effect=_org_conflict_backoff,
            risk_hint="内部統制-8 / リスク+10。審査不通過の主因になり得る",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
)


# ─────────────────────────────────────────────
# 新規イベント：利益操作の誘惑（N-1〜N期）
# ─────────────────────────────────────────────
def _profit_manip_honest(company: Company) -> str:
    company.investor_trust = max(0, company.investor_trust - 10)
    company.compliance_score = min(100, company.compliance_score + 12)
    company.auditor_trust = min(100, company.auditor_trust + 8)
    return ("📉 業績の下方修正を誠実に報告しました。\n\n"
            "   ・取締役会で修正経営計画を承認\n"
            "   ・投資家・VCに対して原因分析と改善策を説明\n"
            "   ・監査法人に対して修正数値の根拠を提示\n\n"
            "   ▶ 投資家信頼-10（短期的な失望）\n"
            "   ▶ コンプラ+12 / 監査法人信頼+8（誠実な開示姿勢を評価）\n\n"
            "   💬 監査法人パートナー：「正直な開示は信頼の基盤です。\n"
            "     短期的には痛いですが、審査では誠実な経営姿勢として\n"
            "     高く評価されるでしょう。」\n\n"
            "   ▶ 【実務】下方修正は投資家にとって不快ですが、\n"
            "     「N期における過年度修正」は遥かに致命的です。\n"
            "     誠実な開示は上場後のIR活動における最大の武器となります。")


def _profit_manip_revenue_front(company: Company) -> str:
    # 売上を一時的にブーストするが、因果応報爆弾がセットされる
    company.revenue.recognized += 15.0  # 不正に¥15M売上計上
    company.flags.profit_manipulation = True
    company.flags.profit_manipulation_type = "revenue_front"
    company.flags.profit_manipulation_bomb_timer = 3  # 3Q後に発覚
    return ("📈 来期の売上¥15Mを今期に前倒し計上しました。\n\n"
            "   ・受注済み案件の検収完了日を「調整」\n"
            "   ・今期の売上が見栄え良くなりました\n\n"
            "   ▶ 売上+¥15M（一時的）\n\n"
            "   💬 経理部長（小声）：「社長、これは…正直言って危ない橋です。\n"
            "     監査法人に見つかったら、取り返しがつきません…」")


def _profit_manip_inventory(company: Company) -> str:
    # 在庫評価を甘くして利益を水増し
    company.revenue.recognized += 8.0  # 原価圧縮→利益増に相当
    company.flags.profit_manipulation = True
    company.flags.profit_manipulation_type = "inventory_inflate"
    company.flags.profit_manipulation_bomb_timer = 4  # 4Q後に発覚（棚卸時）
    return ("📦 棚卸資産の評価を「楽観的」に見直しました。\n\n"
            "   ・滞留在庫の評価減を見送り\n"
            "   ・仕掛品の進捗率を上方修正\n"
            "   ・見かけ上の利益が¥8M改善\n\n"
            "   ▶ 利益+¥8M相当（在庫評価甘め）\n\n"
            "   💬 CFO：「社長、在庫の評価は次の棚卸立会で必ず検証されます。\n"
            "     そのとき辻褄が合わなければ…全てが終わります。」")


EVENT_PROFIT_MANIPULATION = GameEvent(
    id="profit_manipulation",
    title="業績目標と会計処理のジレンマ：利益操作の誘惑",
    description=(
        "CFOからの緊急報告です。\n\n"
        "「社長、深刻な問題があります。\n"
        "今期の業績が当初計画を大幅に下回る見込みです。\n\n"
        "  計画売上：達成率 約75%\n"
        "  営業利益：計画比 ▲30%\n\n"
        "投資家向けに公表した事業計画との乖離が大きく、\n"
        "VCからの信頼に影響が出かねません。\n\n"
        "正直に下方修正を報告するか、それとも…\n"
        "会計処理を『工夫』して数字を作るか。\n\n"
        "社長、どうされますか？」\n\n"
        "【ポイント】不適切な会計処理は典型的なIPO失敗パターンです。\n"
        "売上の先行計上、在庫の過大評価は、監査で発覚すれば\n"
        "審査中止・1年以上の延期、最悪の場合は上場取消しを招きます。"
    ),
    choices=[
        Choice(
            label="A. 正直に下方修正を報告する",
            description="投資家信頼は一時的に下がるが、誠実な経営として監査法人から高評価",
            immediate_effect=_profit_manip_honest,
            profit_hint="コンプラ+12、監査法人信頼+8",
            risk_hint="投資家信頼-10（短期的な失望）",
        ),
        Choice(
            label="B. 来期の売上を今期に前倒し計上する",
            description="受注済み案件の検収日を「調整」。一時的に売上が改善するが…",
            immediate_effect=_profit_manip_revenue_front,
            profit_hint="売上+¥15M（一時的）",
            risk_hint="【危険】監査で発覚した場合、審査中止級の致命的ダメージ",
        ),
        Choice(
            label="C. 棚卸資産の評価を甘くして利益を水増しする",
            description="在庫の評価減を見送り利益を改善。次の棚卸立会が最大のリスク",
            immediate_effect=_profit_manip_inventory,
            profit_hint="利益+¥8M相当",
            risk_hint="【危険】棚卸立会で発覚すれば全てが終わる",
        ),
    ],
    min_n_period=-1,
    max_n_period=0,
    one_shot=True,
    # 業績が目標を下回っている場合にのみ発火
    trigger_condition=lambda c: (c.revenue.recognized < c.quarterly_burn * 1.2
                                  and not c.flags.profit_manipulation),
)


# ─────────────────────────────────────────────
# 新規イベント: 顧客集中リスク対応（N-2〜N-1期）③事業継続性
# ─────────────────────────────────────────────
def _customer_diversification(c: Company) -> str:
    c.has_customer_diversification = True
    c.investor_trust += 12
    c.flags.total_risk_score -= 5
    c.offense_score = getattr(c, "offense_score", 0) + 1   # 🚀 事業投資（新規顧客開拓）
    return ("🏢 顧客分散戦略を実行しました。\n\n"
            "   ・新規顧客開拓により売上上位3社依存度を50%未満に改善\n"
            "   ・業種・規模の異なる顧客層を確保\n"
            "   ・主要顧客との長期契約も並行締結\n\n"
            "   投資家信頼+12 / リスクスコア-5 / 🚀 事業投資+1\n\n"
            "   ▶ 【実務】上場審査での顧客集中リスクの確認ポイント：\n"
            "     ①売上上位顧客の構成比（1社で30%超は要説明）\n"
            "     ②取引継続性の根拠（長期契約・スイッチングコスト）\n"
            "     ③代替顧客獲得の可能性と実績\n"
            "     特定顧客への依存は③事業継続性リスクとして審査で必ず問われます。")


def _disclose_customer_risk(c: Company) -> str:
    c.has_customer_diversification = True
    c.investor_trust += 5
    c.flags.total_risk_score += 5
    return ("📋 顧客集中リスクを有価証券届出書に開示する方針としました。\n\n"
            "   ・上位顧客への依存状況を「事業上のリスク」として明記\n"
            "   ・主要顧客との関係継続の根拠を詳細説明\n"
            "   ・ただし集中そのものは解消されていない\n\n"
            "   投資家信頼+5（誠実な開示）/ リスクスコア+5（集中リスク残存）\n\n"
            "   ▶ 主幹事証券会社から引受時の評価に影響する可能性があります。")


EVENT_CUSTOMER_CONCENTRATION = GameEvent(
    id="customer_concentration",
    title="顧客集中リスクへの対応（売上依存度の分散）",
    description=(
        "主幹事証券会社からの指摘です。\n\n"
        "「御社の売上上位3社で売上の約65%を占めています。\n"
        "上場審査では特定顧客への依存度が高い場合、\n"
        "③事業継続性・収益性の観点から重点的に審査されます。\n\n"
        "【確認事項】\n"
        "  ・主要顧客が離反した場合の影響額と代替可能性\n"
        "  ・長期契約・スイッチングコストの有無\n"
        "  ・新規顧客獲得の実績と見通し\n\n"
        "投資家に対して「再現性のある収益」を示すには、\n"
        "顧客分散か、または集中の合理性の説明が不可欠です。\n\n"
        "【ポイント】顧客集中は③事業継続性の典型的な審査論点です。"
    ),
    choices=[
        Choice(
            label="A. 新規顧客開拓を強化し顧客分散を推進する（¥8M）",
            description="営業リソースを追加投下して依存度を低減。上場審査での高評価",
            immediate_effect=lambda c: (_apply_cost(c, 8.0), _customer_diversification(c))[1],
            profit_hint="投資家信頼+12・リスクスコア-5",
            risk_hint="短期コスト¥8M",
        ),
        Choice(
            label="B. 集中リスクを開示しつつ主要顧客との長期契約を強化する",
            description="事実を誠実に開示。集中そのものは解消されないが透明性を担保",
            immediate_effect=_disclose_customer_risk,
            profit_hint="コスト抑制・誠実開示",
            risk_hint="集中リスク残存・引受評価への影響",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
    trigger_condition=lambda c: not getattr(c, 'has_customer_diversification', False),
)


# ─────────────────────────────────────────────
# 新規イベント: キーパーソン依存リスク（N-2〜N-1期）⑦組織・人材
# ─────────────────────────────────────────────
def _build_succession_plan(c: Company) -> str:
    c.has_succession_plan = True
    c.governance_score += 15
    c.investor_trust += 8
    c.employee_morale += 10
    c.quarterly_burn += 2.0
    return ("🏛️  後継者育成・組織体制強化を実施しました。\n\n"
            "   ・事業部門ごとに副責任者を任命し権限委譲を推進\n"
            "   ・業務マニュアルの整備により組織的運営体制を確立\n"
            "   ・CFO・CTOなど経営幹部の後継者候補を育成中\n"
            "   ・組織図と職務記述書（JD）を整備\n\n"
            "   ガバナンス+15 / 投資家信頼+8 / 士気+10（人件費¥2M/Q増）\n\n"
            "   ▶ 【実務】上場審査での⑦組織・人材の確認ポイント：\n"
            "     ①キーパーソンが抜けても業務が継続できる体制か\n"
            "     ②「人ではなく組織で回る会社」か\n"
            "     ③管理部門（経理・法務等）の専門人材の充足度\n"
            "     特定人物への依存は上場後の経営リスクと評価されます。")


def _accept_key_person_risk(c: Company) -> str:
    c.has_succession_plan = False
    c.flags.total_risk_score += 12
    return ("⚠️  現在の体制を維持することにしました。\n\n"
            "   ・創業者・CEOが引き続き主要業務を把握・判断\n"
            "   ・権限委譲は最小限にとどめる\n\n"
            "   リスクスコア+12（キーパーソン依存リスク）\n\n"
            "   ▶ 主幹事証券会社から「組織的な運営体制の構築」を\n"
            "     上場審査条件として求められる可能性があります。\n"
            "     有価証券届出書のリスク項目にキーパーソンリスクを\n"
            "     記載する必要が生じます。")


EVENT_KEY_PERSON_RISK = GameEvent(
    id="key_person_risk",
    title="キーパーソン依存リスクの解消（組織的運営体制の構築）",
    description=(
        "主幹事証券会社からのフィードバックです。\n\n"
        "「事業計画説明会で、CEOが全事業領域の詳細を\n"
        "単独で把握・判断している印象を受けました。\n\n"
        "上場審査では⑦組織・人材の観点として：\n"
        "  ・特定個人への依存が大きい場合、その離脱が重大リスクと評価\n"
        "  ・『人ではなく組織で回る会社』かどうかが判断軸\n"
        "  ・管理部門（経理・法務・総務）の専門人材の充足も確認される\n\n"
        "後継者計画と権限委譲の体制整備が推奨されます。」\n\n"
        "【ポイント】キーパーソン依存は⑦組織・人材リスクの典型論点です。"
    ),
    choices=[
        Choice(
            label="A. 後継者育成と権限委譲を本格的に推進する（¥2M/Q）",
            description="組織的な運営体制を整備。幹部育成・マニュアル整備・JD策定",
            immediate_effect=_build_succession_plan,
            profit_hint="ガバナンス+15・投資家信頼+8",
            risk_hint="人件費¥2M/Q追加",
        ),
        Choice(
            label="B. 現体制を維持し、リスクとして開示する",
            description="整備コストを避けるが、キーパーソンリスクが審査論点として残る",
            immediate_effect=_accept_key_person_risk,
            profit_hint="コスト削減",
            risk_hint="キーパーソン依存リスク+12。審査での指摘必至",
        ),
    ],
    min_n_period=-2,
    max_n_period=-1,
    one_shot=True,
    trigger_condition=lambda c: not getattr(c, 'has_succession_plan', False),
)


# ─────────────────────────────────────────────
# 全イベントリスト
# ─────────────────────────────────────────────
ALL_EVENTS = [
    # ── N-3期：体制構築 ＋ 株主数の種まき ──────────────────────
    # ★ 株主数増加イベントは get_available_events() の優先ロジックにより
    #   他のイベントより先に発火します（順番は保険として先頭寄りに配置）
    EVENT_SHORT_REVIEW,          # ショートレビュー（N-3最重要）
    EVENT_AUDIT_FIRM_SELECTION,  # 監査法人候補の選定（N-3期）④
    EVENT_FUNDRAISING,           # 資金調達（株主数+80）★優先
    # EVENT_SO_PROGRAM は廃止 → SOの設計・特別決議はN-3期Q4の定時株主総会AGMで処理
    EVENT_ESOP,                  # 従業員持株会（実株主 毎Q+3）★優先
    EVENT_CFO_HIRING,            # CFO採用
    EVENT_UNDERWRITER,           # 主幹事証券会社選定（N-3理想・N-2最遅 → 早期配置）
    EVENT_BUSINESS_PLAN,         # 中期経営計画策定
    EVENT_ORG_BUILDING,          # 組織体制強化
    EVENT_IT_SYSTEMS,            # ERPシステム整備
    EVENT_VOUCHER_MANAGEMENT,    # 証憑管理
    EVENT_ACCRUAL_ACCOUNTING,    # 発生主義移行
    EVENT_INVENTORY,             # 棚卸資産管理
    EVENT_WHISTLEBLOWER,         # 【実務検定】内部通報制度（N-3〜N-2）
    EVENT_SALES_GROWTH_EARLY,    # 売上成長前半（繰返）
    EVENT_BOARD_STRATEGY,        # 取締役会：戦略議論（繰返）
    # ── N-2期：整備・運用 ＋ 大型ファイナンス ──────────────────
    EVENT_SERIES_BC,             # シリーズB 大型ファイナンス（株主数+180）★優先
    EVENT_AGM_ANGEL_EXIT,        # 株主総会：エンジェル出口要求
    EVENT_MONTHLY_CLOSING,       # 月次決算早期化（N-2〜N-1）★新規
    EVENT_ORG_CONFLICT,          # 事業部門との軋轢（N-2〜N-1）★新規
    EVENT_LABOR,                 # 労務管理
    EVENT_JOB_SEPARATION,        # 職務分掌
    EVENT_ANTISOCIAL_CHECK,      # 反社チェック
    EVENT_RELATED_PARTY,         # 関連当事者取引
    EVENT_OUTSIDE_DIRECTOR,      # 社外役員選任（N-3〜N-2）⑩ ※N-1期は緊急版が担当
    EVENT_OUTSIDE_DIRECTOR_N1,   # 社外役員 N-1期 最終機会（選任済みなら発火しない）
    EVENT_EOGM_ARTICLES_AMENDMENT,  # 定款変更 N期 臨時総会で再上程（否決フラグ立ち時）
    EVENT_JSOX,                  # J-SOX準備
    # ── 補完イベント群（チェックポイント網羅） ────────────────
    EVENT_AUTHORITY_RULES,       # 職務権限・業務分掌規程（N-2）④
    EVENT_BUDGET_CONTROL,        # 予算管理制度（N-2）④
    EVENT_INTERNAL_AUDIT,        # 内部監査部門（N-2）②
    EVENT_IP_PROTECTION,         # 知財保護（N-2）⑧
    EVENT_CUSTOMER_CONCENTRATION, # 顧客集中リスク（N-2〜N-1）③
    EVENT_KEY_PERSON_RISK,        # キーパーソン依存（N-2〜N-1）⑦
    EVENT_ACCOUNTING_AUDITOR,    # 会計監査人 正式選任（N-1）
    EVENT_FINAL_LISTING_PROCEDURE,  # ほふり・定款・CG報告書（N期）
    EVENT_GOVERNANCE_REPORT_FIX,    # CG報告書修正（N期 / partial選択後）
    # EVENT_MARKET_SELECTION: 市場区分はゲーム開始時に選択済み → 削除
    EVENT_INSIDER_TRADING,       # 【実務検定】インサイダー取引防止
    EVENT_ESG_DISCLOSURE,        # 【実務検定】ESG/サステナビリティ開示
    EVENT_PREFERRED_CONVERSION,  # 【実務検定】種類株式の転換（資本政策）
    EVENT_AGM_VC_GRILLING,       # 株主総会：VC業績追及
    EVENT_AGM_DILUTION,          # 株主総会：希薄化・資本政策議論
    EVENT_BOARD_COMPENSATION,    # 取締役会：役員報酬制度整備
    EVENT_KANSAYAKU_REPORT,      # 監査役：内部統制指摘（低IC時・繰返）
    EVENT_KANSAYAKU_INDEPENDENCE, # 監査役：独立性問題
    # ── N-1期〜N期：本格運用・申請 ＋ ロードショー ──────────────
    EVENT_PROFIT_MANIPULATION,   # 利益操作の誘惑（N-1〜N期）★新規
    EVENT_N_SO_EXERCISE,         # N期SO行使（潜在→実株主）★優先
    EVENT_PUBLIC_OFFERING,       # 上場時公募・売出し（株主数充足の本丸・N期）★最優先
    EVENT_PREIPO_ROADSHOW,       # 機関投資家ロードショー（N-1〜N期）
    EVENT_SALES_GROWTH_LATE,     # 売上成長後半（繰返）
    EVENT_STOCK_ADMIN,           # 株式事務・定款整備
    EVENT_IR_SETUP,              # IR・適時開示体制
    EVENT_STOCK_SPLIT,           # 【実務検定】株式分割（資本政策・N-1〜N）
    EVENT_DISCLOSURE_DRILL,      # 【実務検定】適時開示ドリル
    EVENT_LOCKUP_POLICY,         # 【実務検定】ロックアップ設定
    EVENT_PROSPECTUS,            # 有価証券届出書準備
    EVENT_IPO_PRICING,           # 公開価格戦略（N期）
]


def get_fresh_events() -> list:
    """ゲーム開始時に使うイベントリストの完全な新規コピーを返す。
    ALL_EVENTS はモジュールレベルのシングルトンなので、
    同一プロセス内で複数ゲームを行うと fired フラグが残ってしまう。
    毎ゲーム開始時にこの関数でディープコピーを作成すること。"""
    return copy.deepcopy(ALL_EVENTS)


def get_available_events(company: "Company", n_period: int,
                         events: list | None = None,
                         quarter: int = 1) -> list:
    """現在のターンで発火可能なイベントを返す（最大2件）。
    株主数増加イベント（SO付与・シリーズB/C・ロードショー）は優先的に先頭に並べる。
    チェックリスト必須イベントも優先発火させ、上場準備項目が必ず意思決定できるようにする。

    events を省略した場合はモジュール共有の ALL_EVENTS を使う（後方互換）。
    推奨: ゲームセッションごとに get_fresh_events() で取得したリストを渡す。"""
    # 株主数増加に直接関係するイベントID（第1優先）
    SHAREHOLDER_PRIORITY_IDS = {
        # "so_program" は廃止 → AGM（N-3期Q4）で処理するため削除
        "esop_setup",            # 従業員持株会（実株主を毎Q積み上げ）
        "n_so_exercise",         # N期SO行使（潜在→実株主）
        "public_offering",       # 上場時公募・売出し（株主数充足の本丸）
        "series_a_fundraising",  # 資金調達
        "series_bc_fundraising", # シリーズB/C
        "preipo_roadshow",       # 機関投資家ロードショー
        "outside_director",      # 社外役員選任（N-3〜N-2 最優先）ガバナンス要件
    }
    # チェックリスト必須イベントID（第2優先）— 必ず意思決定できるよう保証
    CHECKLIST_MUST_FIRE_IDS = {
        # ── N-3期 体制構築 ────────────────────────────────────
        "short_review",                # ショートレビュー（N-3最重要①②）
        "audit_firm_selection",        # 監査法人候補選定（N-3期②）
        "cfo_hiring",                  # CFO採用（N-3〜N-2 ②⑦）
        "business_plan",               # 中期経営計画（N-3③④）
        "labor_management",            # 労務コンプライアンス（N-3〜N-1 ①）
        "job_separation",              # 職務分掌（N-3〜N-1 ①②）
        "voucher_management",          # 証憑管理（N-3〜N-2 ②）
        "accrual_accounting",          # 発生主義移行（N-3〜N-2 ②）
        "inventory_management",        # 棚卸管理（N-3〜N-2 ②）
        "antisocial_check",            # 反社チェック（N-3〜N-1 ①）
        # ── N-2期 整備・運用 ─────────────────────────────────
        "related_party_transactions",  # 関連当事者（N-2〜N期 ⑥）
        "authority_rules",             # 職務権限規程（N-2〜N-1 ②④）
        "budget_control",              # 予算管理制度（N-2〜N-1 ④）
        "internal_audit",              # 内部監査部門（N-2〜N-1 ②）
        "jsox_preparation",            # 内部統制システム（N-2〜N-1 ②）
        "ip_protection",               # 知財保護（N-2 ⑧）
        "customer_concentration",      # 顧客集中リスク（N-2〜N-1 ③）
        "key_person_risk",             # キーパーソン依存（N-2〜N-1 ⑦）
        "outside_director",            # 社外役員選任（N-3〜N-1 ①）
        "outside_director_urgent",     # 社外役員 N-1期 最終機会
        "monthly_closing",             # 月次決算早期化（N-2〜N-1 ②④）
        "underwriter_selection",       # 主幹事証券会社選定（N-3〜N-1 ⑩）
        # ── N-1期〜N期 申請対応 ──────────────────────────────
        "insider_trading_prevention",  # インサイダー防止（N-1〜N ①）
        "ir_setup",                    # 適時開示体制（N-1〜N ②）
        "final_listing_procedure",     # ほふり・定款・CG報告書（N期）
        "governance_report_fix",       # CG報告書修正（N期）
        "eogm_articles_amendment",     # 定款変更 N期 臨時総会で再上程
    }

    src = events if events is not None else ALL_EVENTS
    available = [e for e in src if e.can_fire(company, n_period)]

    # 優先度別に分類
    priority     = [e for e in available if e.id in SHAREHOLDER_PRIORITY_IDS]
    checklist    = [e for e in available if e.id in CHECKLIST_MUST_FIRE_IDS]
    others       = [e for e in available if e.id not in SHAREHOLDER_PRIORITY_IDS
                                        and e.id not in CHECKLIST_MUST_FIRE_IDS]
    random.shuffle(others)   # ← リプレイ性のためシャッフル

    # ── リスクスコアが高い場合、リスク回復イベントを最優先で挿入 ──────
    risk = company.flags.total_risk_score
    if risk >= 60:
        recovery = _make_risk_recovery_event(company)
        # チェックリスト > 株主数 > その他 の順で残り1スロットを埋める
        fill = (checklist + priority + others)[:1]
        return [recovery] + fill

    # ── Q4：期限切れCHECKLISTを全発火（2件制限を撤廃）──────────────
    if quarter == 4:
        expiring     = [e for e in checklist if e.max_n_period == n_period]
        non_expiring = [e for e in checklist if e.max_n_period != n_period]
        if expiring:
            # 期限切れ全件 + priorityから残スロット（AGMと合わせて過負荷を避けるため上限4件）
            remaining = max(0, 4 - len(expiring))
            pool_q4 = expiring + (priority + non_expiring)[:remaining]
            return pool_q4

    # 通常：株主数 > チェックリスト > その他 の順で最大2件
    pool = priority + checklist + others
    return pool[:2]


# ─────────────────────────────────────────────
# ヘルパー
# ─────────────────────────────────────────────
def _apply_cost(company: Company, cost: float) -> None:
    company.cash -= cost


def _add_score(company: "Company", field: str, delta: int) -> str:
    """逓減計算付きスコア加算。80点超→×0.5、90点超→×0.25。
    Returns note string (empty if no reduction applied)."""
    if delta <= 0:
        setattr(company, field, max(0, getattr(company, field, 0) + delta))
        return ""
    current = getattr(company, field, 0)
    if current >= 90:
        applied = max(1, round(delta * 0.25))
        note = f"（90点超逓減: +{delta}→+{applied}）" if applied < delta else ""
    elif current >= 80:
        applied = max(1, round(delta * 0.5))
        note = f"（80点超逓減: +{delta}→+{applied}）" if applied < delta else ""
    else:
        applied = delta
        note = ""
    setattr(company, field, min(100, current + applied))
    return note
