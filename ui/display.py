"""
The IPO Path: 栄光への決断
アニメRPG風UIモジュール（Persona5テイスト × 和風ビジュアル）
"""
import time
import random
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.text import Text
from rich.rule import Rule
from rich.prompt import Prompt
from rich import box
from rich.align import Align
from rich.layout import Layout
from rich.live import Live

from models.company import Company
from engine.timeline import Timeline

console = Console()

# ══════════════════════════════════════════════
# アニメ風カラーパレット（ペルソナ5 × 和風）
# ══════════════════════════════════════════════
C_GOLD      = "bold bright_yellow"
C_SAKURA    = "bold #ff79c6"        # 桜ピンク
C_CYAN      = "bold bright_cyan"
C_LIME      = "bold bright_green"
C_DANGER    = "bold bright_red"
C_WARN      = "bold yellow"
C_DIM       = "dim white"
C_WHITE     = "bold white"
C_PURPLE    = "bold magenta"
C_BLUE      = "bold bright_blue"

# 装飾記号
DECO_LINE   = "═"
DECO_STAR   = "★"
DECO_DIAMOND= "◆"
DECO_ARROW  = "▶"
DECO_SKULL  = "💀"
DECO_CROWN  = "👑"
DECO_FIRE   = "🔥"
DECO_BOMB   = "💣"

# ══════════════════════════════════════════════
# キャラクター（アドバイザー吹き出し）
# ══════════════════════════════════════════════
ADVISOR_ART = """\
  ╭──────╮
  │ (^_^)│  IPO先生
  │ CFO  │  公認会計士
  ╰──────╯"""

ADVISOR_TIPS = {
    "good":  "順調ですよ！この調子で進みましょう。",
    "warn":  "少し気になる点があります。慎重に。",
    "danger":"このままでは上場審査を通過できません！",
    "bomb":  "過去の決断のツケが回ってきました……",
}


# ══════════════════════════════════════════════
# ユーティリティ
# ══════════════════════════════════════════════
def _score_color(score: int) -> str:
    if score >= 70: return "bright_green"
    if score >= 40: return "yellow"
    return "bright_red"


def _cash_color(cash: float, burn: float) -> str:
    if cash <= 0:        return "bright_red"
    if cash < burn * 2:  return "bright_red"
    if cash < burn * 4:  return "yellow"
    return "bright_green"


def _hp_bar(value: int, max_val: int = 100, width: int = 16) -> str:
    """アニメ風HPバー"""
    pct = min(value, max_val) / max_val
    filled = int(width * pct)
    empty  = width - filled
    if pct > 0.6:
        block = "[bright_green]█[/]"
    elif pct > 0.3:
        block = "[yellow]█[/]"
    else:
        block = "[bright_red]█[/]"
    empty_block = "[dim]░[/]"
    return block * filled + empty_block * empty


def _risk_bar(value: int, width: int = 16) -> str:
    """リスクバー（逆方向・赤が悪い）"""
    pct = min(value, 100) / 100
    filled = int(width * pct)
    empty  = width - filled
    if pct > 0.6:
        block = "[bright_red]█[/]"
    elif pct > 0.3:
        block = "[yellow]█[/]"
    else:
        block = "[bright_green]█[/]"
    return block * filled + "[dim]░[/]" * empty


def _typewriter(text: str, delay: float = 0.018, style: str = ""):
    """タイプライター演出"""
    for char in text:
        console.print(char, end="", style=style)
        time.sleep(delay)
    console.print()


def _flash_rule(text: str, color: str = "bright_cyan", flashes: int = 2):
    """点滅風ルール演出"""
    for _ in range(flashes):
        console.print(Rule(f"[{color}]{text}[/{color}]", style=color))
        time.sleep(0.12)
        console.print("\033[1A\033[2K", end="")
    console.print(Rule(f"[{color}]{text}[/{color}]", style=color))


def _advisor_bubble(mood: str = "good"):
    """IPO先生の吹き出し表示"""
    tip = ADVISOR_TIPS.get(mood, ADVISOR_TIPS["good"])
    art_lines = ADVISOR_ART.strip().split("\n")
    bubble_text = "\n".join(art_lines) + f"\n  💬 {tip}"
    console.print(Panel(
        bubble_text,
        border_style="dim cyan",
        padding=(0, 1),
        width=45,
    ))


