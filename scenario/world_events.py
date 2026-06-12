"""
世界イベント（ランダムルーレット）
毎四半期、外部環境の変化が会社に影響を与える
"""
import copy
import random
from dataclasses import dataclass, field
from typing import List, Optional
from models.company import Company
from models.events import Choice


@dataclass
class WorldEvent:
    id: str
    title: str
    category: str   # geopolitics / epidemic / demand / scandal / social / economy
    description: str
    choices: List[Choice]
    probability: float = 0.35
    one_shot: bool = True
    fired: bool = False
    last_fired_n_period: int = field(default=-99)
    target_biz: Optional[List[str]] = None   # None=全業種, ["SaaS","FinTech"]等で業種絞込
    min_n_period: int = -3                    # 発火最小N期

    def eligible(self) -> bool:
        return not (self.one_shot and self.fired)


def get_fresh_world_events() -> list:
    return copy.deepcopy(WORLD_EVENTS)


def roll_world_event(events: list, n_period: int, biz_type: str = "") -> Optional["WorldEvent"]:
    """50%の確率で世界イベントを1件発生させる（業種フィルタ付き）"""
    if random.random() > 0.50:   # 35% → 50% に引き上げ
        return None
    eligible = [
        e for e in events
        if e.eligible()
        and e.last_fired_n_period != n_period   # 同一N期内での重複発火を防止
        and n_period >= e.min_n_period
        and (e.target_biz is None or biz_type in (e.target_biz or []))
    ]
    if not eligible:
        return None
    weights = [e.probability for e in eligible]
    total = sum(weights)
    r = random.random() * total
    cumulative = 0.0
    for e, w in zip(eligible, weights):
        cumulative += w
        if r <= cumulative:
            return e
    return eligible[-1]


# ══════════════════════════════════════════════
# イベント効果関数
# ══════════════════════════════════════════════

# ── 中東戦争・原油高騰 ──────────────────────────
def _war_cost_cut(c: Company) -> str:
    c.cash -= 10
    c.quarterly_burn = max(0, c.quarterly_burn - 8)
    return (
        "✅ 緊急コスト削減を実施しました。\n"
        "   輸送業者と緊急再交渉し、在庫を最適化することで費用増加を抑制。\n"
        "   ▶ 現金-¥10M / 四半期費用-¥8M\n"
        "   【学習ポイント】外部環境リスクへの即時対応が競合との差を生みます。"
    )

def _war_watch(c: Company) -> str:
    c.quarterly_burn += 35
    c.investor_trust = max(0, c.investor_trust - 12)
    c.cash -= 20
    return (
        "❌ 様子見の間に輸送コストが急騰。四半期費用が¥35M増加し財務を直撃しました。\n"
        "   「なぜ早期対応しなかったのか」投資家・監査法人から厳しい指摘が届いています。\n"
        "   ▶ 四半期費用+¥35M（恒久増加） / 現金-¥20M / 投資家信頼-12\n"
        "   【学習ポイント】地政学リスクの初動遅れは、財務への長期ダメージになります。"
    )

def _war_diversify(c: Company) -> str:
    c.cash -= 20
    c.quarterly_burn = max(0, c.quarterly_burn - 10)
    c.compliance_score = min(100, c.compliance_score + 3)
    return (
        "✅ サプライチェーン多様化を完了しました。\n"
        "   複数の調達先を確保し、地政学リスクへの耐性が向上しました。\n"
        "   ▶ 現金-¥20M / 四半期費用-¥10M / コンプライアンス+3\n"
        "   【学習ポイント】BCP（事業継続計画）は上場審査でも評価されます。"
    )

# ── パンデミック ──────────────────────────────
def _pandemic_remote(c: Company) -> str:
    c.cash -= 15
    c.employee_morale = min(100, c.employee_morale + 5)
    c.internal_control_score = min(100, c.internal_control_score + 5)
    return (
        "✅ 全社リモートワーク移行を完了しました。\n"
        "   ITインフラを整備し、従業員の安全を確保しながら事業を継続できています。\n"
        "   ▶ 現金-¥15M / 従業員士気+5 / 内部統制+5\n"
        "   【学習ポイント】デジタル化への先行投資はIPO後も競争力の源泉になります。"
    )

def _pandemic_bcp(c: Company) -> str:
    c.cash -= 25
    c.compliance_score = min(100, c.compliance_score + 10)
    c.investor_trust = min(100, c.investor_trust + 5)
    return (
        "✅ 事業継続計画（BCP）を本格発動しました。\n"
        "   費用は大きいですが、最も確実な事業継続を実現。投資家からも高評価を得ました。\n"
        "   ▶ 現金-¥25M / コンプライアンス+10 / 投資家信頼+5\n"
        "   【学習ポイント】BCP整備は上場審査のリスク管理評価でもプラスに働きます。"
    )

def _pandemic_ignore(c: Company) -> str:
    c.flags.total_risk_score += 25
    c.employee_morale = max(0, c.employee_morale - 25)
    c.investor_trust = max(0, c.investor_trust - 20)
    c.quarterly_burn += 15
    return (
        "❌ クラスターが発生。政府から事業停止命令を受け、操業が2週間中断しました。\n"
        "   主要幹部が感染し、IPO準備が大幅に遅延。監査法人から懸念事項の書面が届きました。\n"
        "   ▶ リスクスコア+25 / 従業員士気-25 / 投資家信頼-20 / 四半期費用+¥15M\n"
        "   【学習ポイント】感染症軽視は事業継続そのものを脅かします。"
    )

# ── 大地震 ──────────────────────────────────
def _quake_bcp(c: Company) -> str:
    c.cash -= 10
    c.employee_morale = min(100, c.employee_morale + 5)
    c.investor_trust = min(100, c.investor_trust + 3)
    return (
        "✅ BCP発動・保険請求を速やかに実施しました。\n"
        "   迅速な対応で従業員・取引先からの信頼を維持できました。\n"
        "   ▶ 現金-¥10M / 従業員士気+5 / 投資家信頼+3\n"
        "   【学習ポイント】自然災害への備えは上場企業として必須の経営課題です。"
    )

def _quake_repair(c: Company) -> str:
    c.cash -= 30
    c.internal_control_score = min(100, c.internal_control_score + 8)
    return (
        "✅ 緊急修繕工事でオフィスを完全復旧しました。\n"
        "   費用は大きかったですが、事業継続体制が確実に整いました。\n"
        "   ▶ 現金-¥30M / 内部統制+8\n"
        "   【学習ポイント】施設の安全確保と事業継続体制は内部統制の重要要素です。"
    )

def _quake_remote(c: Company) -> str:
    c.cash -= 20
    c.employee_morale = max(0, c.employee_morale - 10)
    return (
        "⚡ 急遽リモートワークに切り替えましたが、従業員の混乱が続いています。\n"
        "   システム整備が追い付かず、生産性が一時的に大幅低下しました。\n"
        "   ▶ 現金-¥20M / 従業員士気-10\n"
        "   【学習ポイント】リモート環境は事前整備が重要。急な切替は混乱を招きます。"
    )

# ── 仕入先不祥事 ──────────────────────────────
def _supplier_switch(c: Company) -> str:
    c.cash -= 20
    c.compliance_score = min(100, c.compliance_score + 5)
    c.investor_trust = min(100, c.investor_trust + 3)
    return (
        "✅ 問題のある取引先との取引を即時停止し、代替調達先を確保しました。\n"
        "   迅速な対応で投資家・監査法人からの信頼を守りました。\n"
        "   ▶ 現金-¥20M / コンプライアンス+5 / 投資家信頼+3\n"
        "   【学習ポイント】反社・コンプライアンス問題は「知らなかった」では通りません。"
    )

def _supplier_statement(c: Company) -> str:
    c.cash -= 5
    c.investor_trust = max(0, c.investor_trust - 8)
    return (
        "⚡ 共同声明を発表しましたが、投資家・メディアの疑念は払拭できていません。\n"
        "   「なぜ取引継続したのか」という追及が続いています。\n"
        "   ▶ 現金-¥5M / 投資家信頼-8（疑念払拭できず）\n"
        "   【学習ポイント】声明だけでは不十分。取引関係の見直しが求められます。"
    )

def _supplier_continue(c: Company) -> str:
    c.flags.total_risk_score += 15
    return (
        "❌ 継続取引を選んだ結果、御社も「共犯者」として報道されました。\n"
        "   上場審査での取引先調査で重大な問題として指摘されるリスクが急増しています。\n"
        "   ▶ リスクスコア+15（上場審査で致命的な問題になる可能性）\n"
        "   【学習ポイント】取引先の不祥事は経営者の判断力・ガバナンスの問題として問われます。"
    )

# ── 主要顧客危機 ──────────────────────────────
def _customer_collect(c: Company) -> str:
    c.cash += 30
    c.investor_trust = max(0, c.investor_trust - 5)
    return (
        "✅ 売掛金¥30Mを速やかに回収しました。財務リスクを最小化できました。\n"
        "   厳格な与信管理の姿勢は、投資家から「慎重すぎる」と見られた面もあります。\n"
        "   ▶ 現金+¥30M（回収完了） / 投資家信頼-5\n"
        "   【学習ポイント】与信管理は財務の健全性を守る重要な管理業務です。"
    )

def _customer_support(c: Company) -> str:
    c.cash -= 30
    c.investor_trust = min(100, c.investor_trust + 3)
    return (
        "⚡ 顧客支援を選択しましたが、回収リスクが残っています。\n"
        "   義理人情の判断が財務に大きな影響を与える可能性があります。\n"
        "   ▶ 現金-¥30M（回収リスクあり） / 投資家信頼+3\n"
        "   【学習ポイント】感情的な判断より、財務的なリスク分析が経営者に求められます。"
    )

