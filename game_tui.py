"""
The IPO Path: 栄光への決断
Textual TUI版 — 常時サイドバー + スクロール可能なストーリーエリア
"""
from __future__ import annotations
import sys
import os
import random
from enum import Enum, auto
from typing import Optional, List

sys.path.insert(0, os.path.dirname(__file__))

from textual.app import App, ComposeResult
from textual.widgets import Static, RichLog, Input, Header
from textual.containers import Horizontal
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich import box
from rich.align import Align

from models.company import Company, BusinessType
from engine.timeline import Timeline, N_PERIOD
from engine.finance import (
    initialize_company,
    advance_quarter_financials,
    check_cash_crisis,
    BUSINESS_PARAMS,
)
from engine.roulette import tick_bombs, audit_contract_roulette, roll
from scenario.ipo_knowledge import get_available_events, get_fresh_events, shareholder_meeting_event
from models.events import Choice


# ══════════════════════════════════════════════
# ゲームフェーズ
# ══════════════════════════════════════════════
class Phase(Enum):
    TITLE      = auto()   # タイトル画面
    BIZ_SELECT = auto()   # 業種選択 A/B/C/D
    NAME_INPUT = auto()   # 会社名入力
    CONTINUE   = auto()   # Enter で次へ（_next_action で分岐）
    EVENT_CHOICE = auto() # イベント選択肢 A/B/C/D
    ALT_CHOICE   = auto() # 監査失敗後の代替選択肢
    ENDING       = auto() # ゲーム終了