# ══════════════════════════════════════════════
# メインダッシュボード（アニメ風リデザイン）
# ══════════════════════════════════════════════
def render_dashboard(company: Company, timeline: Timeline):
    """毎ターン表示するメインダッシュボード"""
    console.clear()

    # ─── タイトルバナー ───
    period_colors = {-3: "bright_blue", -2: "bright_cyan", -1: "bright_yellow", 0: "bright_red"}
    pcol = period_colors.get(timeline.n_period, "white")

    banner = Text(justify="center")
    banner.append("  ◆ THE IPO PATH  ", style="bold white on #1a1a2e")
    banner.append(" 栄光への決断 ", style=f"bold white on {pcol}")
    banner.append("  ◆  ", style="bold white on #1a1a2e")
    console.print(Align.center(banner))
    console.print()

    # ─── 期間バナー（アニメ風フレーム）───
    q_blocks = ["[dim]①[/]","[dim]②[/]","[dim]③[/]","[dim]④[/]"]
    q_blocks[timeline.quarter - 1] = f"[{pcol}]❤[/{pcol}]"
    q_display = " ".join(q_blocks)

    period_text = (
        f"[{pcol}]【 {timeline.period_name()} 】[/{pcol}]"
        f"  Quarter: {q_display}"
        f"  [dim]残り[/dim] [{pcol}]{timeline.quarters_until_ipo()}Q[/{pcol}] [dim]で上場審査[/dim]"
    )
    console.print(Panel(
        Align.center(period_text),
        border_style=pcol,
        padding=(0, 2),
        box=box.DOUBLE_EDGE,
    ))
    console.print()

    # ─── 左：財務パネル ／ 右：スコアパネル ───
    cash = company.cash
    burn = company.quarterly_burn
    net  = company.revenue.recognized - burn
    runway = company.runway_quarters()
    cash_col = _cash_color(cash, burn)

    # 財務テーブル
    fin = Table(box=None, show_header=False, padding=(0,1), expand=True)
    fin.add_column("", style="dim", width=18)
    fin.add_column("", justify="right")

    fin.add_row("💰 手元資金", f"[{cash_col}]¥{cash:,.0f}百万円[/{cash_col}]")
    fin.add_row("  ", _hp_bar(int(min(cash, 2000)), 2000))
    fin.add_row("📈 売上（今期）", f"[bright_green]¥{company.revenue.recognized:,.0f}百万円[/]")
    fin.add_row("🔥 四半期の支出", f"[yellow]¥{burn:,.0f}百万円[/]")
    net_label = "黒字" if net >= 0 else "赤字"
    fin.add_row("📊 四半期の収支", f"[{'bright_green' if net>=0 else 'bright_red'}]{net_label} {'+' if net>=0 else ''}{net:,.0f}百万円[/]")
    rway_col = "bright_green" if runway>8 else ("yellow" if runway>4 else "bright_red")
    fin.add_row("⏳ 資金の持続期間", f"[{rway_col}]あと約{runway}四半期[/{rway_col}]")
    fin.add_row("🏢 会社の推定価値", f"[bright_yellow]¥{company.market_cap_million:,.0f}百万円[/]")
    sc_col = "bright_green" if company.shareholder_count >= 150 else "yellow"
    fin.add_row("👥 株主数",      f"[{sc_col}]{company.shareholder_count}人[/{sc_col}] [dim]/150人[/dim]")

    # スコアテーブル（HPバー付き）
    sco = Table(box=None, show_header=False, padding=(0,1), expand=True)
    sco.add_column("", style="dim", width=14)
    sco.add_column("", width=4, justify="right")
    sco.add_column("", width=20)

    score_data = [
        ("🏗️ 内部管理",    company.internal_control_score),
        ("⚖️ コンプラ",    company.compliance_score),
        ("📒 会計品質",    company.accounting_quality),
        ("🏛️ ガバナンス",  company.governance_score),
        ("🤝 監査信頼",    company.auditor_trust),
        ("💼 投資家信頼",  company.investor_trust),
        ("😊 士気",        company.employee_morale),
    ]
    for label, score in score_data:
        col = _score_color(score)
        sco.add_row(label, f"[{col}]{score}[/{col}]", _hp_bar(score))

    # リスクスコア（反転バー）
    risk = company.flags.total_risk_score
    rcol = "bright_green" if risk<30 else ("yellow" if risk<60 else "bright_red")
    sco.add_row(
        f"[{rcol}]💣 リスク[/{rcol}]",
        f"[{rcol}]{risk}[/{rcol}]",
        _risk_bar(risk) + f"[dim] /100[/dim]"
    )

    console.print(Columns([
        Panel(fin, title=f"[{C_GOLD}]◆ 財務状況 ◆[/{C_GOLD}]",
              border_style="bright_blue", box=box.HEAVY),
        Panel(sco, title=f"[{C_GOLD}]◆ 準備スコア ◆[/{C_GOLD}]",
              border_style="bright_blue", box=box.HEAVY),
    ], equal=True))

    # ─── 上場準備チェックリスト（アイコン付き横並び）───
    def ck(ok): return f"[bright_green]✔[/]" if ok else f"[bright_red]✘[/]"
    checks = [
        f"{ck(company.has_audit_contract)} 監査契約",
        f"{ck(company.has_underwriter)} 主幹事証券",
        f"{ck(company.has_cfo)} CFO",
        f"{ck(company.flags.short_review_done)} ショートレビュー",
        f"{ck(not company.flags.no_outside_director)} 社外役員",
        f"{ck(not company.flags.no_related_party_review)} 関連当事者整理",
        f"{ck(not company.flags.cash_basis_accounting)} 発生主義会計",
        f"{ck(not company.flags.no_inventory_count)} 棚卸管理",
    ]
    checklist_text = "  ".join(checks)
    console.print(Panel(
        Align.center(checklist_text),
        title=f"[{C_GOLD}]◆ 上場準備チェックリスト ◆[/{C_GOLD}]",
        border_style="dim",
        box=box.SIMPLE_HEAD,
    ))

    # ─── 潜在リスク（ショートレビュー後のみ）───
    if company.flags.short_review_done:
        bombs = company.flags.visible_bombs()
        if bombs:
            bomb_lines = "\n".join(f"  {b}" for b in bombs)
            console.print(Panel(
                bomb_lines,
                title=f"[{C_DANGER}]⚠  検出済みリスク 要対処  ⚠[/{C_DANGER}]",
                border_style="bright_red",
                box=box.HEAVY,
            ))

    # ─── キャップテーブル（コンパクト版）───
    if company.cap_table.shareholders:
        cap = Table(box=box.SIMPLE, title=f"[{C_GOLD}]📊 キャップテーブル[/{C_GOLD}]",
                    title_style="bold", show_header=True, header_style="bold dim")
        cap.add_column("株主名", style="bold")
        cap.add_column("持分比率", justify="right")
        cap.add_column("種別", justify="center")
        for sh in company.cap_table.shareholders:
            ratio = sh.ratio(company.cap_table.total_shares)
            col = "bright_green" if ratio > 0.1 else "white"
            kind = "👤創業者" if sh.is_founder else ("💼VC" if sh.is_vc else "🌱エンジェル")
            cap.add_row(sh.name, f"[{col}]{ratio:.1%}[/{col}]", kind)
        console.print(cap)

    # ─── IPO先生アドバイス ───
    risk = company.flags.total_risk_score
    morale = "danger" if risk >= 60 or company.investor_trust <= 20 else \
             "warn"   if risk >= 30 or company.compliance_score < 40 else "good"
    console.print()
    _advisor_bubble(morale)
    console.print()