def _customer_new(c: Company) -> str:
    c.cash -= 15
    c.revenue.recognized *= 0.9
    c.compliance_score = min(100, c.compliance_score + 5)
    return (
        "✅ 新規顧客開拓に集中し、顧客集中リスクを分散しました。\n"
        "   短期売上は下がりましたが、健全な顧客ポートフォリオに近づきました。\n"
        "   ▶ 現金-¥15M / 短期売上-10% / コンプライアンス+5\n"
        "   【学習ポイント】特定顧客への売上集中は上場審査でリスクとして指摘されます。"
    )

# ── AI/DXブーム ───────────────────────────────
def _ai_efficiency(c: Company) -> str:
    c.cash -= 20
    c.quarterly_burn = max(0, c.quarterly_burn - 15)
    c.accounting_quality = min(100, c.accounting_quality + 5)
    c.offense_score = getattr(c, "offense_score", 0) + 1   # 🚀 事業投資（¥20M規模）
    return (
        "✅ AIによる業務効率化を実装しました。\n"
        "   経理・内部統制業務のAI化で、費用削減と品質向上を同時に達成しました。\n"
        "   ▶ 現金-¥20M / 四半期費用-¥15M / 会計品質+5 / 🚀 事業投資+1\n"
        "   【学習ポイント】DX投資は上場後も競争優位の源泉。早期実装が重要です。"
    )

def _ai_product(c: Company) -> str:
    c.cash -= 40
    c.revenue.recognized *= 1.20
    c.investor_trust = min(100, c.investor_trust + 10)
    c.offense_score = getattr(c, "offense_score", 0) + 2   # 🚀 事業投資（¥40M大型投資=2点）
    return (
        "✅ AIプロダクトの市場投入に成功しました！\n"
        "   大型投資が実を結び、売上が20%増加。投資家からの評価も急上昇しています。\n"
        "   ▶ 現金-¥40M / 売上+20% / 投資家信頼+10 / 🚀 事業投資+2\n"
        "   【学習ポイント】成長ストーリーの明確な企業は上場審査でも高く評価されます。"
    )

def _ai_wait(c: Company) -> str:
    c.investor_trust = max(0, c.investor_trust - 5)
    return (
        "⚡ 様子見を選択しましたが、競合他社がシェアを拡大しています。\n"
        "   投資家から「なぜAI投資をしないのか」という懸念の声が上がっています。\n"
        "   ▶ 投資家信頼-5（機会損失・成長性への懸念）\n"
        "   【学習ポイント】技術トレンドへの対応遅れは、IPO後の成長性評価にも響きます。"
    )

# ── 政府補助金 ────────────────────────────────
def _subsidy_apply(c: Company) -> str:
    c.cash += 50
    c.compliance_score = min(100, c.compliance_score + 3)
    c.investor_trust = min(100, c.investor_trust + 3)
    return (
        "✅ 補助金審査に採択されました！¥50Mの資金を獲得しました。\n"
        "   適切な申請書類の準備が評価され、デジタル認定も取得できました。\n"
        "   ▶ 現金+¥50M / コンプライアンス+3 / 投資家信頼+3\n"
        "   【学習ポイント】補助金活用はIPO準備資金の有力な調達手段の一つです。"
    )

def _subsidy_rush(c: Company) -> str:
    c.cash += 30
    c.flags.total_risk_score += 5
    return (
        "⚡ 急ぎ申請で部分採択となりました。¥30Mを獲得しましたが書類に不備がありました。\n"
        "   書類の不備が後の監査で問題になる可能性があります。\n"
        "   ▶ 現金+¥30M / リスクスコア+5（書類不備の懸念）\n"
        "   【学習ポイント】補助金申請も正確な書類が重要。焦りは後の問題を生みます。"
    )

def _subsidy_skip(c: Company) -> str:
    return (
        "── 補助金申請を見送りました。\n"
        "   コストと手間を省きましたが、資金獲得の機会を逃しました。\n"
        "   ▶ 変化なし（機会損失）\n"
        "   【学習ポイント】補助金・助成金情報は常にアンテナを張っておきましょう。"
    )

# ── 為替ショック ──────────────────────────────
def _fx_hedge(c: Company) -> str:
    c.cash -= 10
    c.compliance_score = min(100, c.compliance_score + 5)
    c.investor_trust = min(100, c.investor_trust + 5)
    return (
        "✅ 為替ヘッジ契約を締結し、為替変動リスクを排除しました。\n"
        "   財務の安定性が高まり、投資家からの信頼も向上しました。\n"
        "   ▶ 現金-¥10M / コンプライアンス+5 / 投資家信頼+5\n"
        "   【学習ポイント】為替リスクの管理と開示は上場企業の財務管理の基本です。"
    )

def _fx_export(c: Company) -> str:
    c.revenue.recognized *= 1.15
    return (
        "✅ 円安を追い風に輸出を強化し、売上が15%増加しました。\n"
        "   ただし為替リスクは継続しており、円高転換時の影響も想定しておく必要があります。\n"
        "   ▶ 売上+15%（為替リスクは継続中）\n"
        "   【学習ポイント】為替リスクの開示は投資家へのフェアな情報提供として重要です。"
    )

def _fx_nothing(c: Company) -> str:
    c.quarterly_burn += 10
    c.cash -= 20
    return (
        "❌ 為替対策を怠った結果、輸入コストが直撃しました。\n"
        "   クラウドサービス費・部品費が急騰し、四半期費用が大幅増加しています。\n"
        "   ▶ 四半期費用+¥10M / 現金-¥20M（輸入コスト直撃）\n"
        "   【学習ポイント】財務リスクへの無対応は経営者としての責任問題になります。"
    )

# ── 人材不足 ──────────────────────────────────
def _labor_raise(c: Company) -> str:
    c.cash -= 30
    c.quarterly_burn += 20
    c.employee_morale = min(100, c.employee_morale + 15)
    return (
        "✅ 全エンジニアへの大幅賃上げを実施し、人材流出を防ぎました。\n"
        "   士気が大幅に向上し、IPO準備業務の生産性が改善されました。\n"
        "   ▶ 現金-¥30M / 四半期費用+¥20M（恒久増加） / 従業員士気+15\n"
        "   【学習ポイント】IPO準備期間中の人材確保は最優先課題の一つです。"
    )

def _labor_global(c: Company) -> str:
    c.cash -= 25
    c.employee_morale = min(100, c.employee_morale + 10)
    c.governance_score = min(100, c.governance_score + 5)
    return (
        "✅ 海外エンジニアの採用に成功しました。チームの多様性も高まっています。\n"
        "   グローバルな視点がIPO後の成長戦略にも好影響を与えそうです。\n"
        "   ▶ 現金-¥25M / 従業員士気+10 / ガバナンス+5\n"
        "   【学習ポイント】多様性ある経営陣・チームは投資家からも高く評価されます。"
    )

def _labor_nothing(c: Company) -> str:
    c.employee_morale = max(0, c.employee_morale - 30)
    c.flags.total_risk_score += 12
    c.revenue.recognized *= 0.88
    c.internal_control_score = max(0, c.internal_control_score - 10)
    return (
        "❌ 主要エンジニア5名が一斉退職。IPO準備の中核システム担当者が全員いなくなりました。\n"
        "   内部統制整備が半年遅延し、監査法人から「準備不足」を指摘されています。\n"
        "   ▶ 従業員士気-30 / リスクスコア+12 / 売上-12% / 内部統制-10\n"
        "   【学習ポイント】人材流出はIPOの最大のリスクの一つです。給与は投資です。"
    )

# ── SNS炎上 ──────────────────────────────────
def _sns_apologize(c: Company) -> str:
    c.cash -= 15
    c.investor_trust = max(0, c.investor_trust - 5)
    c.compliance_score = min(100, c.compliance_score + 8)
    return (
        "✅ 公式謝罪と改善策を発表しました。誠実な対応が功を奏しつつあります。\n"
        "   短期的な信頼低下はあるものの、透明性ある対応が長期的な回復につながります。\n"
        "   ▶ 現金-¥15M / 投資家信頼-5（短期） / コンプライアンス+8\n"
        "   【学習ポイント】問題発生時の誠実な初動対応が、企業の真価を問います。"
    )

def _sns_legal(c: Company) -> str:
    c.cash -= 20
    c.compliance_score = min(100, c.compliance_score + 3)
    c.flags.total_risk_score += 5
    return (
        "⚡ 法的対応を選択しました。事実関係の整理には時間がかかっています。\n"
        "   訴訟の長期化により、IPOスケジュールへの影響が懸念されます。\n"
        "   ▶ 現金-¥20M / コンプライアンス+3 / リスクスコア+5（訴訟長期化リスク）\n"
        "   【学習ポイント】法的手段は最後の手段。コミュニケーション対応を先に検討すべきです。"
    )

def _sns_ignore(c: Company) -> str:
    c.investor_trust = max(0, c.investor_trust - 35)
    c.flags.total_risk_score += 25
    c.employee_morale = max(0, c.employee_morale - 15)
    c.auditor_trust = max(0, c.auditor_trust - 10)
    return (
        "❌ 無視を選択した結果、炎上が1ヶ月以上続き企業価値が激しく毀損しました。\n"
        "   主幹事証券会社が引受辞退を通告。監査法人からも追加説明を求められています。\n"
        "   ▶ 投資家信頼-35 / リスクスコア+25 / 従業員士気-15 / 監査信頼-10\n"
        "   【学習ポイント】SNS炎上への沈黙は企業を廃業に追い込む最悪の対応です。"
    )

