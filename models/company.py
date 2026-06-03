from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class BusinessType(Enum):
    SAAS = "SaaS"
    FINTECH = "FinTech"
    MANUFACTURING = "製造業"
    RETAIL = "小売業"


class Quarter(Enum):
    Q1 = 1
    Q2 = 2
    Q3 = 3
    Q4 = 4


@dataclass
class Shareholder:
    name: str
    shares: int
    is_founder: bool = False
    is_vc: bool = False

    def ratio(self, total_shares: int) -> float:
        return self.shares / total_shares if total_shares > 0 else 0.0


@dataclass
class CapTable:
    shareholders: List[Shareholder] = field(default_factory=list)
    total_shares: int = 0

    def add_shareholder(self, name: str, shares: int, is_founder: bool = False, is_vc: bool = False):
        for s in self.shareholders:
            if s.name == name:
                s.shares += shares
                self.total_shares += shares
                return
        self.shareholders.append(Shareholder(name, shares, is_founder, is_vc))
        self.total_shares += shares

    def founder_ratio(self) -> float:
        founder_shares = sum(s.shares for s in self.shareholders if s.is_founder)
        return founder_shares / self.total_shares if self.total_shares > 0 else 0.0


@dataclass
class Revenue:
    """収益認識会計基準に基づく売上管理"""
    recognized: float = 0.0       # 認識済み売上（百万円）
    deferred: float = 0.0         # 繰延収益（前受金など）
    pipeline: float = 0.0         # 受注残・パイプライン
    growth_rate: float = 0.0      # 四半期成長率


@dataclass
class Flags:
    """因果応報フラグ管理 — 将来の爆弾"""
    # 労務リスク
    unpaid_overtime: bool = False       # 未払残業代放置
    overtime_bomb_timer: int = 0        # 労基署調査まで残りQ数（0=発動済み）

    # 反社フラグ
    antisocial_vendor: bool = False     # 怪しい仕入先と契約
    antisocial_bomb_timer: int = 0

    # 内部統制フラグ
    no_job_separation: bool = False     # 出納と記帳が同一担当
    embezzlement_risk_level: int = 0    # 横領リスクレベル（0〜5）

    # 会計フラグ
    cash_basis_accounting: bool = False  # 現金主義のまま
    no_inventory_count: bool = False    # 棚卸立会なし
    no_voucher_management: bool = False  # 証憑管理未整備
    no_cost_accounting: bool = False    # 原価計算体制なし
    unknown_balances: bool = False      # 不明残高あり
    no_related_party_review: bool = False  # 関連当事者取引未整理

    # ガバナンスフラグ
    no_outside_director: bool = False   # 社外役員未選任
    no_compliance_system: bool = False  # コンプライアンス体制なし

    # 利益操作フラグ（因果応報爆弾）
    profit_manipulation: bool = False        # 利益操作実施済み
    profit_manipulation_type: str = ""       # "revenue_front" or "inventory_inflate"
    profit_manipulation_bomb_timer: int = 0  # 発覚までのカウントダウン

    # 監査フラグ
    audit_contract_rejected: bool = False  # 監査契約拒絶
    short_review_done: bool = False     # ショートレビュー実施済み
    ipo_force_delay: bool = False    # 強制上場延期フラグ（ダメージ蓄積）
    underwriter_intentionally_skipped: bool = False  # 主幹事選定を意図的に先送り

    # 総合リスクスコア（100超えで上場審査NG）
    total_risk_score: int = 0

    def visible_bombs(self) -> List[str]:
        """ショートレビュー後に見えるようになるリスク一覧"""
        risks = []
        if self.unpaid_overtime:
            risks.append(f"⚠️  未払残業代 — 労基署調査まで残り{self.overtime_bomb_timer}Q")
        if self.antisocial_vendor:
            risks.append(f"💣 反社チェック不備 — 主幹事発覚まで残り{self.antisocial_bomb_timer}Q")
        if self.no_job_separation:
            risks.append(f"🔓 出納・記帳の分離なし — 横領リスクLv.{self.embezzlement_risk_level}")
        if self.cash_basis_accounting:
            risks.append("📉 現金主義会計 — 発生主義への移行が未完了")
        if self.no_inventory_count:
            risks.append("📦 棚卸立会なし — 遡及監査不可のリスク")
        if self.no_voucher_management:
            risks.append("📄 証憑管理未整備 — 監査受入不可リスク")
        if self.no_cost_accounting:
            risks.append("🔢 原価計算体制なし — 製造原価の検証不可")
        if self.unknown_balances:
            risks.append("❓ 不明残高あり — 貸借対照表の信頼性低下")
        if self.no_related_party_review:
            risks.append("🤝 関連当事者取引未整理 — 上場審査での重大指摘リスク")
        if self.no_outside_director:
            risks.append("🏛️  社外役員未選任 — ガバナンス体制不備")
        if self.no_compliance_system:
            risks.append("⚖️  コンプライアンス体制なし — 上場審査リスク大")
        if self.profit_manipulation:
            risks.append(f"🔥 不適切な会計処理あり — 監査発覚まで残り{self.profit_manipulation_bomb_timer}Q")
        return risks