# ══════════════════════════════════════════════
# イベント表示（アニメ演出）
# ══════════════════════════════════════════════
def render_event(event_title: str, description: str):
    """イベント発生演出"""
    console.print()
    # ピカッとした区切り線
    _flash_rule(f"  ◆  EVENT  ◆  {event_title}  ◆", color="bright_yellow", flashes=1)

    # 背景パネル
    console.print(Panel(
        description,
        title=f"[{C_GOLD}]◇ {event_title} ◇[/{C_GOLD}]",
        border_style="bright_yellow",
        box=box.DOUBLE_EDGE,
        padding=(1, 3),
    ))


def render_choices(choices) -> int:
    """
    選択肢をA/B/C/D形式で表示し、プレイヤーの入力を受け取る。
    戻り値: 選択インデックス（0始まり）
    """
    labels = ["A", "B", "C", "D"]
    label_styles = [
        ("bright_cyan",   "on #0d3b6e"),  # A: 青
        ("bright_yellow", "on #3b2d00"),  # B: 金
        ("bright_green",  "on #0d3b1e"),  # C: 緑
        ("bright_magenta","on #2d0d3b"),  # D: 紫
    ]

    console.print()
    for i, choice in enumerate(choices):
        lbl = labels[i]
        fg, bg = label_styles[i]

        hint_parts = []
        if choice.profit_hint:
            hint_parts.append(f"[bright_green]💰 {choice.profit_hint}[/]")
        if choice.risk_hint:
            hint_parts.append(f"[yellow]⚠  {choice.risk_hint}[/]")
        hint_str = "   " + "  /  ".join(hint_parts) if hint_parts else ""

        body = (
            f"[{fg} {bg}] {lbl} [/{fg} {bg}]  "
            f"[bold]{choice.label.lstrip('ABCD. ')}[/bold]\n"
            f"     [{C_DIM}]{choice.description}[/{C_DIM}]"
            f"{hint_str}"
        )
        console.print(Panel(
            body,
            border_style=fg,
            box=box.ROUNDED,
            padding=(0, 1),
        ))

    console.print()
    valid = [labels[i] for i in range(len(choices))]
    valid_str = " / ".join(f"[bold bright_cyan]{v}[/]" for v in valid)

    while True:
        ans = Prompt.ask(
            f"[{C_GOLD}]◆ 選択してください[/{C_GOLD}] ({valid_str})"
        ).strip().upper()
        if ans in valid:
            return labels.index(ans)
        console.print(f"[bright_red]  {' か '.join(valid)} を入力してください[/]")