# ── 競合価格破壊 ──────────────────────────────
def _comp_differentiate(c: Company) -> str:
    c.cash -= 20
    c.accounting_quality = min(100, c.accounting_quality + 5)
    c.investor_trust = min(100, c.investor_trust + 5)
    return (
        "✅ 差別化戦略を強化し、プレミアム市場への集中を宣言しました。\n"
        "   価格競争ではなく価値競争で、ブランドと利益率を守ることに成功しています。\n"
        "   ▶ 現金-¥20M / 会計品質+5 / 投資家信頼+5\n"
        "   【学習ポイント】価格競争は消耗戦。差別化こそが持続的競争優位の源泉です。"
    )

def _comp_price_follow(c: Company) -> str:
    c.revenue.recognized *= 0.82
    c.quarterly_burn += 10
    c.investor_trust = max(0, c.investor_trust - 10)
    return (
        "❌ 価格追随を選択。利益率が大幅に悪化し、赤字転落の懸念が現実となっています。\n"
        "   投資家から「差別化戦略がない」と厳しい評価を受け始めました。\n"
        "   ▶ 売上-18% / 四半期費用+¥10M / 投資家信頼-10\n"
        "   【学習ポイント】価格競争は収益モデルを破壊します。"
    )

def _comp_ma(c: Company) -> str:
    c.cash -= 40
    c.market_cap_million *= 1.15
    c.investor_trust = min(100, c.investor_trust + 8)
    return (
        "✅ M&A交渉を開始し、補完企業の買収に向けて動き出しました。\n"
        "   シナジー効果への期待から時価総額が上昇しています。\n"
        "   ▶ 現金-¥40M / 時価総額+15% / 投資家信頼+8\n"
        "   【学習ポイント】M&Aはリスクも大きいですが、競合対策の有力な選択肢です。"
    )

# ── 人権DD ────────────────────────────────────
def _hr_full_dd(c: Company) -> str:
    c.cash -= 20
    c.compliance_score = min(100, c.compliance_score + 15)
    c.investor_trust = min(100, c.investor_trust + 8)
    return (
        "✅ 全取引先への人権デューデリジェンスを完了しました。\n"
        "   ESG投資家・外国人投資家からの評価が大幅に向上しています。\n"
        "   ▶ 現金-¥20M / コンプライアンス+15 / 投資家信頼+8\n"
        "   【学習ポイント】人権DDは今後の上場企業に必須の取り組みになります。"
    )

def _hr_partial_dd(c: Company) -> str:
    c.cash -= 8
    c.compliance_score = min(100, c.compliance_score + 5)
    return (
        "✅ 主要取引先50社への人権DDを完了しました。リスクベースの合理的な対応です。\n"
        "   ▶ 現金-¥8M / コンプライアンス+5\n"
        "   【学習ポイント】リスクベースアプローチは費用対効果の高い対応方法です。"
    )

def _hr_minimal(c: Company) -> str:
    c.compliance_score = max(0, c.compliance_score - 5)
    c.flags.total_risk_score += 10
    return (
        "⚡ 形式的な方針策定のみで実態調査を省略しました。\n"
        "   後に問題が発覚した場合、経営者責任を問われるリスクがあります。\n"
        "   ▶ コンプライアンス-5 / リスクスコア+10（法令違反リスク）\n"
        "   【学習ポイント】形式的な対応は「やっていない」と同じ。実態が問われます。"
    )

# ── 半導体不足 ────────────────────────────────
def _semi_stockpile(c: Company) -> str:
    c.cash -= 35
    c.investor_trust = min(100, c.investor_trust + 5)
    return (
        "✅ 代替部品を大量確保し、安定供給体制を維持することに成功しました。\n"
        "   競合他社が納期遅延に苦しむ中、御社は通常通りの事業を継続できています。\n"
        "   ▶ 現金-¥35M / 投資家信頼+5（安定供給確保で差別化）\n"
        "   【学習ポイント】サプライチェーンリスクへの先行投資が競争優位を生みます。"
    )

def _semi_redesign(c: Company) -> str:
    c.cash -= 15
    c.flags.total_risk_score += 8
    return (
        "⚡ 製品仕様を変更して対応しましたが、納期遅延リスクが残っています。\n"
        "   顧客への説明と信頼維持が今後の課題です。\n"
        "   ▶ 現金-¥15M / リスクスコア+8（納期遅延リスク継続）\n"
        "   【学習ポイント】仕様変更は品質管理プロセスへの影響も考慮が必要です。"
    )

def _semi_throttle(c: Company) -> str:
    c.revenue.recognized *= 0.85
    c.investor_trust = max(0, c.investor_trust - 5)
    return (
        "⚡ 受注を抑制した結果、売上が15%減少しました。\n"
        "   安全策ではありましたが、投資家からの成長性評価が下がっています。\n"
        "   ▶ 売上-15% / 投資家信頼-5（成長鈍化の懸念）\n"
        "   【学習ポイント】受注抑制は財務に直接影響。上場審査前は特に注意が必要です。"
    )

# ── インバウンド特需 ──────────────────────────
def _inbound_service(c: Company) -> str:
    c.cash -= 20
    c.revenue.recognized *= 1.15
    c.offense_score = getattr(c, "offense_score", 0) + 1   # 🚀 事業投資
    return (
        "✅ インバウンド向けサービスを展開し、売上が15%増加しました！\n"
        "   円安・訪日ブームを最大限に活用した成長戦略が功を奏しました。\n"
        "   ▶ 現金-¥20M / 売上+15% / 🚀 事業投資+1\n"
        "   【学習ポイント】外部環境のポジティブな変化をいち早く取り込む経営判断が重要です。"
    )

def _inbound_multilang(c: Company) -> str:
    c.cash -= 10
    c.investor_trust = min(100, c.investor_trust + 5)
    c.governance_score = min(100, c.governance_score + 3)
    c.offense_score = getattr(c, "offense_score", 0) + 1   # 🚀 事業投資
    return (
        "✅ 多言語対応を完了し、海外投資家・顧客からの評価が向上しました。\n"
        "   ▶ 現金-¥10M / 投資家信頼+5 / ガバナンス+3 / 🚀 事業投資+1\n"
        "   【学習ポイント】グローバル対応力は上場後の海外IR活動にも直結します。"
    )

def _inbound_pass(c: Company) -> str:
    c.investor_trust = max(0, c.investor_trust - 3)
    return (
        "⚡ インバウンド対応を見送った結果、競合他社にシェアを奪われました。\n"
        "   ▶ 投資家信頼-3（機会損失・成長性への懸念）\n"
        "   【学習ポイント】市場機会への対応スピードは、経営者の判断力の証明です。"
    )

# ── 業界規制強化 ──────────────────────────────
def _reg_early_adopt(c: Company) -> str:
    c.cash -= 25
    c.compliance_score = min(100, c.compliance_score + 20)
    c.investor_trust = min(100, c.investor_trust + 10)
    return (
        "✅ 業界に先駆けて規制対応を完了し、リーダーとしての地位を確立しました。\n"
        "   「コンプライアンス優良企業」として上場審査でも高い評価が期待できます。\n"
        "   ▶ 現金-¥25M / コンプライアンス+20 / 投資家信頼+10\n"
        "   【学習ポイント】規制への先行対応は、ブランド価値と投資家信頼の向上につながります。"
    )

def _reg_industry(c: Company) -> str:
    c.cash -= 10
    c.compliance_score = min(100, c.compliance_score + 8)
    c.governance_score = min(100, c.governance_score + 5)
    return (
        "✅ 業界団体の標準化委員会に参加し、対応コストを最適化しました。\n"
        "   業界内での信頼とネットワークも強化されました。\n"
        "   ▶ 現金-¥10M / コンプライアンス+8 / ガバナンス+5\n"
        "   【学習ポイント】業界団体への参加はコスト分担とネットワーク形成の両面で有益です。"
    )

def _reg_wait(c: Company) -> str:
    c.compliance_score = max(0, c.compliance_score - 10)
    c.flags.total_risk_score += 15
    return (
        "❌ 様子見を選んだ結果、他社との規制対応格差が広がりました。\n"
        "   監督当局からの問い合わせも届き始めており、上場審査への影響が懸念されます。\n"
        "   ▶ コンプライアンス-10 / リスクスコア+15（規制違反リスク）\n"
        "   【学習ポイント】規制対応の遅れは取り返しのつかない問題につながります。"
    )


# ══════════════════════════════════════════════
# 世界イベント定義
# ══════════════════════════════════════════════

WORLD_WAR_OUTBREAK = WorldEvent(
    id="WORLD_WAR_OUTBREAK",
    title="中東での戦争勃発・原油価格高騰",
    category="geopolitics",
    description=(
        "速報：中東において大規模な武力衝突が勃発しました。\n"
        "原油先物価格は一時1バレル150ドルを突破、史上最高値を更新しています。\n"
        "国内でもガソリン・物流コストが急騰し、企業収益を直撃する見通しです。\n"
        "政府は緊急対策会議を召集しましたが、事態収拾には時間がかかる見込みです。\n"
        "御社のサプライチェーンと輸送コストに深刻な影響が出ています。"
    ),
    choices=[
        Choice(label="A. コスト削減緊急対応（輸送業者再交渉・在庫最適化）",
               description="¥10M支出で輸送コストを緊急削減",
               immediate_effect=_war_cost_cut),
        Choice(label="B. 様子見（情勢を注視しながら対応を検討）",
               description="コスト上昇を受け入れながら経過観察",
               immediate_effect=_war_watch),
        Choice(label="C. サプライチェーン多様化（代替ルート・調達先分散）",
               description="¥20M投資で調達先を分散し中長期リスクを低減",
               immediate_effect=_war_diversify),
    ],
)