# ══════════════════════════════════════════════
# メインアプリ
# ══════════════════════════════════════════════
class IPOGameApp(App):

    TITLE = "◆ THE IPO PATH: 栄光への決断 ◆"

    CSS = """
    Screen {
        background: #0d0d1a;
        layout: vertical;
    }

    Header {
        background: #1a1a2e;
        color: #ffd700;
        height: 1;
    }

    #main-area {
        height: 1fr;
    }

    #sidebar {
        width: 36;
        background: #08081a;
        border-right: solid #b8860b;
        overflow-y: auto;
        padding: 0 1;
    }

    #story {
        width: 1fr;
        background: #0d0d1a;
        padding: 0 1;
    }

    Input {
        background: #08081a;
        color: #ffd700;
        border-top: solid #b8860b;
        height: 3;
    }

    Input:focus {
        border-top: solid #ffd700;
    }
    """

    # ─────────────────────────────────────────
    # 初期化
    # ─────────────────────────────────────────
    def __init__(self) -> None:
        super().__init__()
        self.phase: Phase = Phase.TITLE
        self.company: Optional[Company] = None
        self.timeline: Optional[Timeline] = None
        self.pending_events: list = []
        self.pending_event_idx: int = 0
        self._game_events: list = []   # ゲームごとのイベントコピー
        self.selected_biz: int = 0
        self._next_action: str = ""
        self._alt_choices: List[Choice] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="main-area"):
            yield Static("", id="sidebar", markup=True)
            yield RichLog(id="story", markup=True, highlight=False, wrap=True)
        yield Input(id="cmd", placeholder="► Enter キーを押してゲームを開始...")

    def on_mount(self) -> None:
        self.query_one("#cmd", Input).focus()
        self._show_title()
        self._update_sidebar()

    # ─────────────────────────────────────────
    # ヘルパー
    # ─────────────────────────────────────────
    def _story_write(self, content) -> None:
        self.query_one(RichLog).write(content)

    def _story_rule(self, text: str, color: str = "bright_cyan") -> None:
        self.query_one(RichLog).write(
            Rule(f"[{color}]{text}[/{color}]", style=color)
        )

    def _set_placeholder(self, text: str) -> None:
        self.query_one("#cmd", Input).placeholder = text

    def _period_color(self) -> str:
        if self.timeline is None:
            return "white"
        return {
            -3: "bright_blue",
            -2: "bright_cyan",
            -1: "bright_yellow",
            0: "bright_red",
        }.get(self.timeline.n_period, "white")

    # ─────────────────────────────────────────
    # サイドバー構築
    # ─────────────────────────────────────────
    def _update_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", Static)
        sidebar.update(self._build_sidebar())

    def _build_sidebar(self) -> str:
        if self.company is None or self.timeline is None:
            return (
                "\n[dim]─────────────────────[/dim]\n"
                "[bold bright_cyan]  THE IPO PATH[/bold bright_cyan]\n"
                "[dim]  栄光への決断[/dim]\n\n"
                "[dim]  ゲーム開始前[/dim]\n\n"
                "[dim]─────────────────────[/dim]\n"
            )

        c = self.company
        t = self.timeline
        pcol = self._period_color()

        q_hearts = ["○", "○", "○", "○"]
        q_hearts[t.quarter - 1] = f"[{pcol}]❤[/{pcol}]"
        q_str = " ".join(q_hearts)

        def cash_col(cash: float, burn: float) -> str:
            if cash <= 0 or cash < burn * 2:
                return "bright_red"
            if cash < burn * 4:
                return "yellow"
            return "bright_green"

        def sc(v: int) -> str:
            if v >= 70: return "bright_green"
            if v >= 40: return "yellow"
            return "bright_red"

        def bar(v: int, w: int = 10) -> str:
            p = min(max(v, 0), 100) / 100
            f = int(w * p)
            bc = "bright_green" if p > 0.6 else ("yellow" if p > 0.3 else "bright_red")
            return f"[{bc}]{'█' * f}[/{bc}][dim]{'░' * (w - f)}[/dim]"

        def ck(ok: bool) -> str:
            return "[bright_green]✔[/]" if ok else "[bright_red]✘[/]"

        cc = cash_col(c.cash, c.quarterly_burn)
        net = c.revenue.recognized - c.quarterly_burn
        net_col = "bright_green" if net >= 0 else "bright_red"
        net_sign = "+" if net >= 0 else ""
        runway = c.runway_quarters()
        rc = "bright_green" if runway > 8 else ("yellow" if runway > 4 else "bright_red")
        risk = c.flags.total_risk_score
        risk_col = "bright_green" if risk < 30 else ("yellow" if risk < 60 else "bright_red")

        if risk >= 60 or c.investor_trust <= 20:
            mood = "[bright_red]🔴 危険な状態！[/bright_red]"
        elif risk >= 30 or c.compliance_score < 40:
            mood = "[yellow]🟡 注意が必要[/yellow]"
        else:
            mood = "[bright_green]🟢 順調です！[/bright_green]"

        lines: List[str] = [
            f"[bold {pcol}]◆ {t.period_name()} ◆[/bold {pcol}]",
            f" {q_str}  [dim]残{t.quarters_until_ipo()}Q[/dim]",
            "",
            "[dim]─ 財 務 ─────────────────[/dim]",
            f"[{cc}]💰 ¥{c.cash:,.0f}M[/{cc}]",
            f"[bright_green]📈 売上 ¥{c.revenue.recognized:,.0f}M[/]",
            f"[yellow]🔥 支出 ¥{c.quarterly_burn:,.0f}M[/]",
            f"[{net_col}]📊 収支 {net_sign}{net:,.0f}M[/{net_col}]",
            f"[{rc}]⏳ 持続 約{runway}Q[/{rc}]",
            f"[bright_yellow]🏢 ¥{c.market_cap_million:,.0f}M[/]",
            "",
            "[dim]─ スコア ─────────────────[/dim]",
            f"[{sc(c.internal_control_score)}]内管 {c.internal_control_score:>3}[/{sc(c.internal_control_score)}] {bar(c.internal_control_score)}",
            f"[{sc(c.compliance_score)}]法令 {c.compliance_score:>3}[/{sc(c.compliance_score)}] {bar(c.compliance_score)}",
            f"[{sc(c.accounting_quality)}]会計 {c.accounting_quality:>3}[/{sc(c.accounting_quality)}] {bar(c.accounting_quality)}",
            f"[{sc(c.governance_score)}]統治 {c.governance_score:>3}[/{sc(c.governance_score)}] {bar(c.governance_score)}",
            f"[{sc(c.auditor_trust)}]監査 {c.auditor_trust:>3}[/{sc(c.auditor_trust)}] {bar(c.auditor_trust)}",
            f"[{sc(c.investor_trust)}]投資 {c.investor_trust:>3}[/{sc(c.investor_trust)}] {bar(c.investor_trust)}",
            f"[{sc(c.employee_morale)}]士気 {c.employee_morale:>3}[/{sc(c.employee_morale)}] {bar(c.employee_morale)}",
            f"[{risk_col}]💣リスク {risk:>3}[/{risk_col}] {bar(risk)}",
            "",
            "[dim]─ 上場準備チェック ──────[/dim]",
            f"{ck(c.has_audit_contract)} 監査契約",
            f"{ck(c.has_underwriter)} 主幹事証券",
            f"{ck(c.has_cfo)} CFO在籍",
            f"{ck(c.flags.short_review_done)} ショートレビュー",
            f"{ck(not c.flags.no_outside_director)} 社外役員",
            f"{ck(not c.flags.no_related_party_review)} 関連当事者",
            f"{ck(not c.flags.cash_basis_accounting)} 発生主義会計",
            f"{ck(not c.flags.no_inventory_count)} 棚卸管理",
            "",
            "[dim]─ IPO先生 ──────────────[/dim]",
            f" {mood}",
            "",
            f"[dim] {c.name}[/dim]",
        ]
        return "\n".join(lines)

    # ─────────────────────────────────────────
    # 入力ハンドラ
    # ─────────────────────────────────────────
    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        inp = self.query_one("#cmd", Input)
        inp.value = ""
        inp.focus()
        self._dispatch(value)

    def _dispatch(self, value: str) -> None:
        if self.phase == Phase.TITLE:
            self._start_biz_select()

        elif self.phase == Phase.BIZ_SELECT:
            v = value.upper()
            valid = list("ABCD")[: len(BUSINESS_PARAMS)]
            if v in valid:
                self.selected_biz = valid.index(v)
                self._start_name_input()
            else:
                self._story_write(
                    f"[bright_red]  {' / '.join(valid)} のいずれかを入力してください[/bright_red]"
                )

        elif self.phase == Phase.NAME_INPUT:
            self._init_game(value or "テック株式会社")

        elif self.phase == Phase.CONTINUE:
            if self._next_action == "begin_turn":
                self._begin_turn()
            elif self._next_action == "next_event":
                self._show_next_event()
            elif self._next_action == "advance_turn":
                self._advance_turn()

        elif self.phase == Phase.EVENT_CHOICE:
            event = self.pending_events[self.pending_event_idx]
            valid = list("ABCD")[: len(event.choices)]
            if value.upper() in valid:
                self._apply_event_choice(valid.index(value.upper()))
            else:
                self._story_write(
                    f"[bright_red]  {' / '.join(valid)} のいずれかを選んでください[/bright_red]"
                )

        elif self.phase == Phase.ALT_CHOICE:
            valid = list("ABCD")[: len(self._alt_choices)]
            if value.upper() in valid:
                self._apply_alt_choice(valid.index(value.upper()))
            else:
                self._story_write(
                    f"[bright_red]  {' / '.join(valid)} のいずれかを選んでください[/bright_red]"
                )

        elif self.phase == Phase.ENDING:
            self.exit()

    # ─────────────────────────────────────────
    # タイトル画面
    # ─────────────────────────────────────────
    def _show_title(self) -> None:
        story = self.query_one(RichLog)
        story.clear()
        title_art = (
            "  ████████╗██╗  ██╗███████╗    ██╗██████╗  ██████╗\n"
            "     ██╔══╝██║  ██║██╔════╝    ██║██╔══██╗██╔═══██╗\n"
            "     ██║   ███████║█████╗      ██║██████╔╝██║   ██║\n"
            "     ██║   ██╔══██║██╔══╝      ██║██╔═══╝ ██║   ██║\n"
            "     ██║   ██║  ██║███████╗    ██║██║     ╚██████╔╝\n"
            "     ╚═╝   ╚═╝  ╚═╝╚══════╝   ╚═╝╚═╝      ╚═════╝\n"
            "          P  A  T  H  :  栄 光 へ の 決 断"
        )
        self._story_write(
            Panel(
                Text.from_markup(
                    f"[bold bright_cyan]{title_art}[/bold bright_cyan]\n\n"
                    "[dim]〜 IPO準備の知識を、実践の決断を通じて学ぶ経営シミュレーション 〜[/dim]\n\n"
                    "[bright_yellow]上場審査・監査・内部統制・資本政策……[/bright_yellow]\n"
                    "[white]あなたの会社を東証に上場させることができるか？[/white]",
                    justify="center",
                ),
                border_style="bright_cyan",
                box=box.DOUBLE_EDGE,
                padding=(1, 4),
            )
        )
        self._set_placeholder("► Enter キーを押してゲームを開始...")

    # ─────────────────────────────────────────
    # 業種選択
    # ─────────────────────────────────────────
    def _start_biz_select(self) -> None:
        self.phase = Phase.BIZ_SELECT
        self._story_rule("◆ 業種を選んでください ◆", "bright_yellow")
        self._story_write(
            "[dim]業種によって初期資金・成長率・リスクが異なります[/dim]\n"
        )
        labels = ["A", "B", "C", "D"]
        styles = ["bright_cyan", "bright_yellow", "bright_green", "bright_magenta"]
        for i, (btype, params) in enumerate(BUSINESS_PARAMS.items()):
            col = styles[i]
            self._story_write(
                f"  [{col}][ {labels[i]} ][/{col}]  [bold]{btype.value}[/bold]\n"
                f"       [dim]{params['description']}[/dim]\n"
                f"       [dim]初期資金 ¥{params['initial_cash']:.0f}M"
                f"  |  成長率/Q {params['growth_rate']:.0%}"
                f"  |  支出/Q ¥{params['burn_rate']:.0f}M[/dim]\n"
            )
        valid = labels[: len(BUSINESS_PARAMS)]
        self._set_placeholder(f"► 業種を選択 ({' / '.join(valid)})")

    # ─────────────────────────────────────────
    # 会社名入力
    # ─────────────────────────────────────────
    def _start_name_input(self) -> None:
        self.phase = Phase.NAME_INPUT
        btype = list(BUSINESS_PARAMS.keys())[self.selected_biz]
        self._story_write(
            f"\n[bright_green]✔ {btype.value}を選択しました[/bright_green]\n"
        )
        self._story_rule("◆ 会社名を入力してください ◆", "bright_cyan")
        self._story_write(
            "[dim]（空欄でEnterすると「テック株式会社」になります）[/dim]"
        )
        self._set_placeholder("► 会社名を入力...")

    # ─────────────────────────────────────────
    # ゲーム初期化
    # ─────────────────────────────────────────
    def _init_game(self, name: str) -> None:
        btype = list(BUSINESS_PARAMS.keys())[self.selected_biz]
        self.company = Company(name=name, business_type=btype)
        initialize_company(self.company)

        # 初期フラグ（未整備状態）
        self.company.flags.no_voucher_management = True
        self.company.flags.no_job_separation = True
        self.company.flags.no_outside_director = True
        self.company.flags.no_related_party_review = True
        self.company.flags.no_compliance_system = True
        self.company.has_underwriter = False

        self.timeline = Timeline()
        self._game_events = get_fresh_events()   # ← 毎ゲーム新規コピー
        self._update_sidebar()

        self._story_write(
            Panel(
                f"[bold bright_yellow]{name}[/bold bright_yellow] の IPO準備を開始します！\n\n"
                "[dim]N-3期（第1四半期）からスタートです。\n"
                "N期Q4の東証上場審査まで、賢明な決断を積み重ねてください。[/dim]",
                title="[bold bright_green]◆ ゲームスタート ◆[/bold bright_green]",
                border_style="bright_green",
                box=box.DOUBLE_EDGE,
                padding=(1, 2),
            )
        )
        self.phase = Phase.CONTINUE
        self._next_action = "begin_turn"
        self._set_placeholder("► Enter でゲーム開始...")

    # ─────────────────────────────────────────
    # ターン開始
    # ─────────────────────────────────────────
    def _begin_turn(self) -> None:
        c = self.company
        t = self.timeline
        pcol = self._period_color()

        self._story_rule(
            f"  {t.period_name()} — {t.full_label()}  残り{t.quarters_until_ipo()}Q  ",
            pcol,
        )

        # ゲームオーバーチェック
        if check_cash_crisis(c):
            self._show_ending("bankruptcy", [])
            return
        if c.investor_trust <= 5 or c.auditor_trust <= 5:
            self._show_ending("dismissed", [])
            return

        # クライマックス: N期Q4 = 東証上場審査
        if t.n_period == N_PERIOD and t.quarter == 4:
            self._run_tse_exam()
            return

        # イベント取得
        self.pending_events = get_available_events(c, t.n_period, self._game_events)
        self.pending_event_idx = 0

        if self.pending_events:
            self._show_next_event()
        else:
            self._story_write("[dim]── 本四半期は追加の意思決定事項はありません ──[/dim]")
            self.phase = Phase.CONTINUE
            self._next_action = "advance_turn"
            self._set_placeholder("► Enter でターンを進める...")

    # ─────────────────────────────────────────
    # イベント表示
    # ─────────────────────────────────────────
    def _show_next_event(self) -> None:
        event = self.pending_events[self.pending_event_idx]

        self._story_write(
            Panel(
                f"[white]{event.description}[/white]",
                title=f"[bold bright_yellow]◇ {event.title} ◇[/bold bright_yellow]",
                border_style="bright_yellow",
                box=box.DOUBLE_EDGE,
                padding=(1, 2),
            )
        )

        labels = ["A", "B", "C", "D"]
        style_colors = ["bright_cyan", "bright_yellow", "bright_green", "bright_magenta"]
        self._story_write("")
        for i, choice in enumerate(event.choices):
            col = style_colors[i]
            hints: List[str] = []
            if choice.profit_hint:
                hints.append(f"[bright_green]💰 {choice.profit_hint}[/]")
            if choice.risk_hint:
                hints.append(f"[yellow]⚠ {choice.risk_hint}[/]")
            hint_str = "   " + "  /  ".join(hints) if hints else ""
            self._story_write(
                f"  [{col}][ {labels[i]} ][/{col}]  "
                f"[bold]{choice.label.lstrip('ABCD. ')}[/bold]\n"
                f"       [dim]{choice.description}[/dim]{hint_str}"
            )

        valid = labels[: len(event.choices)]
        self.phase = Phase.EVENT_CHOICE
        self._set_placeholder(f"► 選択 ({' / '.join(valid)})")

    # ─────────────────────────────────────────
    # 選択肢適用
    # ─────────────────────────────────────────
    def _apply_event_choice(self, idx: int) -> None:
        event = self.pending_events[self.pending_event_idx]
        choice = event.choices[idx]
        labels = ["A", "B", "C", "D"]

        self._story_write(f"\n[bright_cyan]▶ {labels[idx]} を選択しました[/bright_cyan]")

        result_msg = choice.immediate_effect(self.company)
        if choice.future_flag_setter:
            choice.future_flag_setter(self.company)

        event.fired = True
        # 繰り返しイベントは「同じN期には再発火しない」よう記録
        if not event.one_shot:
            event.last_fired_n_period = self.timeline.n_period
        self.company.add_event_log(
            f"[{self.timeline.full_label()}] {event.title}: {choice.label[:30]}"
        )

        is_good = not any(
            kw in result_msg for kw in ["⚠️", "❗", "❌", "💰（短期のみ）"]
        )
        col = "bright_green" if is_good else "bright_red"
        icon = "✅" if is_good else "⚡"

        self._story_write(
            Panel(
                f"{icon}  {result_msg}",
                title=f"[bold {col}]◆ 結果 ◆[/bold {col}]",
                border_style=col,
                box=box.HEAVY,
                padding=(0, 2),
            )
        )

        self._update_sidebar()
        self.pending_event_idx += 1

        if self.pending_event_idx < len(self.pending_events):
            self.phase = Phase.CONTINUE
            self._next_action = "next_event"
            self._set_placeholder("► Enter で次のイベントへ...")
        else:
            self.phase = Phase.CONTINUE
            self._next_action = "advance_turn"
            self._set_placeholder("► Enter でターンを進める...")

    # ─────────────────────────────────────────
    # ターン進行（財務・爆弾・タイムライン）
    # ─────────────────────────────────────────
    def _advance_turn(self) -> None:
        c = self.company
        t = self.timeline

        # 財務進行
        advance_quarter_financials(c, t.n_period, t.quarter)

        # 爆弾タイマー
        triggered = tick_bombs(c)
        for bomb_msg in triggered:
            c.add_event_log(f"[{t.full_label()}] 爆弾発動!")
            self._story_write(
                Panel(
                    f"[white]{bomb_msg}[/white]",
                    title="[bold bright_red]  💥 過去の決断の代償！ 💥  [/bold bright_red]",
                    border_style="bright_red",
                    box=box.DOUBLE_EDGE,
                    padding=(1, 2),
                )
            )

        # タイムライン進行（old_n_period を保存してから進める）
        old_n_period = t.n_period
        period_events = t.advance()
        self._update_sidebar()

        # 定時株主総会（年度末）
        if period_events.get("year_end"):
            result = shareholder_meeting_event(c, old_n_period)
            period_label = {
                -3: "N-3期", -2: "N-2期（直前々期）",
                -1: "N-1期（直前期）", 0: "N期（申請期）",
            }.get(old_n_period, "")
            self._story_write(
                Panel(
                    f"[white]{result}[/white]",
                    title=f"[bold]🏢 {period_label} 定時株主総会[/bold]",
                    border_style="bright_white",
                    box=box.HEAVY,
                    padding=(1, 1),
                )
            )

        # ─── N-2期突入：監査契約ルーレット ───
        if period_events.get("enter_n2"):
            self._story_rule("◆ N-2期（直前々期）に突入！ ◆", "bright_cyan")
            self._story_write(
                "[bold yellow]監査法人との「準金商法監査契約」を結ぶ時期です。\n"
                "内部管理体制が問われます……[/bold yellow]\n"
            )
            self._run_audit_roulette()
            return  # audit_roulette が continuation を担う

        # ─── N-1期突入 ───
        if period_events.get("enter_n1"):
            self._story_rule("◆ N-1期（直前期）スタート ◆", "bright_yellow")
            self._story_write(
                "[bold yellow]直前期に入りました。2期目の監査が始まります。\n"
                "内部統制報告制度への対応も本格化します。[/bold yellow]\n"
            )

        # ─── N期（申請期）突入 ───
        if period_events.get("enter_n"):
            self._story_rule("◆ 申請期 N期 スタート！ ◆", "bright_red")
            self._story_write(
                "[bold bright_red]N期Q4に東証上場審査が行われます。\n"
                "今までの準備の総決算です！[/bold bright_red]\n"
            )
            if not c.has_underwriter:
                if c.investor_trust >= 50 and c.compliance_score >= 40:
                    c.has_underwriter = True
                    self._story_write(
                        "[bright_green]✅ 主幹事証券会社が決定しました！[/bright_green]"
                    )
                else:
                    self._story_write(
                        "[bright_red]⚠️  主幹事証券会社が未決定のまま申請期に入りました！[/bright_red]"
                    )
            self._update_sidebar()

        # 次のターンへ
        self.phase = Phase.CONTINUE
        self._next_action = "begin_turn"
        self._set_placeholder("► Enter で次のターンへ...")

    # ─────────────────────────────────────────
    # 監査契約ルーレット（N-2期突入時）
    # ─────────────────────────────────────────
    def _run_audit_roulette(self) -> None:
        success, msg = audit_contract_roulette(self.company)
        color = "bright_green" if success else "bright_red"
        title = "🎊 監査契約 締結！" if success else "💔 監査契約 拒絶"

        self._story_write(
            Panel(
                f"[white]{msg}[/white]",
                title=f"[bold {color}]🎲 監査契約ルーレット — {title}[/bold {color}]",
                border_style=color,
                box=box.DOUBLE_EDGE,
                padding=(1, 2),
            )
        )
        self._update_sidebar()

        if not success:
            self._story_write(
                "\n[bold yellow]監査法人に受嘱を断られました。どう対応しますか？[/bold yellow]\n"
            )
            self._alt_choices = [
                Choice(
                    label="A. 急いで体制整備して別の監査法人に再チャレンジ（¥20M）",
                    description="コストはかかるが上場スケジュールを維持しようとする",
                    immediate_effect=lambda c: self._emergency_internal_control(c),
                ),
                Choice(
                    label="B. 上場を1年延期して体制整備に専念する",
                    description="確実な上場のため、じっくり準備する",
                    immediate_effect=lambda c: self._postpone_ipo(c),
                ),
            ]
            for i, ch in enumerate(self._alt_choices):
                col = ["bright_cyan", "bright_yellow"][i]
                lbl = "AB"[i]
                self._story_write(
                    f"  [{col}][ {lbl} ][/{col}]  [bold]{ch.label.lstrip('AB. ')}[/bold]\n"
                    f"       [dim]{ch.description}[/dim]"
                )
            self.phase = Phase.ALT_CHOICE
            self._set_placeholder("► 選択 (A / B)")
        else:
            self.phase = Phase.CONTINUE
            self._next_action = "begin_turn"
            self._set_placeholder("► Enter で次のターンへ...")

    def _apply_alt_choice(self, idx: int) -> None:
        choice = self._alt_choices[idx]
        labels = ["A", "B"]
        self._story_write(f"\n[bright_cyan]▶ {labels[idx]} を選択しました[/bright_cyan]")
        result_msg = choice.immediate_effect(self.company)
        self._story_write(
            Panel(
                f"[white]{result_msg}[/white]",
                title="[bold bright_cyan]◆ 結果 ◆[/bold bright_cyan]",
                border_style="bright_cyan",
                box=box.HEAVY,
                padding=(0, 2),
            )
        )
        self._update_sidebar()
        self.phase = Phase.CONTINUE
        self._next_action = "begin_turn"
        self._set_placeholder("► Enter で次のターンへ...")

    def _emergency_internal_control(self, company: Company) -> str:
        company.cash -= 20.0
        company.internal_control_score = min(100, company.internal_control_score + 20)
        company.accounting_quality = min(100, company.accounting_quality + 15)
        if roll(0.5):
            company.has_audit_contract = True
            return (
                "✅ 緊急体制整備の結果、別の監査法人と契約できました！\n"
                "   ¥20M支出 / 内部統制+20 / 会計品質+15"
            )
        else:
            company.flags.total_risk_score += 15
            return (
                "❌ 再チャレンジしましたが、監査法人に断られました。\n"
                "   ¥20M支出 / リスクスコア+15"
            )

    def _postpone_ipo(self, company: Company) -> str:
        company.internal_control_score = min(100, company.internal_control_score + 30)
        company.accounting_quality = min(100, company.accounting_quality + 25)
        company.flags.total_risk_score = max(0, company.flags.total_risk_score - 10)
        return (
            "📅 上場を1年延期して体制整備に専念します。\n"
            "   内部統制+30 / 会計品質+25 / リスクスコア-10"
        )

    # ─────────────────────────────────────────
    # 東証上場審査（クライマックス）
    # ─────────────────────────────────────────
    def _run_tse_exam(self) -> None:
        c = self.company
        self._story_rule("★  東京証券取引所 上場審査  ★", "bright_red")
        self._story_write(
            Panel(
                "[bold white]あなたの会社の命運が決まる瞬間——\n\n"
                "東証の審査官が資料を開きます。\n\n"
                "これまでの全ての決断が、ここで問われます。[/bold white]",
                border_style="bright_red",
                box=box.DOUBLE_EDGE,
                padding=(1, 3),
            )
        )

        issues: List[str] = []
        passed: List[str] = []

        # 形式要件
        self._story_write(
            Rule("[bold bright_cyan] 第一審査：形式要件 [/bold bright_cyan]", style="bright_cyan")
        )
        formal_checks = [
            ("👥 株主数 150人以上",
             c.shareholder_count >= 150,
             f"現在 {c.shareholder_count}人"),
            ("🏢 時価総額 5億円以上",
             c.market_cap_million >= 500,
             f"現在 ¥{c.market_cap_million:.0f}M"),
            ("📋 監査契約締結済み",
             c.has_audit_contract,
             "2期間の監査証明が必要"),
            ("🏦 主幹事証券会社選定済み",
             c.has_underwriter,
             "引受契約が必要"),
        ]
        for label, ok, detail in formal_checks:
            if ok:
                self._story_write(f"  [bold bright_green]✔ PASS[/]  {label}")
                passed.append(label)
            else:
                self._story_write(
                    f"  [bold bright_red]✘ FAIL[/]  {label}  [dim]← {detail}[/dim]"
                )
                issues.append(f"{label} — {detail}")

        # 実質審査
        self._story_write("")
        self._story_write(
            Rule("[bold bright_yellow] 第二審査：実質審査 [/bold bright_yellow]", style="bright_yellow")
        )
        substance_checks = [
            ("🔍 反社会的勢力との関係",
             not c.flags.antisocial_vendor,
             "反社チェック不備が疑われます"),
            ("🏗️  内部管理体制（スコア50以上）",
             c.internal_control_score >= 50,
             f"スコア {c.internal_control_score}"),
            ("⚖️  コンプライアンス体制（50以上）",
             c.compliance_score >= 50,
             f"スコア {c.compliance_score}"),
            ("📒 会計処理の適正性",
             not c.flags.cash_basis_accounting,
             "現金主義会計が残存"),
            ("🤝 関連当事者取引の整理",
             not c.flags.no_related_party_review,
             "関連当事者取引が未整理"),
            ("🏛️  ガバナンス体制（50以上）",
             c.governance_score >= 50,
             f"スコア {c.governance_score}"),
            ("💣 累積リスクスコア（60未満）",
             c.flags.total_risk_score < 60,
             f"現在 {c.flags.total_risk_score}"),
        ]
        for label, ok, detail in substance_checks:
            if ok:
                self._story_write(f"  [bold bright_green]✔ PASS[/]  {label}")
                passed.append(label)
            else:
                self._story_write(
                    f"  [bold bright_red]✘ FAIL[/]  {label}  [dim]← {detail}[/dim]"
                )
                issues.append(f"{label} — {detail}")

        # 審査結果
        self._story_write("")
        if not issues:
            self._story_write(
                Panel(
                    "[bold bright_yellow]🎊 全審査項目をクリアしました！\n\n"
                    "東証への上場が承認されました！[/bold bright_yellow]",
                    title="[bold bright_yellow] ★ 上場承認！ ★ [/bold bright_yellow]",
                    border_style="bright_yellow",
                    box=box.DOUBLE_EDGE,
                    padding=(1, 3),
                )
            )
            self._show_ending("success", [])
        else:
            issue_lines = "\n".join(f"  [bright_red]✘[/]  {i}" for i in issues)
            self._story_write(
                Panel(
                    f"[bold bright_red]以下の問題が指摘されました:[/bold bright_red]\n\n"
                    f"{issue_lines}",
                    title="[bold bright_red] ⚠ 審査不通過 ⚠ [/bold bright_red]",
                    border_style="bright_red",
                    box=box.DOUBLE_EDGE,
                    padding=(1, 2),
                )
            )
            fatal = any("反社" in i or "監査契約" in i for i in issues)
            self._show_ending("dismissed" if fatal else "delay", issues)

    # ─────────────────────────────────────────
    # エンディング
    # ─────────────────────────────────────────
    def _show_ending(self, ending_type: str, issues: list) -> None:
        c = self.company

        if ending_type == "success":
            self._story_write(
                Panel(
                    "[bold bright_yellow]🎊  上場おめでとうございます！  🎊[/bold bright_yellow]\n\n"
                    "東京証券取引所に株式が上場されました！\n\n"
                    f"[bright_yellow]時価総額: ¥{c.market_cap_million:,.0f}M[/bright_yellow]\n"
                    f"[bright_green]最終売上: ¥{c.revenue.recognized:,.0f}M[/bright_green]",
                    title="[bold bright_yellow]  👑 CONGRATULATIONS! 上場成功 👑  [/bold bright_yellow]",
                    border_style="bright_yellow",
                    box=box.DOUBLE_EDGE,
                    padding=(1, 4),
                )
            )
        elif ending_type == "delay":
            self._story_write(
                Panel(
                    "[bold bright_red]上場延期が決定しました[/bold bright_red]\n\n"
                    "[yellow]改善後に再申請が必要です。上場は最低1年延期されます。[/yellow]",
                    title="[bold bright_red]  ⚠  上場延期  ⚠  [/bold bright_red]",
                    border_style="bright_red",
                    box=box.DOUBLE_EDGE,
                    padding=(1, 2),
                )
            )
        elif ending_type == "bankruptcy":
            self._story_write(
                Panel(
                    "[bold bright_red]資金がショートしました[/bold bright_red]\n\n"
                    "上場前に資金が底をつき、事業継続が困難になりました。\n"
                    "[yellow]資本政策と収益基盤の確立が上場準備の大前提です。[/yellow]",
                    title="[bold bright_red]  💔  GAME OVER — 資金ショート  💔  [/bold bright_red]",
                    border_style="bright_red",
                    box=box.DOUBLE_EDGE,
                    padding=(1, 2),
                )
            )
        elif ending_type == "dismissed":
            self._story_write(
                Panel(
                    "[bold bright_red]代表取締役から解任通告を受けました[/bold bright_red]\n\n"
                    "コンプライアンス違反や不正の発覚により\n"
                    "投資家・取締役会からの信頼を完全に失いました。",
                    title="[bold bright_red]  🚫  GAME OVER — 代表取締役解任  🚫  [/bold bright_red]",
                    border_style="bright_red",
                    box=box.DOUBLE_EDGE,
                    padding=(1, 2),
                )
            )

        self._show_feedback()
        self.phase = Phase.ENDING
        self._set_placeholder("► Enter で終了...")

    # ─────────────────────────────────────────
    # 学習フィードバック
    # ─────────────────────────────────────────
    def _show_feedback(self) -> None:
        c = self.company
        self._story_write("")
        self._story_write(
            Rule("[bold bright_cyan] 📚 実務学習フィードバック [/bold bright_cyan]", style="bright_cyan")
        )
        self._story_write("")

        feedbacks: List[tuple] = []

        if c.flags.unpaid_overtime:
            feedbacks.append((
                "⏰ 労務管理",
                "未払残業代を放置したため上場直前に労基署申告が発生しました。\n"
                "N-3期から勤怠管理システムの整備が必要でした。",
            ))
        if c.flags.antisocial_vendor:
            feedbacks.append((
                "🔍 反社チェック",
                "取引先の審査を怠ったため主幹事証券会社から上場延期を通告されました。\n"
                "主幹事証券会社は全取引先の反社チェックを必ず実施します。",
            ))
        if c.flags.no_job_separation:
            feedbacks.append((
                "🔒 職務分掌",
                "出納と記帳の分離が未実施のため横領リスクが高い状態が続きました。\n"
                "職務分掌は内部統制の基本中の基本です。",
            ))
        if c.flags.cash_basis_accounting:
            feedbacks.append((
                "📒 収益認識",
                "現金主義から発生主義への移行が未完了でした。\n"
                "N-3期から移行に着手しないとN-2期の監査開始時に大混乱が生じます。",
            ))
        if not c.flags.short_review_done:
            feedbacks.append((
                "🔍 ショートレビュー",
                "実施しなかったため潜在リスクが可視化されませんでした。\n"
                "N-3期に実施することで課題を事前に整理できます。",
            ))
        if c.flags.audit_contract_rejected:
            feedbacks.append((
                "📋 監査契約",
                "監査法人に受嘱を拒絶されました。\n"
                "N-2期期首までに受入体制を整えることが絶対条件です。",
            ))

        if not feedbacks:
            feedbacks.append((
                "🎊 総評",
                "素晴らしい判断の連続でした！\n"
                "IPO準備の鉄則：「短期コスト削減 ＜ 長期リスク管理」",
            ))

        for i, (title, body) in enumerate(feedbacks, 1):
            self._story_write(
                Panel(
                    f"[white]{body}[/white]",
                    title=f"[bold bright_cyan] 📖 教訓{i}：{title} [/bold bright_cyan]",
                    border_style="bright_cyan",
                    box=box.ROUNDED,
                    padding=(0, 2),
                )
            )

        # 最終スコアサマリー
        self._story_write("")
        summary = Table(
            title="[bold bright_yellow]◆ 最終スコアサマリー ◆[/bold bright_yellow]",
            box=box.DOUBLE_EDGE,
            title_style="bold",
            show_header=True,
            header_style="bold dim",
        )
        summary.add_column("カテゴリ", style="bold")
        summary.add_column("スコア", justify="center")
        summary.add_column("評価", justify="center")

        def grade(s: int) -> tuple:
            if s >= 90: return ("S", "bright_yellow")
            if s >= 75: return ("A", "bright_green")
            if s >= 60: return ("B", "bright_cyan")
            if s >= 40: return ("C", "yellow")
            return ("D", "bright_red")

        for label, score in [
            ("内部管理体制", c.internal_control_score),
            ("コンプライアンス", c.compliance_score),
            ("会計品質", c.accounting_quality),
            ("ガバナンス", c.governance_score),
            ("監査法人信頼", c.auditor_trust),
            ("投資家信頼", c.investor_trust),
        ]:
            g, gc = grade(score)
            summary.add_row(label, str(score), f"[bold {gc}]{g}[/]")

        self._story_write(summary)


# ══════════════════════════════════════════════
# エントリーポイント
# ══════════════════════════════════════════════
if __name__ == "__main__":
    app = IPOGameApp()
    app.run()