def render_result(result_text: str, is_good: bool = True):
    """イベント結果演出"""
    if is_good:
        icon   = "✅"
        color  = "bright_green"
        title  = f"[{C_LIME}]◆ 結果 ◆[/{C_LIME}]"
    else:
        icon   = "⚡"
        color  = "bright_red"
        title  = f"[{C_DANGER}]◆ 結果 ◆[/{C_DANGER}]"

    console.print()
    console.print(Panel(
        result_text,
        title=title,
        border_style=color,
        box=box.HEAVY,
        padding=(1, 2),
    ))
    time.sleep(0.4)


# ══════════════════════════════════════════════
# 爆弾発動（ドラマチック演出）
# ══════════════════════════════════════════════
def render_bomb_trigger(bomb_text: str):
    """爆弾発動：画面を震わせるような演出"""
    console.print()
    for _ in range(3):
        console.print(f"[bold bright_red]  {'⚡' * 20}  [/]")
        time.sleep(0.1)
        console.print("\033[1A\033[2K", end="")

    _flash_rule("  💥  過去の決断の代償が来た！  💥", color="bright_red", flashes=2)

    _advisor_bubble("bomb")
    console.print()

    console.print(Panel(
        bomb_text,
        title=f"[{C_DANGER}]  💣 BOMB TRIGGERED 💣  [/{C_DANGER}]",
        border_style="bright_red",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))
    console.print()
    time.sleep(0.8)


# ══════════════════════════════════════════════
# 監査契約ルーレット（スロット演出）
# ══════════════════════════════════════════════
def render_audit_contract_result(success: bool, message: str):
    """監査契約ルーレット演出"""
    console.print()
    _flash_rule("  🎲  監査契約ルーレット  🎲", color="magenta", flashes=1)

    # スロット回転演出
    slots = ["監査法人A","監査法人B","監査法人C","監査法人D"]
    console.print()
    console.print("  判定中", end="", style="bold")
    for i in range(12):
        console.print(f" [{random.choice(slots)}]", end="", style="dim")
        time.sleep(0.08)
        if i % 4 == 3:
            console.print("\r  判定中", end="", style="bold")
    console.print()
    console.print()

    color = "bright_green" if success else "bright_red"
    result_title = "🎊  監査契約  締結！" if success else "💔  監査契約  拒絶"

    console.print(Panel(
        message,
        title=f"[bold {color}]{result_title}[/]",
        border_style=color,
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))
    time.sleep(0.8)