WORLD_PANDEMIC = WorldEvent(
    id="WORLD_PANDEMIC",
    title="新興感染症パンデミック宣言",
    category="epidemic",
    description=(
        "WHO（世界保健機関）が新興感染症について「パンデミック」を正式宣言しました。\n"
        "国内でも感染者が急増し、政府は都市部への外出自粛要請を発令。\n"
        "企業には在宅勤務の推奨が強く求められており、オフィス閉鎖の判断が迫られています。\n"
        "取引先企業の多くが事業継続計画（BCP）を発動し始めており、\n"
        "経営判断を誤ると上場スケジュールに致命的な影響が出かねません。"
    ),
    choices=[
        Choice(label="A. 全社リモートワーク移行（テレワーク環境整備）",
               description="¥15M支出でITインフラを整備し事業継続",
               immediate_effect=_pandemic_remote),
        Choice(label="B. 事業継続計画（BCP）発動・安定運営維持",
               description="¥25M支出でBCPを本格発動",
               immediate_effect=_pandemic_bcp),
        Choice(label="C. 楽観視して通常営業継続（リスク覚悟）",
               description="コストゼロだが感染拡大・信頼失墜リスク",
               immediate_effect=_pandemic_ignore),
    ],
)

WORLD_EARTHQUAKE = WorldEvent(
    id="WORLD_EARTHQUAKE",
    title="大規模地震・自然災害発生",
    category="epidemic",
    description=(
        "マグニチュード7.4の大規模地震が発生しました。震源地周辺のインフラが壊滅的な被害を受け、\n"
        "御社のオフィスおよびデータセンター設備にも甚大な損傷が確認されています。\n"
        "従業員の安否確認は完了しましたが、事業拠点の復旧に数週間を要する見込みです。\n"
        "取引先からも問い合わせが殺到しており、事業継続能力を問われる状況です。\n"
        "迅速な意思決定が、この危機からの回復速度を左右します。"
    ),
    choices=[
        Choice(label="A. BCP発動・保険請求（迅速復旧）",
               description="¥10M支出で緊急復旧・保険請求を並行実施",
               immediate_effect=_quake_bcp),
        Choice(label="B. 緊急修繕工事（施設の全面復旧優先）",
               description="¥30Mの大規模修繕でオフィスを完全復旧",
               immediate_effect=_quake_repair),
        Choice(label="C. 在宅勤務に切替（オフィス閉鎖・リモート移行）",
               description="¥20M支出でリモート環境整備（急な切替で混乱リスク）",
               immediate_effect=_quake_remote),
    ],
)

WORLD_SUPPLIER_SCANDAL = WorldEvent(
    id="WORLD_SUPPLIER_SCANDAL",
    title="主要仕入先の不祥事・品質偽装発覚",
    category="scandal",
    description=(
        "御社の主要仕入先が製品データの改ざんおよび品質偽装を行っていたことが発覚しました。\n"
        "週刊誌やSNSでの報道が一気に拡散し、仕入先の株価は本日だけで40%急落しています。\n"
        "取引継続の場合、御社も「共犯者」として報道されるリスクが急浮上しています。\n"
        "監査法人からも「取引先の適切性確認」を求める書面が届きました。\n"
        "上場審査では取引先の実態も厳しく審査されます。今すぐ対応が必要です。"
    ),
    choices=[
        Choice(label="A. 取引先変更（即時取引停止・代替調達先へ切替）",
               description="¥20M支出で代替調達先を確保",
               immediate_effect=_supplier_switch),
        Choice(label="B. 共同声明で距離置き（関与否定の公式コメント発表）",
               description="¥5M支出でPR対応（疑念は残る）",
               immediate_effect=_supplier_statement),
        Choice(label="C. 継続取引（静観・問題が過ぎるのを待つ）",
               description="短期コストゼロだが上場審査リスク急増",
               immediate_effect=_supplier_continue),
    ],
)

WORLD_CUSTOMER_CRISIS = WorldEvent(
    id="WORLD_CUSTOMER_CRISIS",
    title="主要顧客の経営危機・倒産懸念",
    category="scandal",
    description=(
        "御社の売上上位3社に入る主要顧客が、多額の有利子負債を抱えて経営危機に陥っています。\n"
        "民間信用調査会社が「倒産確率高」の判定を下し、与信管理の見直しが急務となっています。\n"
        "現時点での未回収売掛金は¥50M以上に上ると試算されており、\n"
        "貸倒損失が発生すれば四半期決算に大きな穴が空く恐れがあります。\n"
        "監査法人は「貸倒引当金の追加計上」を検討するよう求めています。"
    ),
    choices=[
        Choice(label="A. 売掛金即時回収要求（厳格な与信管理）",
               description="財務リスクを最小化。投資家信頼は若干低下",
               immediate_effect=_customer_collect),
        Choice(label="B. 支援して継続取引（リスクを取って関係継続）",
               description="¥30M支出。将来売上確保だが財務リスク大",
               immediate_effect=_customer_support),
        Choice(label="C. 新規顧客開拓に集中（リスク分散戦略）",
               description="¥15M投資で顧客集中リスクを解消",
               immediate_effect=_customer_new),
    ],
)

WORLD_AI_BOOM = WorldEvent(
    id="WORLD_AI_BOOM",
    title="AI・DXブームによる業界特需",
    category="demand",
    one_shot=False,
    description=(
        "生成AIの爆発的普及により、デジタルトランスフォーメーション（DX）需要が急増しています。\n"
        "主要ITコンサルティング会社の案件が軒並みパンクしており、\n"
        "御社にも大手企業からの引き合いが通常の3倍以上届いています。\n"
        "このビジネスチャンスをどう活かすかが、今後の成長軌道を大きく左右します。\n"
        "ただし、AIへの投資にはリソースと費用がかかることも念頭に置く必要があります。"
    ),
    choices=[
        Choice(label="A. AI活用で業務効率化（内部コスト削減から着手）",
               description="¥20M投資で業務プロセスをAI化",
               immediate_effect=_ai_efficiency),
        Choice(label="B. AIプロダクト投資（新規サービス開発・市場投入）",
               description="¥40M大型投資でAI新製品を開発",
               immediate_effect=_ai_product),
        Choice(label="C. 様子見（市場動向を注視・見送り）",
               description="投資ゼロだが競合にシェアを奪われるリスク",
               immediate_effect=_ai_wait),
    ],
)

WORLD_SUBSIDY = WorldEvent(
    id="WORLD_SUBSIDY",
    title="政府デジタル化補助金・助成金公募",
    category="demand",
    description=(
        "経済産業省が中小企業向けDX推進補助金の公募を開始しました。\n"
        "上限¥50M、補助率50%という大型補助金で、申請期限は今月末です。\n"
        "要件を満たす企業には「デジタル認定」の称号も与えられ、\n"
        "上場審査における信頼性向上にも活用できると言われています。\n"
        "ただし申請書類の準備には一定のコストと時間がかかります。"
    ),
    choices=[
        Choice(label="A. 補助金申請（正規手続き・要件充足を確認して申請）",
               description="しっかり準備して申請。採択確率高",
               immediate_effect=_subsidy_apply),
        Choice(label="B. 急いで申請（書類の精度は下げて期限優先）",
               description="申請は間に合うが書類不備リスクあり",
               immediate_effect=_subsidy_rush),
        Choice(label="C. 見送り（申請の手間とコストを省く）",
               description="申請しない。資金獲得機会を逃す",
               immediate_effect=_subsidy_skip),
    ],
)

WORLD_FX_SHOCK = WorldEvent(
    id="WORLD_FX_SHOCK",
    title="急激な円安・為替ショック（1ドル=180円台突入）",
    category="economy",
    description=(
        "日米金利差の拡大を受けて円が急落し、1ドル＝180円台に突入しました。\n"
        "輸入コストが急激に上昇しており、原材料費・クラウドサービス費が激増しています。\n"
        "一方、海外売上を持つ企業にとっては円換算での売上増加という追い風もあります。\n"
        "為替ヘッジを行っていない企業は、来期以降の決算に大きな影響が出る見込みです。\n"
        "監査法人から「為替リスクの開示と管理方針の明確化」を求める指摘が入っています。"
    ),
    choices=[
        Choice(label="A. 為替ヘッジ契約締結（先物・オプションで固定化）",
               description="¥10M費用で為替変動リスクを排除",
               immediate_effect=_fx_hedge),
        Choice(label="B. 輸出強化・海外売上拡大（円安を追い風に）",
               description="円安を活かして海外営業を強化。売上+15%",
               immediate_effect=_fx_export),
        Choice(label="C. 何もしない（様子見・現状維持）",
               description="対策なし。輸入コスト上昇が直撃",
               immediate_effect=_fx_nothing),
    ],
)

WORLD_LABOR_SHORTAGE = WorldEvent(
    id="WORLD_LABOR_SHORTAGE",
    title="深刻な人材不足・エンジニア争奪戦の激化",
    category="social",
    description=(
        "テック系人材の争奪戦が激化し、上位エンジニアの平均年収が1,500万円を超えました。\n"
        "御社のエンジニア3名が競合大手からのオファーを受けており、退職の意向を示しています。\n"
        "このまま人材流出が続けば、IPO準備に必要な内部統制整備や\n"
        "システム開発が大幅に遅延するリスクがあります。\n"
        "採用市場では人材確保コストも急騰しており、即断即決が求められています。"
    ),
    choices=[
        Choice(label="A. 大幅賃上げ（エンジニア全員に30%昇給）",
               description="¥30M支出・四半期費用+¥20M。人材確保最優先",
               immediate_effect=_labor_raise),
        Choice(label="B. 外国人採用・グローバル化（ビザ支援付き採用）",
               description="¥25M投資で海外エンジニアを採用",
               immediate_effect=_labor_global),
        Choice(label="C. 現状維持（様子見・コスト増加を避ける）",
               description="コストゼロだが人材流出が続く",
               immediate_effect=_labor_nothing),
    ],
)