@dataclass
class Company:
    name: str
    business_type: BusinessType

    # 財務状況（百万円）
    cash: float = 500.0
    quarterly_burn: float = 50.0
    revenue: Revenue = field(default_factory=Revenue)
    cap_table: CapTable = field(default_factory=CapTable)

    # 管理体制スコア（0〜100）
    internal_control_score: int = 10    # 内部管理体制
    compliance_score: int = 10          # コンプライアンス
    accounting_quality: int = 10        # 決算品質
    governance_score: int = 10          # ガバナンス

    # 信頼・評判
    auditor_trust: int = 50            # 監査法人からの信頼
    investor_trust: int = 50           # 投資家・証券会社からの信頼
    employee_morale: int = 70          # 従業員士気

    # 上場準備状態
    has_audit_contract: bool = False    # 監査契約締結済み
    audit_firm_agreed: bool = False     # 監査法人から契約内諾済み（AGM選任待ち）
    audit_firm_tier: str = ""           # 監査法人候補ティア: "big", "mid", "small", ""=未選定
    has_underwriter: bool = False       # 主幹事証券会社選定済み
    underwriter_pre_exam_passed: bool = False  # 主幹事事前審査合格
    has_cfo: bool = False              # CFO在籍
    shareholder_count: int = 5          # 実株主数（上場要件：150人以上）
    potential_shareholders: int = 0     # SO保有者（潜在株主）— 上場審査の株主数要件には未カウント
    has_esop: bool = False              # 従業員持株会設立済み（毎Q実株主が増加）
    market_cap_million: float = 500.0  # 時価総額（百万円、要件：5億円以上）

    # ── 上場準備チェック項目（時期別） ──
    # N-3期：現状把握と体制構築の開始
    has_mid_term_plan: bool = False           # 中期経営計画策定
    has_capital_policy: bool = False          # 資本政策立案
    # N-2期：管理体制の整備と運用開始
    has_monthly_closing: bool = False         # 月次決算早期化（10日締め）
    has_authority_rules: bool = False         # 職務権限・業務分掌規程
    has_budget_control: bool = False          # 予算管理制度
    has_internal_audit: bool = False          # 内部監査部門設置
    has_antisocial_system: bool = False       # 反社排除体制
    has_ip_protection: bool = False           # 知財保護体制
    # N-1期：運用の徹底と実績の積み上げ
    has_internal_control_system: bool = False # 内部統制システム構築
    has_accounting_auditor: bool = False      # 会計監査人 正式選任
    has_share_admin: bool = False             # 株主名簿管理人
    has_disclosure_system: bool = False       # 適時開示体制
    has_insider_prevention: bool = False      # インサイダー取引防止
    # N期：上場申請と審査対応
    has_articles_amendment: bool = False      # 定款変更
    has_hofuri: bool = False                  # ほふり参加
    has_governance_report: bool = False       # ガバナンス報告書

    # AGM承認により翌四半期に効力が発現するフラグ（会社法上の決議タイミング管理）
    agm_deferred_outside_director: bool = False      # 社外役員候補内定→翌Q就任（会社法329条）
    agm_deferred_auditor_appt: bool = False          # 会計監査人候補選定→翌Q就任（会社法329条2項）
    agm_deferred_articles_amendment: bool = False    # 定款変更可決→翌Q登記完了（会社法466条）
    outside_director_rejected_needs_eogm: bool = False  # 社外役員選任否決→臨時株主総会要（会社法297条）
    articles_amendment_rejected_needs_eogm: bool = False  # 定款変更否決→臨時株主総会で再上程要（会社法466条）

    # フラグ
    flags: Flags = field(default_factory=Flags)

    # イベント履歴
    event_log: List[str] = field(default_factory=list)

    def runway_quarters(self) -> int:
        """資金の持続期間（何四半期持つか）"""
        if self.quarterly_burn <= 0:
            return 99
        net_burn = self.quarterly_burn - self.revenue.recognized
        if net_burn <= 0:
            return 99
        return int(self.cash / net_burn)

    def add_event_log(self, msg: str):
        self.event_log.append(msg)
        if len(self.event_log) > 50:
            self.event_log = self.event_log[-50:]