# ══════════════════════════════════════════════
# 定時株主総会
# ══════════════════════════════════════════════
def render_shareholder_meeting(result: str, n_period: int):
    """定時株主総会演出"""
    console.print()
    _flash_rule("  🏢  定時株主総会  🏢", color="bright_white", flashes=1)
    label = {-3:"N-3期",-2:"N-2期（直前々期）",-1:"N-1期（直前期）",0:"N期（申請期）"}.get(n_period,"")
    console.print(Panel(
        result,
        title=f"[bold]{label} 定時株主総会[/bold]",
        border_style="bright_white",
        box=box.HEAVY,
        padding=(1, 2),
    ))
    time.sleep(0.5)


# ══════════════════════════════════════════════
# 期移行演出
# ══════════════════════════════════════════════
def render_period_transition(old_period: int, new_period: int):
    """期移行：ドラマチック演出"""
    label = {-2:"N-2期（直前々期）",-1:"N-1期（直前期）",0:"N期（申請期）"}.get(new_period,"")
    color = {-2:"bright_cyan",-1:"bright_yellow",0:"bright_red"}.get(new_period,"white")
    messages = {
        -2:"監査対象期間に突入しました。\n準金商法監査がスタートします。\n直前々期の期首から上場会社と同水準の管理体制が必要です！",
        -1:"直前期に入りました。\n2期目の監査が始まります。\n内部統制報告制度への対応も本格化します。",
        0: "申請期に入りました！\nN期Q4に東京証券取引所の上場審査が行われます。\n今まで積み上げた準備の総決算です！",
    }
    msg = messages.get(new_period, "")

    console.print()
    for i in range(3):
        spaces = " " * (i * 2)
        console.print(f"[{color}]{spaces}>>> {label} スタート <<<[/{color}]")
        time.sleep(0.15)
    console.print()

    if msg:
        console.print(Panel(
            msg,
            title=f"[bold {color}]◆ PHASE CHANGE: {label} ◆[/]",
            border_style=color,
            box=box.DOUBLE_EDGE,
            padding=(1, 2),
        ))
    time.sleep(0.6)


# ══════════════════════════════════════════════
# 東証上場審査（クライマックス）
# ══════════════════════════════════════════════
def render_tse_examination(company: Company) -> dict:
    """東証上場審査 — ゲーム最大のクライマックス演出"""
    console.clear()

    # ドラマチックオープニング
    console.print()
    _flash_rule("  ★  東京証券取引所 上場審査  ★", color="bright_red", flashes=3)
    console.print()

    opening = """\
あなたの会社の命運が決まる瞬間——

東証の審査官が資料を開きます。

これまでの全ての決断が、ここで問われます。"""

    # タイプライター演出
    for line in opening.split("\n"):
        _typewriter(line, delay=0.025, style="bold white")
    console.print()
    time.sleep(0.5)

    issues = []
    passed_items = []

    # ─── 形式要件チェック ───
    console.print(Rule(f"[bold bright_cyan]  第一審査：形式要件  [/bold bright_cyan]", style="bright_cyan"))
    console.print()
    time.sleep(0.3)

    formal_checks = [
        ("👥 株主数 150人以上",
         company.shareholder_count >= 150,
         f"現在 {company.shareholder_count}人"),
        ("🏢 時価総額 5億円以上",
         company.market_cap_million >= 500,
         f"現在 ¥{company.market_cap_million:.0f}百万円"),
        ("📋 監査契約締結済み",
         company.has_audit_contract,
         "2期間の監査証明が必要"),
        ("🏦 主幹事証券会社選定済み",
         company.has_underwriter,
         "引受契約が必要"),
    ]
    _run_check_animation(formal_checks, issues, passed_items)

    time.sleep(0.3)
    # ─── 実質審査チェック ───
    console.print()
    console.print(Rule(f"[bold bright_yellow]  第二審査：実質審査（蓄積フラグ判定）  [/bold bright_yellow]",
                       style="bright_yellow"))
    console.print()
    time.sleep(0.3)

    substance_checks = [
        ("🔍 反社会的勢力との関係",
         not company.flags.antisocial_vendor,
         "反社チェック不備が疑われます"),
        ("🏗️  内部管理体制（50以上）",
         company.internal_control_score >= 50,
         f"スコア {company.internal_control_score}"),
        ("⚖️  コンプライアンス体制（50以上）",
         company.compliance_score >= 50,
         f"スコア {company.compliance_score}"),
        ("📒 会計処理の適正性",
         not company.flags.cash_basis_accounting,
         "現金主義会計が残存"),
        ("🤝 関連当事者取引の整理",
         not company.flags.no_related_party_review,
         "関連当事者取引が未整理"),
        ("🏛️  ガバナンス体制（50以上）",
         company.governance_score >= 50,
         f"スコア {company.governance_score}"),
        ("💣 累積リスクスコア（60未満）",
         company.flags.total_risk_score < 60,
         f"現在 {company.flags.total_risk_score}（60未満が必要）"),
    ]
    _run_check_animation(substance_checks, issues, passed_items)

    time.sleep(0.8)
    passed = len(issues) == 0
    return {"passed": passed, "issues": issues, "passed_items": passed_items}