WORLD_SNS_SCANDAL = WorldEvent(
    id="WORLD_SNS_SCANDAL",
    title="SNS炎上・ブランド毀損（バイラル拡散）",
    category="scandal",
    probability=0.20,
    description=(
        "御社の元従業員によるSNS投稿が急拡散し、24時間で100万リツイートを超えました。\n"
        "「パワハラ・サービス残業・コンプライアンス違反」を告発する内容で、\n"
        "大手メディアも後追い報道を開始。株価相当の企業価値が毀損する恐れがあります。\n"
        "投資家・監査法人・主幹事証券会社から相次いで説明要求が届いており、\n"
        "上場審査への影響は計り知れません。今すぐ経営トップとして対応が必要です。"
    ),
    choices=[
        Choice(label="A. 謝罪・改善策を公式発表（真摯な対応）",
               description="¥15M費用でPR対応・改善策実施",
               immediate_effect=_sns_apologize),
        Choice(label="B. 法的対応（名誉毀損で元従業員を提訴）",
               description="¥20M費用の法的措置（長期化リスクあり）",
               immediate_effect=_sns_legal),
        Choice(label="C. 無視・ノーコメント（沈黙を守る）",
               description="対応コストゼロだが炎上長期化で壊滅的打撃",
               immediate_effect=_sns_ignore),
    ],
)

WORLD_COMPETITION_PRICE_WAR = WorldEvent(
    id="WORLD_COMPETITION_PRICE_WAR",
    title="競合他社による価格破壊・シェア奪取",
    category="economy",
    description=(
        "国内最大手の競合が、御社のコアサービスに対して50%値下げを敢行しました。\n"
        "顧客への一斉営業メールが流れ、御社の既存顧客からも「価格見直し」の相談が増えています。\n"
        "このまま何もしなければ、来期の売上が20〜30%減少するとの試算が出ています。\n"
        "一方で価格追随は利益率を大幅に削り、上場審査での財務評価が下がります。\n"
        "社長として市場競争にどう対応するか、判断の時です。"
    ),
    choices=[
        Choice(label="A. 差別化戦略強化（品質・サービスで上位市場に集中）",
               description="¥20M投資でプレミアム化。利益率と品質を守る",
               immediate_effect=_comp_differentiate),
        Choice(label="B. 価格追随（競合と同レベルに値下げ）",
               description="売上-10%で顧客流出を防ぐ（利益率低下）",
               immediate_effect=_comp_price_follow),
        Choice(label="C. M&A検討（競合または補完企業の買収）",
               description="¥40M投資でM&A交渉。時価総額+15%が見込める",
               immediate_effect=_comp_ma),
    ],
)

WORLD_HUMAN_RIGHTS = WorldEvent(
    id="WORLD_HUMAN_RIGHTS",
    title="人権デューデリジェンス法の施行",
    category="social",
    description=(
        "欧州の人権デューデリジェンス規制を参考にした国内法が施行されました。\n"
        "上場企業・上場準備企業を含む一定規模以上の企業に対し、\n"
        "サプライチェーン全体における人権リスクの調査・開示が義務付けられています。\n"
        "国際機関からのモニタリングも始まっており、対応の遅れは\n"
        "ESG投資家や外国人投資家からの信頼喪失に直結する重大な問題です。"
    ),
    choices=[
        Choice(label="A. 全取引先への人権DD実施（網羅的調査）",
               description="¥20M費用で全取引先を調査",
               immediate_effect=_hr_full_dd),
        Choice(label="B. 重要取引先のみ対応（リスクベースアプローチ）",
               description="¥8M費用で主要50社のみ調査",
               immediate_effect=_hr_partial_dd),
        Choice(label="C. 最低限の対応（形式的な方針策定のみ）",
               description="コスト最小化だが実態調査なし",
               immediate_effect=_hr_minimal),
    ],
)

WORLD_SEMICONDUCTOR_SHORTAGE = WorldEvent(
    id="WORLD_SEMICONDUCTOR_SHORTAGE",
    title="半導体・電子部品の世界的供給不足",
    category="economy",
    description=(
        "台湾・韓国の主要半導体工場が自然災害と地政学リスクにより生産停止に追い込まれました。\n"
        "世界的な半導体不足が発生し、リードタイムが従来の3倍以上に延長されています。\n"
        "御社の製品・サービスに必要な電子部品の調達が困難になっており、\n"
        "このまま対応しなければ納期遅延・契約違反が発生する可能性が高まっています。\n"
        "競合他社は既に代替調達に動き始めており、迅速な意思決定が競争力を左右します。"
    ),
    choices=[
        Choice(label="A. 代替品調達・在庫積み増し（先行確保戦略）",
               description="¥35M投資で代替部品を大量確保",
               immediate_effect=_semi_stockpile),
        Choice(label="B. 製品仕様変更（半導体不要の設計に切替）",
               description="¥15M費用で仕様変更（納期遅延リスク残存）",
               immediate_effect=_semi_redesign),
        Choice(label="C. 受注抑制（新規受注を一時停止）",
               description="安全策だが売上-15%・成長性低下",
               immediate_effect=_semi_throttle),
    ],
)

WORLD_INBOUND_BOOM = WorldEvent(
    id="WORLD_INBOUND_BOOM",
    title="訪日外国人急増・インバウンド特需",
    category="demand",
    one_shot=True,
    description=(
        "円安を背景に訪日外国人が年間5,000万人を突破し、観光・消費関連産業が空前の好景気を迎えています。\n"
        "政府も「インバウンド2倍計画」を発表し、関連企業への優遇措置を拡充しました。\n"
        "御社の事業領域でも海外からの需要が急増しており、多言語対応・海外マーケティングへの\n"
        "投資がそのまま売上増加につながる絶好のタイミングが到来しています。\n"
        "競合他社はすでにインバウンド向け専用チームを立ち上げています。"
    ),
    choices=[
        Choice(label="A. インバウンド向けサービス展開（専用プランを開発）",
               description="¥20M投資で海外向けサービスを展開。売上+15%",
               immediate_effect=_inbound_service),
        Choice(label="B. 多言語対応（英語・中国語でのサービス提供）",
               description="¥10M費用で多言語化・グローバル対応力向上",
               immediate_effect=_inbound_multilang),
        Choice(label="C. 対応見送り（国内市場に集中）",
               description="インバウンド需要を取り込めず機会損失",
               immediate_effect=_inbound_pass),
    ],
)

# ── 円安による特需 ────────────────────────────
def _yen_export_boost(c: Company) -> str:
    c.revenue.recognized *= 1.12
    c.investor_trust = min(100, c.investor_trust + 6)
    c.offense_score = getattr(c, "offense_score", 0) + 1   # 🚀 事業投資
    return (
        "✅ 円安を追い風に輸出・海外向け売上が急拡大しました。\n"
        "   売上+12% ／ 投資家信頼+6（外需取込みを高評価）／ 🚀 事業投資+1\n"
        "   ▶ 上場後の海外展開ストーリーとして投資家に訴求できます。\n"
        "   【学習ポイント】為替変動を経営リスクと捉えつつ、好機として活用する姿勢が評価されます。"
    )

def _yen_hedge_strategy(c: Company) -> str:
    c.cash -= 8
    c.compliance_score = min(100, c.compliance_score + 5)
    c.investor_trust = min(100, c.investor_trust + 4)
    return (
        "✅ 為替ヘッジと国内外バランス戦略を採用。リスク管理を強化しました。\n"
        "   ¥8M費用 ／ コンプラ+5 ／ 投資家信頼+4\n"
        "   ▶ 為替リスクへの適切な対応は財務管理能力として上場審査でも評価されます。\n"
        "   【学習ポイント】為替ヘッジの検討・開示は上場企業として必須の財務管理です。"
    )

def _yen_pass(c: Company) -> str:
    c.investor_trust = max(0, c.investor_trust - 4)
    return (
        "⚡ 円安特需への対応を見送りました。競合他社との差が開きつつあります。\n"
        "   投資家信頼-4（機会損失への懸念）\n"
        "   ▶ 外部環境変化への対応遅れは経営機動力への疑問につながります。"
    )

WORLD_YEN_WEAK_BOOM = WorldEvent(
    id="WORLD_YEN_WEAK_BOOM",
    title="円安加速・輸出産業・外需ビジネスに特需",
    category="demand",
    one_shot=True,
    description=(
        "急速な円安が進行し、対ドルで150円を突破しました。\n"
        "輸出関連企業・インバウンド消費・海外向けサービス企業を中心に\n"
        "売上・利益の急拡大が相次いでいます。\n"
        "一方で輸入コストの上昇という逆風もあり、\n"
        "御社としてこの為替環境をどう経営に活かすか判断が求められています。\n"
        "主幹事証券は「為替環境を成長ストーリーに組み込めれば上場時の評価が高まる」と助言しています。"
    ),
    choices=[
        Choice(label="A. 外需・輸出戦略を強化（海外売上比率を引き上げ）",
               description="売上+12%・投資家信頼+6（海外成長ストーリーを確立）",
               immediate_effect=_yen_export_boost),
        Choice(label="B. 為替ヘッジ戦略を導入（リスク管理重視）",
               description="¥8M費用・コンプラ+5・投資家信頼+4（財務管理能力をアピール）",
               immediate_effect=_yen_hedge_strategy),
        Choice(label="C. 対応見送り（国内中心戦略を継続）",
               description="機会損失・投資家信頼-4",
               immediate_effect=_yen_pass),
    ],
)


# ── DX・デジタル需要急増 ───────────────────────
def _dx_accelerate(c: Company) -> str:
    c.cash -= 15
    c.revenue.recognized *= 1.18
    c.employee_morale = min(100, c.employee_morale + 8)
    return (
        "✅ DX推進需要を先取りし、デジタルサービス拡充で売上が急拡大しました。\n"
        "   ¥15M投資 ／ 売上+18% ／ 士気+8（先端企業としての評価）\n"
        "   ▶ 成長市場への積極投資は上場審査の成長性評価でプラスになります。\n"
        "   【学習ポイント】DX化の波に乗った成長ストーリーは機関投資家が最も注目するテーマです。"
    )

def _dx_partner(c: Company) -> str:
    c.cash -= 8
    c.investor_trust = min(100, c.investor_trust + 7)
    c.governance_score = min(100, c.governance_score + 4)
    return (
        "✅ 大手SIer・テック企業とのアライアンスでDX需要を取り込みました。\n"
        "   ¥8M費用 ／ 投資家信頼+7 ／ ガバナンス+4（アライアンス戦略の安定性を評価）\n"
        "   ▶ 上場後の成長戦略としてパートナーシップ活用を訴求できます。\n"
        "   【学習ポイント】パートナーネットワークの構築は持続的成長の証拠として評価されます。"
    )

def _dx_wait(c: Company) -> str:
    c.investor_trust = max(0, c.investor_trust - 5)
    c.employee_morale = max(0, c.employee_morale - 6)
    return (
        "⚡ DX需要への対応を見送り、競合他社にリードを許しました。\n"
        "   投資家信頼-5 ／ 士気-6（将来への不安感）\n"
        "   ▶ 成長市場への消極的姿勢は上場審査の成長性評価に影響します。"
    )

WORLD_DX_DEMAND = WorldEvent(
    id="WORLD_DX_DEMAND",
    title="企業DX加速・デジタルサービス需要急増",
    category="demand",
    one_shot=True,
    description=(
        "政府の「デジタル田園都市国家構想」が本格始動し、\n"
        "企業のDX（デジタルトランスフォーメーション）投資が急拡大しています。\n"
        "中堅・中小企業のクラウド移行・業務自動化需要が爆発的に増加しており、\n"
        "デジタルサービスを提供する企業への引き合いが急増しています。\n"
        "競合他社は既に大型契約を獲得し始めており、スピードが競争優位を左右します。"
    ),
    choices=[
        Choice(label="A. DX専門チームを立ち上げ積極展開（¥15M投資）",
               description="売上+18%・士気+8（市場をリード）",
               immediate_effect=_dx_accelerate),
        Choice(label="B. 大手SIerとアライアンス締結（¥8M費用）",
               description="投資家信頼+7・ガバナンス+4（安定的な成長）",
               immediate_effect=_dx_partner),
        Choice(label="C. 様子見（既存事業に集中）",
               description="機会損失・投資家信頼-5・士気-6",
               immediate_effect=_dx_wait),
    ],
)


WORLD_REGULATORY_CHANGE = WorldEvent(
    id="WORLD_REGULATORY_CHANGE",
    title="業界規制の大幅強化・新法施行",
    category="social",
    description=(
        "金融庁・経産省が共同で業界規制の大幅強化を発表し、新法が来期より施行されます。\n"
        "上場準備企業には特に厳格な適用が予定されており、コンプライアンス体制の\n"
        "抜本的見直しと当局への報告義務が新たに課せられます。\n"
        "業界団体では「対応コストが増大する」と反発する声も上がっていますが、\n"
        "早期対応企業は審査で有利な評価を受けるという情報も入ってきています。"
    ),
    choices=[
        Choice(label="A. 早期対応・業界をリード（完全準拠を即時表明）",
               description="¥25M投資で全要件に先行対応",
               immediate_effect=_reg_early_adopt),
        Choice(label="B. 業界団体で対応（共同ロビー活動・標準化参加）",
               description="¥10M費用で業界団体の対応委員会に参加",
               immediate_effect=_reg_industry),
        Choice(label="C. 様子見（他社の対応を見てから判断）",
               description="対応コストゼロだが規制違反リスク急増",
               immediate_effect=_reg_wait),
    ],
)


# ── 社内不正（経理担当者の横領）────────────────
def _fraud_investigate(c: Company) -> str:
    c.cash -= 20
    c.internal_control_score = min(100, c.internal_control_score + 15)
    c.flags.no_job_separation = False
    c.flags.embezzlement_risk_level = max(0, c.flags.embezzlement_risk_level - 2)
    return (
        "✅ 内部調査で全容を解明し、当該担当者を懲戒処分にしました。\n"
        "   出納・記帳の職務分掌を徹底し、内部統制を大幅強化。監査法人からも評価されました。\n"
        "   ▶ 現金-¥20M / 内部統制+15 / 職務分掌が改善 / 横領リスク低下\n"
        "   【学習ポイント】不正発覚時の初動対応と透明性が、上場審査の重要評価ポイントです。"
    )

def _fraud_external_audit(c: Company) -> str:
    c.cash -= 30
    c.accounting_quality = min(100, c.accounting_quality + 10)
    c.auditor_trust = min(100, c.auditor_trust + 8)
    c.flags.no_job_separation = False
    return (
        "✅ 外部専門家による独立調査で不正の全体像を解明し、監査法人に速やかに報告しました。\n"
        "   透明性ある対応が高く評価され、監査法人・投資家からの信頼が向上しました。\n"
        "   ▶ 現金-¥30M / 会計品質+10 / 監査信頼+8\n"
        "   【学習ポイント】自発的な外部調査依頼は、上場審査でのガバナンス成熟度の証明になります。"
    )

def _fraud_cover(c: Company) -> str:
    c.flags.embezzlement_risk_level += 3
    c.flags.total_risk_score += 20
    c.investor_trust = max(0, c.investor_trust - 10)
    return (
        "❌ 揉み消しを図りましたが、後日監査法人の調査で発覚しました。\n"
        "   「経営者の関与」が疑われ、上場審査で致命的な問題として浮上しています。\n"
        "   ▶ リスクスコア+20 / 横領リスクLv+3 / 投資家信頼-10\n"
        "   【学習ポイント】不正の隠蔽は最悪の対応。速やかな開示・是正が経営者の義務です。"
    )

WORLD_INTERNAL_FRAUD = WorldEvent(
    id="WORLD_INTERNAL_FRAUD",
    title="社内不正発覚！経理担当者による横領",
    category="scandal",
    probability=0.25,
    description=(
        "経理部門の担当者が過去1年間にわたり架空発注を繰り返し、会社資金を横領していたことが\n"
        "内部告発により発覚しました。被害総額は¥30M超と試算されています。\n"
        "監査法人からは「内部統制の重大な欠陥」として指摘が入り、\n"
        "このままでは上場審査での決算の信頼性が根本から問われます。\n"
        "出納・記帳の職務分掌が分離されておらず、監視体制の不備が根本原因です。\n"
        "社長として、どう対処しますか？"
    ),
    choices=[
        Choice(label="A. 内部調査チームで全容解明・担当者を懲戒処分（¥20M）",
               description="速やかな内部調査で職務分掌も同時に整備",
               immediate_effect=_fraud_investigate),
        Choice(label="B. 外部専門家（弁護士・公認会計士）による独立調査（¥30M）",
               description="費用は高いが透明性最高。監査法人の信頼回復に最も有効",
               immediate_effect=_fraud_external_audit),
        Choice(label="C. 社内で揉み消し・表沙汰にしない",
               description="コストゼロだが後から発覚すれば経営者責任に",
               immediate_effect=_fraud_cover),
    ],
)

# ── パワハラ問題 ──────────────────────────────
def _harassment_reform(c: Company) -> str:
    c.cash -= 15
    c.compliance_score = min(100, c.compliance_score + 12)
    c.employee_morale = min(100, c.employee_morale + 8)
    c.flags.no_compliance_system = False
    return (
        "✅ 当該役員を厳正処分し、ハラスメント防止規程と社内相談窓口を整備しました。\n"
        "   従業員の安心感が高まりモラール回復。コンプライアンス体制が大幅に強化されました。\n"
        "   ▶ 現金-¥15M / コンプライアンス+12 / 従業員士気+8\n"
        "   【学習ポイント】ハラスメント防止体制は上場審査のコンプライアンス評価に直結します。"
    )

def _harassment_third_party(c: Company) -> str:
    c.cash -= 25
    c.compliance_score = min(100, c.compliance_score + 8)
    c.governance_score = min(100, c.governance_score + 5)
    return (
        "✅ 外部の第三者委員会による独立調査を実施し、透明性ある結論を公表しました。\n"
        "   調査コストは大きいですが、投資家・監査法人から「ガバナンスの成熟」と高評価を得ました。\n"
        "   ▶ 現金-¥25M / コンプライアンス+8 / ガバナンス+5\n"
        "   【学習ポイント】第三者委員会の活用は、ガバナンス成熟度を示す最も有効な手段です。"
    )

def _harassment_deny(c: Company) -> str:
    c.flags.total_risk_score += 18
    c.employee_morale = max(0, c.employee_morale - 20)
    c.investor_trust = max(0, c.investor_trust - 12)
    return (
        "❌ 会社として否認・沈黙を続けた結果、SNSで告発が拡散し炎上が長期化しました。\n"
        "   従業員の大量退職リスクが高まり、主幹事証券会社から上場延期の示唆を受けています。\n"
        "   ▶ リスクスコア+18 / 従業員士気-20 / 投資家信頼-12\n"
        "   【学習ポイント】ハラスメントの否認・隠蔽は最悪の対応。上場審査に致命傷となります。"
    )