def _run_check_animation(checks, issues, passed_items):
    """審査チェックのアニメーション"""
    for label, ok, detail in checks:
        time.sleep(0.35)
        console.print(f"  [dim]審査中……[/dim] {label}", end="\r")
        time.sleep(0.4)

        if ok:
            console.print(f"  [bold bright_green]✔ PASS[/]  {label}")
            passed_items.append(label)
        else:
            console.print(f"  [bold bright_red]✘ FAIL[/]  {label}  [dim]← {detail}[/dim]")
            issues.append(f"{label} — {detail}")


# ══════════════════════════════════════════════
# エンディング
# ══════════════════════════════════════════════
def render_ending(company: Company, ending_type: str, issues: List[str]):
    """ゲームエンディング表示"""
    console.clear()
    time.sleep(0.3)

    if ending_type == "success":
        _render_ipo_success(company)
    elif ending_type == "delay":
        _render_ipo_delay(company, issues)
    elif ending_type == "bankruptcy":
        _render_bankruptcy(company)
    elif ending_type == "dismissed":
        _render_dismissed(company)

    _render_learning_feedback(company, ending_type, issues)
    console.print()
    Prompt.ask("[dim]──  Enterキーを押して終了  ──[/dim]")


def _render_ipo_success(company: Company):
    art = r"""
     *    .  *       .        *    .
   .    *        .      *         .   *
       ╔══════════════════════════════╗
  *    ║  ╔══╗  ╔══╗  ╔══╗  ╔══╗   ║   .
       ║  ║  ║  ║  ║  ║  ║  ║  ║   ║
  .    ║  ╚══╝  ╚══╝  ╚══╝  ╚══╝   ║  *
       ║          🔔  🔔  🔔        ║
  *    ╚══════════════════════════════╝
     .     *    .       *    .     *
    """
    console.print(Panel(
        Align.center(Text(
            art
            + f"\n\n🎊  上場おめでとうございます！  🎊\n"
            + f"東京証券取引所に株式が上場されました！\n\n"
            + f"[bold bright_yellow]時価総額: ¥{company.market_cap_million:,.0f}百万円[/bold bright_yellow]\n"
            + f"[bold bright_green]最終売上（今期）: ¥{company.revenue.recognized:,.0f}百万円[/bold bright_green]",
            justify="center"
        )),
        title=f"[bold bright_yellow]  {DECO_CROWN} CONGRATULATIONS! 上場成功 {DECO_CROWN}  [/]",
        border_style="bright_yellow",
        box=box.DOUBLE_EDGE,
        padding=(1, 4),
    ))


def _render_ipo_delay(company: Company, issues: List[str]):
    issue_str = "\n".join(f"  [bright_red]✘[/]  {i}" for i in issues)
    console.print(Panel(
        f"[bold bright_red]上場延期が決定しました[/bold bright_red]\n\n"
        f"東証の上場審査において以下の問題が指摘されました:\n\n"
        + issue_str +
        f"\n\n[yellow]改善後に再申請が必要です。上場は最低1年延期されます。[/yellow]",
        title=f"[bold bright_red]  ⚠  上場延期  ⚠  [/]",
        border_style="bright_red",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))