WORLD_HARASSMENT = WorldEvent(
    id="WORLD_HARASSMENT",
    title="パワハラ告発！役員によるハラスメント問題発覚",
    category="scandal",
    probability=0.25,
    description=(
        "管理職による継続的なパワーハラスメントの告発状が複数の従業員から提出され、\n"
        "弁護士経由で労働基準監督署にも申告が行われました。\n"
        "SNSでは「〇〇社 パワハラ」がトレンド入りし始めており、\n"
        "投資家・監査法人・主幹事証券会社から「事実関係の早期説明」を求める連絡が届いています。\n"
        "コンプライアンス体制が未整備のままでは、上場審査で重大な指摘を受けます。\n"
        "社長として、どう対処しますか？"
    ),
    choices=[
        Choice(label="A. 当該役員を処分・ハラスメント防止規程を整備（¥15M）",
               description="迅速な処分とコンプライアンス体制の整備",
               immediate_effect=_harassment_reform),
        Choice(label="B. 外部第三者委員会による独立調査（¥25M）",
               description="最も透明性が高く、ガバナンス評価が向上",
               immediate_effect=_harassment_third_party),
        Choice(label="C. 「事実無根」として否認・法的対応で沈黙",
               description="コスト最小だが炎上長期化リスクが高い",
               immediate_effect=_harassment_deny),
    ],
)

# ── 創業メンバー・共同創業者の突然離脱 ───────────
def _cofounder_succession(c: Company) -> str:
    c.cash -= 20
    c.governance_score = min(100, c.governance_score + 8)
    c.employee_morale = max(0, c.employee_morale - 5)
    return (
        "✅ 速やかに後継者を選任し、株式譲渡手続き・役員変更登記を完了しました。\n"
        "   組織の安定を保ちながら引継ぎを完遂。投資家への説明も丁寧に行いました。\n"
        "   ▶ 現金-¥20M / ガバナンス+8 / 従業員士気-5（一時的）\n"
        "   【学習ポイント】経営者の突然の交代は、後継者計画（サクセッション）の重要性を示します。"
    )

def _cofounder_buyback(c: Company) -> str:
    c.cash -= 50
    c.cap_table.founder_ratio()  # just reference
    c.investor_trust = min(100, c.investor_trust + 5)
    return (
        "✅ 離脱する創業メンバーの株式を適正価格で自己株取得しました。\n"
        "   キャップテーブルが整理され、上場審査での株主構成評価がシンプルになりました。\n"
        "   ▶ 現金-¥50M / 投資家信頼+5（株主構成が整理）\n"
        "   【学習ポイント】上場前の不明確な株式保有は審査で問題になります。早期整理が重要です。"
    )

def _cofounder_conflict(c: Company) -> str:
    c.flags.total_risk_score += 12
    c.investor_trust = max(0, c.investor_trust - 15)
    c.employee_morale = max(0, c.employee_morale - 15)
    return (
        "❌ 株式や待遇を巡る対立が法的紛争に発展し、社内に動揺が広がりました。\n"
        "   主幹事証券会社から「経営の安定性への懸念」が示され、IPOスケジュールが危うくなっています。\n"
        "   ▶ リスクスコア+12 / 投資家信頼-15 / 従業員士気-15\n"
        "   【学習ポイント】創業者間の株式・役割の合意は、IPO準備の最初に済ませておくべきです。"
    )

WORLD_COFOUNDER_EXIT = WorldEvent(
    id="WORLD_COFOUNDER_EXIT",
    title="創業メンバーの突然退職・株式問題が浮上",
    category="governance",
    probability=0.20,
    description=(
        "共同創業者であるCTOが「経営方針の相違」を理由に突然退職を申し出ました。\n"
        "退職時の株式の扱い・買取価格を巡って交渉がまとまらず、\n"
        "このまま対立が長引けば、主幹事証券会社から「経営の安定性」に懸念を示される状況です。\n"
        "また、キャップテーブルに「未整理の株主」が存在すると上場審査で重大な問題になります。\n"
        "社長として、どう対処しますか？"
    ),
    choices=[
        Choice(label="A. 後継体制を整えて円満退職・役員変更手続き（¥20M）",
               description="組織安定を優先し、後継者を速やかに選任",
               immediate_effect=_cofounder_succession),
        Choice(label="B. 株式を適正価格で自己株取得し、すっきり整理（¥50M）",
               description="費用は大きいがキャップテーブルが整理される",
               immediate_effect=_cofounder_buyback),
        Choice(label="C. 交渉決裂・法的紛争に発展",
               description="対立が深まりIPOスケジュールが危機に",
               immediate_effect=_cofounder_conflict),
    ],
)


# ══════════════════════════════════════════════
# 新規：致命的ダメージイベント
# ══════════════════════════════════════════════

# ── 汎用AI・SaaS陳腐化危機 ────────────────────
def _ai_dis_pivot(c: Company) -> str:
    c.cash -= 150
    c.revenue.recognized *= 0.65
    c.investor_trust = min(100, c.investor_trust + 15)
    c.market_cap_million *= 0.80
    c.revenue.growth_rate = min(c.revenue.growth_rate + 0.10, 0.35)
    return (
        "⚡ 大規模AIネイティブへのピボットを決断。一時的に売上が35%落ちましたが、\n"
        "   投資家から「正しい判断」と評価され、新たな成長軌道に入りました。\n"
        "   ▶ 現金-¥150M / 売上-35%（一時的） / 投資家信頼+15 / 以降の成長率+10%\n"
        "   【学習ポイント】テクノロジーの非連続変化には、痛みを伴う決断が必要です。"
    )

def _ai_dis_niche(c: Company) -> str:
    c.cash -= 60
    c.revenue.recognized *= 0.80
    c.investor_trust = max(0, c.investor_trust - 15)
    return (
        "⚡ ニッチ市場特化への転換を実施。コアユーザーは残りましたが、\n"
        "   成長鈍化を懸念した主要VCが追加投資を見送る意向を示しています。\n"
        "   ▶ 現金-¥60M / 売上-20% / 投資家信頼-15\n"
        "   【学習ポイント】ニッチ戦略は生存手段ですが、上場審査での成長性評価が下がります。"
    )

def _ai_dis_nothing(c: Company) -> str:
    c.revenue.recognized *= 0.45
    c.investor_trust = max(0, c.investor_trust - 40)
    c.market_cap_million *= 0.35
    c.flags.total_risk_score += 30
    c.employee_morale = max(0, c.employee_morale - 25)
    return (
        "❌ 現状維持を選んだ結果、主要顧客がAIサービスに一斉移行。売上が半減しました。\n"
        "   複数のVCが「事業継続性への重大な疑義」を表明し、上場計画の見直しを求めています。\n"
        "   主幹事証券会社も引受辞退を検討中です。\n"
        "   ▶ 売上-55% / 投資家信頼-40 / 時価総額-65% / リスクスコア+30 / 従業員士気-25"
    )

WORLD_AI_DISRUPTION = WorldEvent(
    id="WORLD_AI_DISRUPTION",
    title="🤖 業界激震！次世代汎用AIがSaaS市場を破壊",
    category="demand",
    target_biz=["SaaS", "FinTech"],
    min_n_period=-2,
    probability=0.40,
    description=(
        "【緊急速報】大手テック企業が汎用AIを無償公開。御社のSaaSプロダクトの主要機能が\n"
        "ほぼ無料で代替されるようになりました。既存顧客から解約通知が殺到しており、\n"
        "先週だけで30社以上がサービス解約を申し出ています。\n"
        "投資家・主幹事証券会社は「事業モデルの抜本的見直し」を求めており、\n"
        "このまま対応しなければ上場計画が消滅する可能性があります。\n\n"
        "社長、これはサバイバルの問題です。どう判断しますか？"
    ),
    choices=[
        Choice(
            label="A. 全社AIネイティブ化ピボット（¥150M・売上一時急落覚悟）",
            description="痛みを伴う大変革。しかし生き残りと成長の可能性を確保する",
            immediate_effect=_ai_dis_pivot,
        ),
        Choice(
            label="B. ニッチ市場への特化（¥60M・差別化で生存）",
            description="中間策。成長は鈍化するが事業は存続",
            immediate_effect=_ai_dis_niche,
        ),
        Choice(
            label="C. 現状維持（様子見・追加投資なし）",
            description="最もリスクが高い。市場から消える可能性大",
            immediate_effect=_ai_dis_nothing,
        ),
    ],
)


# ── 主要株主による経営陣退陣要求 ──────────────────
def _revolt_accept(c: Company) -> str:
    c.cash -= 80
    c.governance_score = min(100, c.governance_score + 25)
    c.investor_trust = min(100, c.investor_trust + 20)
    c.employee_morale = min(100, c.employee_morale + 10)
    return (
        "✅ 経営体制の刷新を受け入れ、社外CFO・COOを緊急招聘しました。\n"
        "   大きなコストでしたが、投資家・監査法人から「ガバナンスの成熟」と高く評価されました。\n"
        "   ▶ 現金-¥80M / ガバナンス+25 / 投資家信頼+20 / 従業員士気+10\n"
        "   【学習ポイント】経営危機時の決断力が、真のリーダーを証明します。"
    )

def _revolt_partial(c: Company) -> str:
    c.cash -= 40
    c.governance_score = min(100, c.governance_score + 10)
    c.investor_trust = max(0, c.investor_trust - 5)
    c.flags.total_risk_score += 10
    return (
        "⚡ 部分的な体制変更を行いましたが、VCは「不十分」と評価しています。\n"
        "   追加要求が来ることは確実で、対立が長期化する懸念があります。\n"
        "   ▶ 現金-¥40M / ガバナンス+10 / 投資家信頼-5 / リスクスコア+10"
    )

def _revolt_refuse(c: Company) -> str:
    c.investor_trust = max(0, c.investor_trust - 45)
    c.flags.total_risk_score += 35
    c.auditor_trust = max(0, c.auditor_trust - 15)
    c.employee_morale = max(0, c.employee_morale - 20)
    return (
        "❌ 退陣要求を全面拒否。VCが保有株を大量売却し始め、時価総額が急落しています。\n"
        "   監査法人が「継続企業の前提に疑義あり」注記を検討。上場計画が実質崩壊しています。\n"
        "   ▶ 投資家信頼-45 / リスクスコア+35 / 監査信頼-15 / 従業員士気-20"
    )

WORLD_INVESTOR_REVOLT = WorldEvent(
    id="WORLD_INVESTOR_REVOLT",
    title="⚠ 主要VCが経営陣退陣要求！緊急取締役会召集",
    category="scandal",
    min_n_period=-1,
    probability=0.25,
    description=(
        "【緊急事態】御社の筆頭VCが「経営陣の意思決定能力に重大な疑問がある」として\n"
        "臨時取締役会を召集。社長を含む経営陣の退陣を正式に要求してきました。\n"
        "業績未達・内部統制の不備・コンプライアンス問題が積み重なった結果です。\n"
        "他のVCも連名で「上場前の経営体制刷新」を求める書面を提出しています。\n\n"
        "この要求を受け入れるか、戦うか。会社の運命がかかった決断です。"
    ),
    choices=[
        Choice(
            label="A. 経営体制刷新を受け入れ・社外プロ経営陣を招聘（¥80M）",
            description="自らの権限を一部委譲。組織の信頼と安定を回復する",
            immediate_effect=_revolt_accept,
        ),
        Choice(
            label="B. 部分的に受け入れ・COO就任で妥協（¥40M）",
            description="最小限の体制変更で乗り切ろうとする",
            immediate_effect=_revolt_partial,
        ),
        Choice(
            label="C. 全面拒否・法廷闘争も辞さない構え",
            description="対立を深める最悪の選択。株主の信頼が完全に崩壊する",
            immediate_effect=_revolt_refuse,
        ),
    ],
)


# ── 主要幹部・CFOの突然逮捕 ───────────────────────
def _arrest_transparent(c: Company) -> str:
    c.cash -= 100
    c.flags.total_risk_score += 20
    c.auditor_trust = max(0, c.auditor_trust - 10)
    c.investor_trust = max(0, c.investor_trust - 20)
    c.governance_score = min(100, c.governance_score + 15)
    return (
        "⚡ 事実関係を全て開示し、第三者委員会による調査を即時開始しました。\n"
        "   短期的ダメージは大きいですが、透明性ある対応が長期的信頼回復の唯一の道です。\n"
        "   ▶ 現金-¥100M / リスクスコア+20 / 投資家信頼-20 / ガバナンス+15（透明性評価）"
    )

def _arrest_limit_damage(c: Company) -> str:
    c.cash -= 50
    c.flags.total_risk_score += 30
    c.investor_trust = max(0, c.investor_trust - 30)
    return (
        "❌ 情報開示を最小限に抑えようとしましたが、リーク情報がメディアに流れました。\n"
        "   「隠蔽疑惑」が広まり、事態が悪化しています。\n"
        "   ▶ 現金-¥50M / リスクスコア+30 / 投資家信頼-30"
    )

def _arrest_deny(c: Company) -> str:
    c.flags.total_risk_score += 50
    c.investor_trust = max(0, c.investor_trust - 50)
    c.auditor_trust = max(0, c.auditor_trust - 30)
    c.flags.ipo_force_delay = True
    return (
        "❌ 事実を否定し続けた結果、検察が追加捜査に乗り出しました。\n"
        "   主幹事証券会社が引受を即時停止。上場計画の全面撤回を余儀なくされています。\n"
        "   ▶ リスクスコア+50 / 投資家信頼-50 / 監査信頼-30 / 上場延期フラグ発動"
    )

WORLD_EXEC_ARREST = WorldEvent(
    id="WORLD_EXEC_ARREST",
    title="🚨 衝撃！CFO・役員が証券取引法違反で逮捕",
    category="scandal",
    min_n_period=-1,
    probability=0.15,
    description=(
        "【速報】御社のCFO（最高財務責任者）が証券取引法違反（インサイダー取引）の疑いで\n"
        "東京地検特捜部に逮捕されました。各メディアが一斉に報道しており、\n"
        "「上場準備企業のガバナンス崩壊」として大きく取り上げられています。\n"
        "投資家・監査法人・主幹事証券会社から、事実関係の即時説明を求める\n"
        "書面が続々と届いています。初動対応がその後の全てを決めます。"
    ),
    choices=[
        Choice(
            label="A. 全事実を開示・第三者委員会設置（¥100M）",
            description="透明性最優先。短期ダメージは大きいが信頼回復の唯一の道",
            immediate_effect=_arrest_transparent,
        ),
        Choice(
            label="B. 情報開示を最小限に・個人責任として切り離す（¥50M）",
            description="ダメージコントロールを試みるが隠蔽疑惑リスクあり",
            immediate_effect=_arrest_limit_damage,
        ),
        Choice(
            label="C. 「会社は無関係」として否定・ノーコメント",
            description="最悪の対応。検察・メディアがさらに掘り下げる",
            immediate_effect=_arrest_deny,
        ),
    ],
)


# ── 大量の訴訟・集団訴訟 ──────────────────────────
def _lawsuit_settle(c: Company) -> str:
    c.cash -= 200
    c.flags.total_risk_score += 10
    c.investor_trust = max(0, c.investor_trust - 5)
    c.compliance_score = min(100, c.compliance_score + 10)
    return (
        "⚡ 和解を選択。¥200Mの和解金は大きな痛手ですが、長期訴訟リスクを回避しました。\n"
        "   和解条件の開示により、コンプライアンス体制の改善にも取り組むことになりました。\n"
        "   ▶ 現金-¥200M / リスクスコア+10 / コンプライアンス+10"
    )

def _lawsuit_fight(c: Company) -> str:
    c.cash -= 80
    c.flags.total_risk_score += 25
    c.investor_trust = max(0, c.investor_trust - 20)
    return (
        "⚡ 全面対決を選択。弁護士費用が膨らむ一方、訴訟の長期化が確実となっています。\n"
        "   上場審査において「係争中の重大案件あり」として必ず問題になります。\n"
        "   ▶ 現金-¥80M / リスクスコア+25 / 投資家信頼-20"
    )

def _lawsuit_delay(c: Company) -> str:
    c.flags.total_risk_score += 40
    c.investor_trust = max(0, c.investor_trust - 35)
    c.auditor_trust = max(0, c.auditor_trust - 20)
    return (
        "❌ 対応を引き延ばしたことで原告団が拡大し、被害額が10倍以上に膨らみました。\n"
        "   監査法人が「訴訟結果次第では大幅な損失処理が必要」と警告。上場審査は絶望的です。\n"
        "   ▶ リスクスコア+40 / 投資家信頼-35 / 監査信頼-20"
    )

WORLD_MASS_LAWSUIT = WorldEvent(
    id="WORLD_MASS_LAWSUIT",
    title="⚖ 元従業員・取引先による集団訴訟！請求額¥500M",
    category="scandal",
    min_n_period=-2,
    probability=0.20,
    description=(
        "御社の元従業員150名と複数の取引先が共同で損害賠償訴訟を提起しました。\n"
        "請求額は¥500Mに上り、「未払賃金・ハラスメント・不当解雇・契約不履行」が\n"
        "主な訴因として挙げられています。\n"
        "裁判所は仮処分申請も受理し、一部業務の停止命令が出る可能性があります。\n"
        "この訴訟が続く限り、上場審査を通過することは極めて困難です。"
    ),
    choices=[
        Choice(
            label="A. 全面和解（¥200M支払い・訴訟終結）",
            description="大きな出費だが事態収拾が最優先",
            immediate_effect=_lawsuit_settle,
        ),
        Choice(
            label="B. 法廷闘争（¥80M弁護費用・全面対決）",
            description="正当性があれば勝てるが長期化は確実",
            immediate_effect=_lawsuit_fight,
        ),
        Choice(
            label="C. 対応引き延ばし（時間稼ぎ・判断を先送り）",
            description="最悪の選択。事態が雪だるま式に拡大する",
            immediate_effect=_lawsuit_delay,
        ),
    ],
)


WORLD_EVENTS = [
    WORLD_WAR_OUTBREAK,
    WORLD_PANDEMIC,
    WORLD_EARTHQUAKE,
    WORLD_SUPPLIER_SCANDAL,
    WORLD_CUSTOMER_CRISIS,
    WORLD_AI_BOOM,
    WORLD_SUBSIDY,
    WORLD_FX_SHOCK,
    WORLD_LABOR_SHORTAGE,
    WORLD_SNS_SCANDAL,
    WORLD_COMPETITION_PRICE_WAR,
    WORLD_HUMAN_RIGHTS,
    WORLD_SEMICONDUCTOR_SHORTAGE,
    WORLD_INBOUND_BOOM,
    WORLD_YEN_WEAK_BOOM,
    WORLD_DX_DEMAND,
    WORLD_REGULATORY_CHANGE,
    WORLD_INTERNAL_FRAUD,   # ← 社内不正（横領）
    WORLD_HARASSMENT,       # ← パワハラ問題
    WORLD_COFOUNDER_EXIT,   # ← 創業メンバー離脱
    WORLD_AI_DISRUPTION,    # ← SaaS AI陳腐化危機
    WORLD_INVESTOR_REVOLT,  # ← 主要株主退陣要求
    WORLD_EXEC_ARREST,      # ← CFO逮捕スキャンダル
    WORLD_MASS_LAWSUIT,     # ← 集団訴訟
]