def _render_bankruptcy(company: Company):
    console.print(Panel(
        "[bold bright_red]資金がショートしました[/bold bright_red]\n\n"
        "上場前に資金が底をつき、事業継続が困難になりました。\n"
        "スポンサー企業への事業譲渡、または清算手続きが必要です。\n\n"
        "[yellow]資本政策と収益基盤の確立が上場準備の大前提でした。[/yellow]",
        title=f"[bold bright_red]  💔  GAME OVER  資金ショート  💔  [/]",
        border_style="bright_red",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))


def _render_dismissed(company: Company):
    console.print(Panel(
        "[bold bright_red]取締役会から解任通告を受けました[/bold bright_red]\n\n"
        "コンプライアンス違反や不正の発覚により\n"
        "投資家・取締役会からの信頼を完全に失いました。\n\n"
        "あなたは代表取締役を解任されました。",
        title=f"[bold bright_red]  🚫  GAME OVER  代表取締役解任  🚫  [/]",
        border_style="bright_red",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))


def _render_learning_feedback(company: Company, ending_type: str, issues: List[str]):
    """実務学習フィードバック"""
    console.print()
    _flash_rule("  📚  実務学習フィードバック  📚", color="bright_cyan", flashes=1)
    console.print()

    feedbacks = []

    if company.flags.unpaid_overtime:
        feedbacks.append((
            "⏰ 労務管理",
            "未払残業代を放置したため上場直前に引当金計上が発生しました。\n"
            "元従業員からの労基署申告は上場直前に起きるケースが多く、\n"
            "利益計画の大幅修正を余儀なくされます。\n"
            "N-3期から勤怠管理システムを整備すべきでした。"
        ))
    if company.flags.antisocial_vendor:
        feedbacks.append((
            "🔍 反社チェック",
            "取引先の審査を怠ったため主幹事証券会社から上場延期を通告されました。\n"
            "主幹事証券会社は全取引先の反社チェックを必ず実施します。\n"
            "コスト削減より安全審査を優先する文化が必要でした。"
        ))
    if company.flags.no_job_separation:
        feedbacks.append((
            "🔒 職務分掌",
            "出納と記帳の分離が未実施のため横領リスクが高い状態が続きました。\n"
            "職務分掌は内部統制の基本中の基本です。\n"
            "1人に集中させることはガバナンス上の重大な欠陥と判断されます。"
        ))
    if company.flags.cash_basis_accounting:
        feedbacks.append((
            "📒 収益認識",
            "現金主義会計から発生主義への移行が未完了でした。\n"
            "全上場会社は収益認識会計基準（ASBJ）に従う義務があります。\n"
            "N-3期から移行に着手しないとN-2期の監査開始時に大混乱が生じます。"
        ))
    if company.flags.no_inventory_count:
        feedbacks.append((
            "📦 棚卸管理",
            "実地棚卸の整備が不十分でした。\n"
            "棚卸資産が重要な業種では監査法人の棚卸立会は必須です。\n"
            "立会ができない場合「監査範囲の制約」となり監査意見を表明できず、\n"
            "遡及監査が不可能となってIPOスケジュールに重大な支障が生じます。"
        ))
    if not company.flags.short_review_done:
        feedbacks.append((
            "🔍 ショートレビュー",
            "実施しなかったため潜在リスクが可視化されませんでした。\n"
            "ショートレビューはIPO準備の設計図です。\n"
            "N-3期に実施することでN-2期の監査開始前に課題を整理できます。\n"
            "省いたコスト以上の損失が後から生じるケースがほとんどです。"
        ))
    if company.flags.audit_contract_rejected:
        feedbacks.append((
            "📋 監査契約",
            "監査法人に受嘱を拒絶されました。\n"
            "監査法人は内部管理体制が整っていない会社の監査を引き受けません。\n"
            "N-2期（直前々期）の期首までに受入体制を整えることが絶対条件です。"
        ))

    if not feedbacks:
        feedbacks.append((
            "🎊 総評",
            "素晴らしい判断の連続でした！\n"
            "コンプライアンスを優先し早期に体制整備を行った結果、\n"
            "スムーズなIPOを実現できました。\n"
            "IPO準備の鉄則：「短期コスト削減 ＜ 長期リスク管理」"
        ))

    for i, (title, body) in enumerate(feedbacks, 1):
        console.print(Panel(
            body,
            title=f"[bold bright_cyan]  📖 教訓{i}：{title}  [/]",
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(0, 2),
        ))

    # 最終スコア表
    console.print()
    summary = Table(
        title=f"[{C_GOLD}]◆ 最終スコアサマリー ◆[/{C_GOLD}]",
        box=box.DOUBLE_EDGE, title_style="bold", show_header=True,
        header_style="bold dim"
    )
    summary.add_column("カテゴリ", style="bold")
    summary.add_column("スコア", justify="center")
    summary.add_column("評価", justify="center")
    summary.add_column("バー", justify="left")

    def grade(s):
        return ("S","bright_yellow") if s>=90 else \
               ("A","bright_green")  if s>=75 else \
               ("B","bright_cyan")   if s>=60 else \
               ("C","yellow")        if s>=40 else \
               ("D","bright_red")
    for label, score in [
        ("内部管理体制", company.internal_control_score),
        ("コンプライアンス", company.compliance_score),
        ("会計品質", company.accounting_quality),
        ("ガバナンス", company.governance_score),
        ("監査法人信頼", company.auditor_trust),
        ("投資家信頼", company.investor_trust),
    ]:
        g, gc = grade(score)
        summary.add_row(label, str(score), f"[bold {gc}]{g}[/]", _hp_bar(score))
    console.print(summary)


# ══════════════════════════════════════════════
# タイトル・設定画面
# ══════════════════════════════════════════════
def render_title():
    console.clear()
    title_art = r"""
  ████████╗██╗  ██╗███████╗    ██╗██████╗  ██████╗
     ██╔══╝██║  ██║██╔════╝    ██║██╔══██╗██╔═══██╗
     ██║   ███████║█████╗      ██║██████╔╝██║   ██║
     ██║   ██╔══██║██╔══╝      ██║██╔═══╝ ██║   ██║
     ██║   ██║  ██║███████╗    ██║██║     ╚██████╔╝
     ╚═╝   ╚═╝  ╚═╝╚══════╝   ╚═╝╚═╝      ╚═════╝
          P  A  T  H  :  栄 光 へ の 決 断
    """
    console.print(Panel(
        Align.center(Text(
            title_art
            + "\n〜 IPO準備の知識を、実践の決断を通じて学ぶ経営シミュレーション 〜\n\n"
            + "上場審査・監査・内部統制・資本政策……\n"
            + "あなたの会社を東証に上場させることができるか？",
            justify="center", style="bold bright_cyan"
        )),
        border_style="bright_cyan",
        box=box.DOUBLE_EDGE,
        padding=(1, 4),
    ))
    console.print()


def render_business_type_selection() -> int:
    from engine.finance import BUSINESS_PARAMS
    from models.company import BusinessType

    console.print(Panel(
        "[bold bright_cyan]◆ 事業の種類を選択してください ◆[/bold bright_cyan]\n"
        "[dim]業種によって初期資金・成長率・リスクが異なります[/dim]",
        border_style="bright_cyan", box=box.DOUBLE_EDGE
    ))

    labels = ["A","B","C","D"]
    for i, (btype, params) in enumerate(BUSINESS_PARAMS.items()):
        console.print(Panel(
            f"[bold bright_cyan][{labels[i]}][/bold bright_cyan]  [bold]{btype.value}[/bold]\n"
            f"  {params['description']}\n"
            f"  [dim]初期キャッシュ: ¥{params['initial_cash']:.0f}M  "
            f"| 成長率/Q: {params['growth_rate']:.0%}  "
            f"| バーン/Q: ¥{params['burn_rate']:.0f}M[/dim]",
            border_style="bright_blue", box=box.ROUNDED, padding=(0,2)
        ))

    valid = labels[:len(BUSINESS_PARAMS)]
    while True:
        ans = Prompt.ask(
            f"[{C_GOLD}]◆ 選択してください (A / B / C / D)[/{C_GOLD}]"
        ).strip().upper()
        if ans in valid:
            return valid.index(ans)
        console.print(f"[bright_red]  A / B / C / D を入力してください[/]")


def render_company_name_input() -> str:
    console.print()
    return Prompt.ask(
        f"[{C_GOLD}]◆ あなたの会社名を入力してください[/{C_GOLD}]",
        default="テック株式会社"
    )


def press_enter_to_continue(msg: str = "次のターンへ進む"):
    console.print()
    Prompt.ask(f"[dim]── Enter で{msg} ──[/dim]")
