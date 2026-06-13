"""
The IPO Path: 栄光への決断 — Web版
Flask + 純粋なHTML/CSS/JS でブラウザ上で動くRPGゲーム
"""
from __future__ import annotations
import sys
import os
import uuid
import html as html_module
import webbrowser
import threading
import time
from typing import Optional, List

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, jsonify, send_file

from models.company import Company, BusinessType
from engine.timeline import Timeline, N_PERIOD
from engine.finance import (
    initialize_company,
    advance_quarter_financials,
    check_cash_crisis,
    BUSINESS_PARAMS,
    market_multiplier,
    effective_growth_rate,
)
from engine.roulette import tick_bombs, audit_contract_roulette, roll
from scenario.ipo_knowledge import get_available_events, get_fresh_events, shareholder_meeting_event, create_agm_event, SALES_GROWTH_DESCRIPTIONS
from scenario.world_events import get_fresh_world_events, roll_world_event
from scenario.exam_questions import EXAM_QUESTIONS
from models.events import Choice, GameEvent


# ══════════════════════════════════════════════
# Gemini AI ナラティブエンジン（オプション）
# ══════════════════════════════════════════════
import os as _os
import re as _re
_GEMINI_AVAILABLE = False
_gemini_clients: list = []          # [genai.Client, ...]  キーごとのクライアント
_gemini_keys: list = []             # ["AIza...", ...]      生キー（プレフィクス表示用）
_gemini_active_idx: int = 0         # 現在使用中のキーindex
_gemini_key_backoffs: list = []     # [float, ...]          各キーの解禁UNIX時刻
_gemini_narrative_cache: dict = {}  # sid → (turn_key, text)
_GEMINI_MODEL = "gemini-2.5-flash-lite"   # 後継モデル（15 RPM / 1000 RPD / 1M context）
_GEMINI_INIT_REASON = ""            # 初期化失敗理由（デバッグ用）
_gemini_last_call_time: float = 0.0          # 後方互換用（未使用）
_GEMINI_MIN_INTERVAL: float = 8.0            # 同一コンテキストの最小間隔（秒）
_gemini_last_call_by_ctx: dict = {}          # コンテキスト別 最終呼び出し時刻
_GEMINI_BACKOFF_SECS: float = 1800.0      # RPM超過時のバックオフ（30分）
_GEMINI_BACKOFF_DAILY: float = 6 * 3600.0 # RPD超過時のバックオフ（暫定値、実際は翌UTC0時まで）

def _next_utc_midnight() -> float:
    """次のUTC深夜0時（= 日本時間 翌朝09:00）のUNIX時刻を返す。
    Googleの無料枠クォータはUTC日付でリセットされる。"""
    import time as _t, datetime as _dt
    now_utc = _dt.datetime.utcnow()
    next_midnight = (now_utc + _dt.timedelta(days=1)).replace(
        hour=0, minute=5, second=0, microsecond=0)   # 5分余裕
    # UTC datetimeをUNIX時刻に変換
    epoch = _dt.datetime(1970, 1, 1)
    return (next_midnight - epoch).total_seconds()
_GEMINI_BACKOFF_FILE = _os.path.join(_os.path.dirname(__file__), "gemini_backoff.json")

def _key_id(key: str) -> str:
    """キー識別子（先頭8文字 + 末尾4文字）。バックオフJSONのキーに使う"""
    return f"{key[:8]}…{key[-4:]}" if len(key) > 12 else key

def _save_gemini_backoff():
    """全キーのバックオフ状態をJSONで保存"""
    try:
        import json as _json
        data = {_key_id(_gemini_keys[i]): _gemini_key_backoffs[i]
                for i in range(len(_gemini_keys))
                if _gemini_key_backoffs[i] > 0}
        with open(_GEMINI_BACKOFF_FILE, "w") as f:
            _json.dump(data, f)
    except Exception:
        pass

def _load_gemini_backoffs(keys: list) -> list:
    """ファイルから各キーのバックオフ状態を読み込む（無ければ全0.0）"""
    backoffs = [0.0] * len(keys)
    try:
        import json as _json
        if _os.path.exists(_GEMINI_BACKOFF_FILE):
            data = _json.load(open(_GEMINI_BACKOFF_FILE))
            import time as _t
            now = _t.time()
            for i, k in enumerate(keys):
                v = data.get(_key_id(k), 0.0)
                if v > now:
                    backoffs[i] = v
    except Exception:
        pass
    return backoffs

def _load_api_keys() -> list:
    """APIキーをリストで返す（gemini_api_key.txt を1行1キーで複数対応）"""
    keys: list = []
    # 1. 環境変数（カンマ区切り対応）
    env_val = _os.environ.get("GEMINI_API_KEY", "").strip()
    if env_val:
        for k in env_val.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
        if keys:
            print(f"  [INFO] APIキー取得元: 環境変数 GEMINI_API_KEY ({len(keys)}本)")
            return keys
    # 2. gemini_api_key.txt（1行1キー、空行・#コメント無視）
    key_file = _os.path.join(_os.path.dirname(__file__), "gemini_api_key.txt")
    if _os.path.exists(key_file):
        try:
            for line in open(key_file, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line not in keys:
                    keys.append(line)
            if keys:
                print(f"  [INFO] APIキー取得元: gemini_api_key.txt ({len(keys)}本)")
                return keys
        except Exception:
            pass
    return []


def _init_gemini():
    global _GEMINI_AVAILABLE, _gemini_clients, _gemini_keys
    global _gemini_key_backoffs, _gemini_active_idx, _GEMINI_INIT_REASON
    keys = _load_api_keys()
    if not keys:
        _GEMINI_INIT_REASON = "APIキー未設定（環境変数 or gemini_api_key.txt）"
        print("  [INFO] GEMINI_API_KEY not set -> using rule-based narrative")
        print("  [INFO] 解決方法: gemini_api_key.txt に1行1キーで貼り付けてください")
        return
    try:
        from google import genai
    except ImportError as e:
        _GEMINI_INIT_REASON = f"パッケージ未インストール: {e}"
        print(f"  [WARN] google-genai not installed: {e}")
        print("  [WARN] -> pip install google-genai  を実行してください")
        return
    for k in keys:
        try:
            client = genai.Client(api_key=k)
            _gemini_clients.append(client)
            _gemini_keys.append(k)
            print(f"  [INFO] Key registered: {_key_id(k)} (len={len(k)})")
        except Exception as e:
            print(f"  [WARN] Key {_key_id(k)} init failed: {e}")
    if not _gemini_clients:
        _GEMINI_INIT_REASON = "全キーの初期化失敗"
        return
    # バックオフ状態を復元
    _gemini_key_backoffs = _load_gemini_backoffs(_gemini_keys)
    import time as _t
    now = _t.time()
    # 利用可能な最初のキーをactiveに
    _gemini_active_idx = 0
    for i, b in enumerate(_gemini_key_backoffs):
        if b <= now:
            _gemini_active_idx = i
            break
    _GEMINI_AVAILABLE = True
    _GEMINI_INIT_REASON = "OK"
    print(f"  [OK] Gemini AI engine started (model: {_GEMINI_MODEL}, keys: {len(_gemini_clients)}, active: #{_gemini_active_idx+1})")
    # バックオフ中のキーがあれば通知
    for i, b in enumerate(_gemini_key_backoffs):
        if b > now:
            rem = int((b - now) // 60)
            print(f"  [INFO] Key #{i+1} ({_key_id(_gemini_keys[i])}) backoff: {rem}分後解禁")

def _get_active_client():
    """現在使用すべきクライアントを返す。全キー枯渇なら None"""
    import time as _t
    now = _t.time()
    n = len(_gemini_clients)
    if n == 0:
        return None, -1
    # active_idxから順に空いているキーを探す
    for offset in range(n):
        idx = (_gemini_active_idx + offset) % n
        if _gemini_key_backoffs[idx] <= now:
            return _gemini_clients[idx], idx
    return None, -1   # 全キー枯渇

def _mark_key_backoff(idx: int, secs: float):
    """指定キーをバックオフ状態にし、次の利用可能キーへ切替"""
    global _gemini_active_idx
    import time as _t
    if 0 <= idx < len(_gemini_key_backoffs):
        _gemini_key_backoffs[idx] = _t.time() + secs
        _save_gemini_backoff()
    # 次の利用可能なキーを探す
    n = len(_gemini_clients)
    now = _t.time()
    for offset in range(1, n + 1):
        nxt = (idx + offset) % n
        if _gemini_key_backoffs[nxt] <= now:
            _gemini_active_idx = nxt
            print(f"  [AI] Switched to key #{nxt+1} ({_key_id(_gemini_keys[nxt])})")
            return

_init_gemini()


# ══════════════════════════════════════════════
# セーブ・ロードシステム
# ══════════════════════════════════════════════
def _resolve_save_path() -> str:
    """セーブファイルのパスを決定。複数候補を試して書き込み可能なディレクトリを選ぶ。"""
    import tempfile
    candidates = []
    # 1) スクリプトと同じディレクトリ
    try:
        candidates.append(_os.path.dirname(_os.path.abspath(__file__)))
    except Exception:
        pass
    # 2) ユーザーホーム配下の専用フォルダ
    try:
        candidates.append(_os.path.join(_os.path.expanduser("~"), ".ipo_game"))
    except Exception:
        pass
    # 3) 一時フォルダ（最後の砦）
    candidates.append(_os.path.join(tempfile.gettempdir(), "ipo_game"))

    for d in candidates:
        if not d:
            continue
        try:
            _os.makedirs(d, exist_ok=True)
            # 書き込みテスト
            test_path = _os.path.join(d, ".write_test")
            with open(test_path, "wb") as f:
                f.write(b"ok")
            _os.remove(test_path)
            return _os.path.join(d, "savegame.dat")
        except Exception:
            continue
    # フォールバック（CWD）
    return "savegame.dat"

_SAVE_PATH = _resolve_save_path()
_SAVE_DIR  = _os.path.dirname(_SAVE_PATH) or "."
print(f"  [INIT] Save path: {_SAVE_PATH}")

def _save_game(session: "GameSession") -> tuple:
    """ターン終了時にゲーム状態をファイル保存 + Base64文字列を返す。
    Returns: (success: bool, error_msg: str, save_b64: str)
    save_b64 はクライアントの localStorage に渡して持たせるデータ。
    ファイル保存が失敗してもBase64生成が成功すればsuccess=Trueとする。"""
    import dill, io, base64
    try:
        session._queue = []   # レンダリングキューは不要
        # ── 1) メモリ上でシリアライズ（Base64生成 ＋ ファイル保存両用） ──
        buf = io.BytesIO()
        dill.dump(session, buf, protocol=2)
        raw = buf.getvalue()
        save_b64 = base64.b64encode(raw).decode("ascii")

        # ── 2) サーバー側ファイルにも保存（失敗しても続行） ──
        try:
            save_dir = _os.path.dirname(_SAVE_PATH) or "."
            _os.makedirs(save_dir, exist_ok=True)
            tmp_path = _SAVE_PATH + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(raw)
                f.flush()
                try:
                    _os.fsync(f.fileno())
                except Exception:
                    pass
            _os.replace(tmp_path, _SAVE_PATH)
            print(f"  [SAVE] Saved to {_SAVE_PATH} ({len(raw)} bytes)")
        except Exception as fe:
            print(f"  [WARN] File save failed (localStorage save still OK): {fe}")

        return True, "", save_b64
    except Exception as e:
        import traceback
        msg = f"{type(e).__name__}: {e}"
        print(f"  [WARN] Save failed: {traceback.format_exc()}")
        return False, msg, ""

def _load_game(save_b64: str = "") -> Optional["GameSession"]:
    """セーブデータを復元する。
    save_b64 が渡された場合はそちらを優先（localStorage経由）。
    なければサーバー側のファイルから読む。失敗時はNoneを返す。"""
    import dill, io
    # ── 1) localStorage経由のBase64データを優先 ──
    if save_b64:
        try:
            import base64
            raw = base64.b64decode(save_b64)
            session = dill.loads(raw)
            print(f"  [LOAD] Restored from localStorage Base64 ({len(raw)} bytes)")
            return session
        except Exception as e:
            print(f"  [WARN] localStorage load failed, falling back to file: {e}")

    # ── 2) サーバー側ファイルから読む ──
    if not _os.path.exists(_SAVE_PATH):
        return None
    try:
        with open(_SAVE_PATH, "rb") as f:
            session = dill.load(f)
        print(f"  [LOAD] Restored from file: {_SAVE_PATH}")
        return session
    except Exception as e:
        print(f"  [WARN] File load failed: {e}")
        return None

def _has_save() -> bool:
    return _os.path.exists(_SAVE_PATH)

def _delete_save():
    try:
        if _os.path.exists(_SAVE_PATH):
            _os.remove(_SAVE_PATH)
    except Exception as e:
        print(f"  [WARN] Delete save failed: {e}")


app = Flask(__name__, template_folder="templates_web")
app.secret_key = "ipo-path-2025"

# セッション管理 (session_id → GameSession)
SESSIONS: dict[str, "GameSession"] = {}


# ══════════════════════════════════════════════
# AI突発イベントシステム
# ── 毎ゲーム異なるシナリオをGeminiが生成し、リプレイ性を高める ──
# ══════════════════════════════════════════════
import random as _rand

def _mk_effect(cash=0.0, burn=0.0, ic=0, comp=0, gov=0, at=0, it=0,
               morale=0, risk=0, rev_growth=0.0, mktcap_mul=1.0, msg=""):
    """ゲームパラメータへの影響を関数として生成するファクトリ"""
    def fn(c: "Company") -> str:
        if cash:      c.cash = max(0.0, c.cash + cash)
        if burn:      c.quarterly_burn = max(1.0, c.quarterly_burn + burn)
        def _dr(v, cur):
            if v <= 0: return max(0, min(100, cur + v))
            if cur >= 90: return min(100, cur + max(1, round(v * 0.25)))
            if cur >= 80: return min(100, cur + max(1, round(v * 0.5)))
            return min(100, cur + v)
        if ic:        c.internal_control_score  = _dr(ic,    c.internal_control_score)
        if comp:      c.compliance_score         = _dr(comp,  c.compliance_score)
        if gov:       c.governance_score         = _dr(gov,   c.governance_score)
        if at:        c.auditor_trust            = _dr(at,    c.auditor_trust)
        if it:        c.investor_trust           = _dr(it,    c.investor_trust)
        if morale:    c.employee_morale          = _dr(morale, c.employee_morale)
        if risk:      c.flags.total_risk_score   = max(0, c.flags.total_risk_score + risk)
        if rev_growth: c.revenue.growth_rate     = max(0.0, c.revenue.growth_rate + rev_growth)
        if mktcap_mul != 1.0:
            c.market_cap_million = max(100.0, c.market_cap_million * mktcap_mul)
        return msg
    return fn


# 12種類の突発クライシステンプレート
# effect_a = 対処する（コスト大・リスク回避）
# effect_b = 先送り/妥協（コスト小・将来リスク）
CRISIS_TEMPLATES = [
    {
        "id":      "cto_poached",
        "topic":   "技術責任者（CTO）が競合他社に引き抜かれようとしている",
        "hint_a":  "緊急引き止め交渉＋代替採用（コスト高・技術力維持）",
        "hint_b":  "退職を受け入れる（コスト低・組織動揺・上場審査への技術力懸念）",
        "effect_a": _mk_effect(cash=-20.0, ic=5,  morale=-5,  risk=5,
                               msg="✅ CTO引き止め・後継者採用に成功。¥20M発生。技術力を維持しました。"),
        "effect_b": _mk_effect(morale=-25, it=-10, risk=15,
                               msg="⚠️ CTOが離脱。組織の技術力・士気が低下。投資家も不安視。"),
        "min_period": -2, "max_period": -1,
    },
    {
        "id":      "major_client_churn",
        "topic":   "売上の30%を占める最大顧客が突然の解約を申し入れてきた",
        "hint_a":  "代替顧客開拓費用投下＋解約交渉（コスト高・売上維持）",
        "hint_b":  "解約を受け入れ自然体制（売上激減・投資家信頼喪失）",
        "effect_a": _mk_effect(cash=-15.0, rev_growth=-0.02, it=5,
                               msg="✅ 代替顧客開拓に着手。¥15M投入。売上への影響を最小化します。"),
        "effect_b": _mk_effect(rev_growth=-0.08, it=-15, risk=12, mktcap_mul=0.92,
                               msg="⚠️ 最大顧客が離脱。売上が急減し、投資家信頼も大幅低下。"),
        "min_period": -3, "max_period": 0,
    },
    {
        "id":      "cyber_attack",
        "topic":   "社内システムへのランサムウェア攻撃が発生し、業務が停止している",
        "hint_a":  "専門対応チーム投入＋セキュリティ強化（コスト高・信頼確保）",
        "hint_b":  "身代金支払いを検討・情報隠蔽（コスト抑制・コンプライアンス違反リスク）",
        "effect_a": _mk_effect(cash=-12.0, ic=10, comp=8, risk=5,
                               msg="✅ サイバーセキュリティ専門家を投入。¥12M発生。内部統制+10。"),
        "effect_b": _mk_effect(cash=-3.0,  comp=-15, risk=25, at=-10,
                               msg="⚠️ 対応を誤りました。コンプライアンス-15 / リスク+25 / 監査信頼-10。"),
        "min_period": -2, "max_period": 0,
    },
    {
        "id":      "sns_scandal",
        "topic":   "元社員がSNSで「未払残業・パワハラ」を告発し、拡散している",
        "hint_a":  "外部調査委員会を設置し誠実に対応（コスト中・信頼確保）",
        "hint_b":  "沈黙・法的対処で封じ込め（コスト低・炎上継続リスク）",
        "effect_a": _mk_effect(cash=-8.0, comp=12, it=5, morale=8, risk=-5,
                               msg="✅ 外部調査委員会を設置・誠実に対応。¥8M発生。コンプラ+12。"),
        "effect_b": _mk_effect(comp=-8, it=-18, risk=20, morale=-15,
                               msg="⚠️ 沈黙が火に油を注ぎました。炎上継続・投資家信頼-18。"),
        "min_period": -2, "max_period": 0,
    },
    {
        "id":      "regulatory_tightening",
        "topic":   "監督官庁が業界規制を大幅に強化する政令を突然発表した",
        "hint_a":  "規制対応チームを組成し先行対応（コスト高・上場審査での信頼）",
        "hint_b":  "様子見・後回し（コスト低・規制違反リスク蓄積）",
        "effect_a": _mk_effect(cash=-10.0, comp=18, risk=-8, it=8,
                               msg="✅ 規制対応チームを先行組成。¥10M発生。コンプラ+18。"),
        "effect_b": _mk_effect(comp=-10, risk=20, it=-5,
                               msg="⚠️ 様子見の間に規制違反リスクが蓄積。コンプラ-10 / リスク+20。"),
        "min_period": -3, "max_period": 0,
    },
    {
        "id":      "competitor_ipo",
        "topic":   "最大の競合他社が先にIPO申請を発表し、業界の注目が集まっている",
        "hint_a":  "差別化PR・機関投資家向け説明会を強化（コスト中・投資家信頼上昇）",
        "hint_b":  "静観する（投資家不安・時価総額評価下落）",
        "effect_a": _mk_effect(cash=-6.0, it=12, mktcap_mul=1.04,
                               msg="✅ 差別化PR・機関投資家説明会を強化。¥6M発生。投資家信頼+12。"),
        "effect_b": _mk_effect(it=-12, mktcap_mul=0.93,
                               msg="⚠️ 静観した結果、投資家が競合に流れました。時価総額-7%。"),
        "min_period": -2, "max_period": 0,
    },
    {
        "id":      "tax_audit",
        "topic":   "税務署から突然の税務調査の通知が届いた",
        "hint_a":  "税理士・顧問弁護士を即時投入し正面から対応（コスト中・リスク解消）",
        "hint_b":  "自社対応で乗り切ろうとする（コスト低・追徴リスク・監査影響）",
        "effect_a": _mk_effect(cash=-8.0, risk=-10, at=8,
                               msg="✅ 税理士・弁護士チームで適正対応。¥8M発生。リスク-10。"),
        "effect_b": _mk_effect(risk=22, at=-12, comp=-5,
                               msg="⚠️ 自社対応が裏目に。追徴リスク・監査法人の不信感増大。"),
        "min_period": -3, "max_period": -1,
    },
    {
        "id":      "vc_demands",
        "topic":   "主要VCから「追加出資の条件として取締役追加・優先配当強化」を要求された",
        "hint_a":  "条件を精査し一部受け入れ・交渉（ガバナンス整備、創業者持分への影響最小化）",
        "hint_b":  "要求を全面拒否（資金調達失敗リスク・VC関係悪化）",
        "effect_a": _mk_effect(cash=30.0, gov=8, it=5, risk=5,
                               msg="✅ VCとの交渉で一部合意。資金+¥30M調達。ガバナンス+8。"),
        "effect_b": _mk_effect(it=-15, risk=10, mktcap_mul=0.95,
                               msg="⚠️ VCが撤退。資金調達失敗・投資家信頼-15 / 時価総額-5%。"),
        "min_period": -3, "max_period": -1,
    },
    {
        "id":      "ipo_market_freeze",
        "topic":   "株式市場が急落し、証券会社から「IPO市況が急激に冷え込んでいる。申請時期の見直しを検討すべきでは」と連絡が入った",
        "hint_a":  "上場を1年延期し、体制整備に専念する（市況回復後・同四半期から再開）",
        "hint_b":  "強行突破でスケジュールを維持する（市況悪化の中での低公開価格リスク）",
        "effect_a": _mk_effect(it=8, mktcap_mul=0.97,
                               msg="── 1年後、同四半期 ──\n\n"
                                   "   市場環境が落ち着きを取り戻しました。\n"
                                   "   この1年間で内部管理体制・財務基盤をさらに磨き上げ、\n"
                                   "   改めて上場準備を本格化させます。\n"
                                   "   ▶ 投資家信頼+8（冷静な延期判断が長期的な信頼につながりました）"),
        "effect_b": _mk_effect(mktcap_mul=0.72, it=-22, morale=-18, risk=22,
                               msg="⚠️ 市況急落下での強行を決断。\n"
                                   "   時価総額-28% / 投資家信頼-22 / 士気-18 / リスク+22\n"
                                   "   証券会社から「公開価格が著しく低下する可能性があります」と警告が届いている。\n"
                                   "   機関投資家の需要が大幅に冷え込んでおり、上場審査通過は極めて困難な状況です。"),
        "min_period": -1, "max_period": 0,
        "macro_shock": True, "shock_name": "市場急落", "pass_prob": 0.28,
        "fail_reason": "株式市場の急激な冷え込みにより公開価格が著しく低下し、引受証券会社からの推薦が取り下げられました",
    },
    {
        "id":      "data_leak",
        "topic":   "顧客の個人情報が外部に漏洩した可能性があるとの報告が上がった",
        "hint_a":  "即時情報開示・被害対応・再発防止策（コスト高・信頼確保）",
        "hint_b":  "内部調査のみで公表せず隠蔽（コスト低・発覚時に致命的打撃）",
        "effect_a": _mk_effect(cash=-12.0, comp=10, ic=8, risk=-5, it=3,
                               msg="✅ 即時開示・被害補償・再発防止を完遂。¥12M発生。コンプラ+10。"),
        "effect_b": _mk_effect(comp=-20, risk=30, it=-20, at=-15,
                               msg="💣 隠蔽が後に発覚。コンプラ-20 / リスク+30 / 投資家・監査信頼が崩壊。"),
        "min_period": -2, "max_period": 0,
    },
    {
        "id":      "patent_lawsuit",
        "topic":   "競合他社から「特許侵害」の訴訟を起こされた",
        "hint_a":  "弁護士チームを投入・和解交渉（コスト高・早期解決）",
        "hint_b":  "徹底抗戦・長期訴訟（コスト中・上場審査への影響大）",
        "effect_a": _mk_effect(cash=-15.0, risk=-12, it=5,
                               msg="✅ 弁護士チームで早期和解。¥15M発生。リスク-12。"),
        "effect_b": _mk_effect(risk=18, it=-8, comp=-5,
                               msg="⚠️ 長期訴訟が上場審査の重大リスクに。リスク+18。"),
        "min_period": -2, "max_period": 0,
    },
    {
        "id":      "mass_resignation",
        "topic":   "中核エンジニアチーム5名が集団退職を表明してきた",
        "hint_a":  "給与改善＋ストックオプション付与で引き止め（コスト中・組織維持）",
        "hint_b":  "退職を受け入れ外注で補填（組織力低下・開発スピード激減）",
        "effect_a": _mk_effect(burn=3.0, morale=12, ic=5, risk=3,
                               msg="✅ SO付与・給与改善で5名を引き止め。費用¥3M/Q増。士気+12。"),
        "effect_b": _mk_effect(morale=-22, ic=-10, it=-8, risk=12,
                               msg="⚠️ コアチームが離散。組織力・内部統制スコアが急落。"),
        "min_period": -2, "max_period": 0,
    },
]

# ── マクロショックテンプレート ──
# 通常クライシスとは別枠。N-1期〜N期に最大1件がランダム発火。
# effect_a = 上場延期（案ア：延期エンディング）、effect_b = 強行（TSE審査で確率判定）
MACRO_SHOCK_TEMPLATES = [
    {
        "id": "macro_pandemic",
        "topic": "新型感染症の世界的パンデミックが発生。政府が緊急事態宣言を発令し、経済活動が大幅に制限されている",
        "hint_a": "上場を自主延期し、事業継続と従業員の安全を最優先する",
        "hint_b": "パンデミック下でも上場スケジュールを維持する（審査通過は極めて困難）",
        "effect_a": _mk_effect(it=5, morale=10,
                               msg="📅 パンデミックの影響を受け、上場を自主延期する決断を下しました。\n\n"
                                   "   従業員の安全と事業継続を最優先とし、\n"
                                   "   市場環境の回復を見据えた体制再構築に専念します。\n"
                                   "   ▶ 投資家信頼+5・士気+10（冷静な判断が評価されました）"),
        "effect_b": _mk_effect(mktcap_mul=0.70, it=-15, morale=-20, risk=20,
                               msg="⚠️ パンデミック下での上場強行を決断。\n"
                                   "   時価総額-30% / 投資家信頼-15 / 士気-20 / リスク+20\n"
                                   "   市場環境の急激な悪化により、上場審査の通過は極めて困難です。"),
        "min_period": -1, "max_period": 0,
        "macro_shock": True, "shock_name": "パンデミック", "pass_prob": 0.20,
        "fail_reason": "感染症拡大の影響により売上の回復が見込めず、事業継続性の審査基準を満たせませんでした",
    },
    {
        "id": "macro_financial_crisis",
        "topic": "世界的な金融危機が発生。株式市場が暴落し、IPO市場が事実上凍結状態に陥っている",
        "hint_a": "上場を自主延期し、財務基盤の強化と市場回復を待つ",
        "hint_b": "金融危機の中でも上場を強行する（審査通過は極めて困難）",
        "effect_a": _mk_effect(it=5, mktcap_mul=0.90,
                               msg="📅 金融危機の影響を受け、上場を自主延期する決断を下しました。\n\n"
                                   "   市場が回復するまで財務基盤の強化に注力し、\n"
                                   "   より良い条件での上場を目指します。\n"
                                   "   ▶ 投資家信頼+5（市場環境を冷静に判断した点が評価）"),
        "effect_b": _mk_effect(mktcap_mul=0.65, it=-20, risk=25,
                               msg="⚠️ 金融危機下での上場強行を決断。\n"
                                   "   時価総額-35% / 投資家信頼-20 / リスク+25\n"
                                   "   IPO市場の凍結状態で、引受証券会社も推薦を躊躇しています。"),
        "min_period": -1, "max_period": 0,
        "macro_shock": True, "shock_name": "金融危機", "pass_prob": 0.20,
        "fail_reason": "金融市場の混乱によりIPO市場が事実上凍結。引受証券会社からの推薦取り下げを受けました",
    },
    {
        "id": "macro_geopolitical",
        "topic": "大規模な地政学リスクが顕在化。主要取引先の国際サプライチェーンが断絶し、原材料調達・物流に深刻な影響が出ている",
        "hint_a": "上場を自主延期し、サプライチェーン再構築に専念する",
        "hint_b": "地政学リスクの中でも上場スケジュールを維持する（審査通過は困難）",
        "effect_a": _mk_effect(it=3, risk=-5,
                               msg="📅 地政学リスクの影響を受け、上場を自主延期する決断を下しました。\n\n"
                                   "   サプライチェーンの再構築と事業基盤の安定化を優先し、\n"
                                   "   リスク要因の解消後に改めて上場を目指します。\n"
                                   "   ▶ 投資家信頼+3・リスク-5"),
        "effect_b": _mk_effect(mktcap_mul=0.80, it=-12, risk=18, rev_growth=-0.05,
                               msg="⚠️ 地政学リスク下での上場強行を決断。\n"
                                   "   時価総額-20% / 投資家信頼-12 / リスク+18\n"
                                   "   サプライチェーン断絶の長期化が懸念されています。"),
        "min_period": -1, "max_period": 0,
        "macro_shock": True, "shock_name": "地政学リスク", "pass_prob": 0.40,
        "fail_reason": "地政学リスクによるサプライチェーン断絶が業績に深刻な影響を与え、収益性要件を充足できませんでした",
    },
    {
        "id": "macro_earthquake",
        "topic": "大規模地震が発生し、本社・主要拠点が被災。事業継続計画（BCP）の発動を余儀なくされている",
        "hint_a": "上場を自主延期し、被災からの復旧と従業員支援を最優先する",
        "hint_b": "復旧と並行して上場スケジュールを維持する（審査通過は困難）",
        "effect_a": _mk_effect(morale=8, it=3,
                               msg="📅 大規模災害の影響を受け、上場を自主延期する決断を下しました。\n\n"
                                   "   従業員と地域社会の支援・事業復旧を最優先とし、\n"
                                   "   体制が整い次第、改めて上場準備を再開します。\n"
                                   "   ▶ 士気+8・投資家信頼+3（人命最優先の判断が評価）"),
        "effect_b": _mk_effect(mktcap_mul=0.75, morale=-25, it=-10, risk=20, cash=-30.0,
                               msg="⚠️ 被災下での上場強行を決断。\n"
                                   "   復旧費用¥30M / 時価総額-25% / 士気-25 / リスク+20\n"
                                   "   従業員からは「社員より上場が大事なのか」との声が上がっています。"),
        "min_period": -1, "max_period": 0,
        "macro_shock": True, "shock_name": "大規模災害", "pass_prob": 0.40,
        "fail_reason": "自然災害による事業拠点被災・売上減少から回復できず、上場審査での事業継続性説明が困難でした",
    },
]


# ══════════════════════════════════════════════
# HTML 生成ヘルパー
# ══════════════════════════════════════════════
def esc(text) -> str:
    return html_module.escape(str(text))


# ──────────────────────────────────────────
# 🗺 ワールドマップ（すごろく盤面）
#   16ターン（4期×4Q）を26マスに割り付け、各四半期開始時にコマを進める。
#   マス26はゴール（山頂の鐘）。座標はフロント側（game.html）が保持する。
# ──────────────────────────────────────────
MAP_GOAL_TILE = 26
MAP_TILE_FOR_TURN = [0, 2, 3, 5, 7, 8, 10, 12, 13, 15, 17, 18, 20, 22, 23, 25]


def map_move_html(from_tile: int, to_tile: int, label: str = "",
                  fall: bool = False, goal: bool = False, intro: bool = False,
                  r_from: int = -1, r_to: int = -1, r_fall: bool = False,
                  r_name: str = "") -> str:
    """🏁 r_from/r_to はライバルコマの移動（-1=ライバル非表示）。
    r_from == r_to なら現在地に静止表示のみ。"""
    return (
        f'<div class="map-move" data-from="{from_tile}" data-to="{to_tile}"'
        f' data-fall="{1 if fall else 0}" data-goal="{1 if goal else 0}"'
        f' data-intro="{1 if intro else 0}" data-label="{esc(label)}"'
        f' data-rfrom="{r_from}" data-rto="{r_to}"'
        f' data-rfall="{1 if r_fall else 0}" data-rname="{esc(r_name)}"></div>'
    )


def story_panel(body: str, title: str = "", cls: str = "gold") -> str:
    title_html = f'<div class="panel-title">{title}</div>' if title else ""
    return f'<div class="story-panel {cls}">{title_html}<div class="panel-body">{body}</div></div>'


def story_rule(text: str, color: str = "cyan") -> str:
    return f'<div class="story-rule {color}">◆◆◆ {esc(text)} ◆◆◆</div>'


def result_html(text: str, is_good: bool) -> str:
    cls = "result-good" if is_good else "result-bad"
    icon = "✅" if is_good else "⚡"
    return (
        f'<div class="result-panel {cls}">'
        f'<span class="result-icon">{icon}</span>'
        f'<pre class="result-text">{esc(text)}</pre>'
        f'</div>'
    )


def bomb_html(text: str) -> str:
    return (
        f'<div class="bomb-panel">'
        f'<div class="bomb-title">💥 過去の決断の代償！</div>'
        f'<pre class="bomb-text">{esc(text)}</pre>'
        f'</div>'
    )


def _split_agm_result(text: str):
    """AGM議決結果テキストを (議案結果, 株主反応, 閉会行) に分割する。
    株主反応（── 株主反応 ── または 💬 で始まる行）を抽出し、
    閉会行（『定時株主総会 閉会』を含む行）の直前に配置できるようにする。"""
    lines = text.split("\n")
    react_idx = None
    closing_idx = None
    for i, ln in enumerate(lines):
        # 株主反応セクションは _secondary が必ず付ける「── 株主反応 ──」で判定
        if react_idx is None and "── 株主反応 ──" in ln:
            react_idx = i
        if "定時株主総会 閉会" in ln:
            closing_idx = i
    if react_idx is None:
        return text, "", ""
    if closing_idx is None or closing_idx < react_idx:
        return "\n".join(lines[:react_idx]), "\n".join(lines[react_idx:]), ""
    main    = "\n".join(lines[:react_idx])
    reaction = "\n".join(lines[react_idx:closing_idx])
    closing  = "\n".join(lines[closing_idx:])
    return main, reaction, closing


def _rw_label(r: int) -> str:
    """資金残存Q数を人が読みやすいテキストに変換"""
    if r >= 99:
        return "資金十分（黒字継続）"
    y, q = divmod(r, 4)
    if y >= 1:
        qs = f"{q}Q" if q else ""
        return f"約{y}年{qs}分"
    if r >= 4:
        return f"{r}Q（約{r * 3}ヶ月）"
    return f"⚠ {r}Q（{r * 3}ヶ月）要調達！"


def choices_html(choices_list, letters="ABCD") -> str:
    color_classes = ["choice-a", "choice-b", "choice-c", "choice-d"]
    parts = []
    for i, ch in enumerate(choices_list):
        lbl = letters[i] if i < len(letters) else str(i + 1)
        cls = color_classes[i % 4]
        title_text = _re.sub(r'^[A-D]\.\s*', '', ch.label)

        # profit_hint / risk_hint を取得（description に既に含まれていれば重複チェック）
        profit_hint = (getattr(ch, 'profit_hint', '') or '').strip()
        risk_hint   = (getattr(ch, 'risk_hint',   '') or '').strip()
        desc_text   = (ch.description or '').strip()

        # 説明文に既にヒント内容が含まれていれば表示しない（重複防止）
        def _not_dup(hint):
            if not hint:
                return False
            # ヒントの核心語（¥や数値を除いた最初の10文字）が説明にあれば重複とみなす
            core = hint.lstrip("💰⚠ ").split("・")[0][:10]
            return core not in desc_text

        hints_html = ""
        hint_parts = []
        if profit_hint and _not_dup(profit_hint):
            hint_parts.append(f'<span class="hint-profit">💰 {esc(profit_hint)}</span>')
        if risk_hint and _not_dup(risk_hint):
            hint_parts.append(f'<span class="hint-risk">⚠ {esc(risk_hint)}</span>')
        if hint_parts:
            # 💰/⚠ ヒントは初期非表示。IPO先生のボタンを押すと revealHints() で表示される
            hints_html = (
                f'<div class="choice-hints choice-hints-hidden">'
                f'{"".join(hint_parts)}'
                f'</div>'
            )

        parts.append(
            f'<div class="choice-item {cls}" ondblclick="submitAction(\'{lbl}\')" '
            f'title="ダブルクリックで選択">'
            f'<span class="choice-letter">{lbl}</span>'
            f'<div class="choice-text">'
            f'<div class="choice-title">{esc(title_text)}</div>'
            f'<div class="choice-desc">{esc(desc_text)}</div>'
            f'{hints_html}'
            f'</div>'
            f'</div>'
        )
    header = (
        '<div class="choices-header">'
        '👆 選択肢をダブルクリックで決定'
        '</div>'
    )
    return f'<div class="choices-wrapper">{header}<div class="choices-container">{"".join(parts)}</div></div>'


# ══════════════════════════════════════════════
def _colorize_agm_votes(html: str) -> str:
    """AGM議決結果の📋議案行と🗳投票行を1行にまとめ、
    ブロック全体を可決=緑・否決=オレンジで着色する。
    html は esc() + <br>変換済みを受け取る。"""
    lines = html.split('<br>')
    output = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if '📋' in line:
            # ブロック収集：次の📋行または ━ 区切りまで
            block = [line]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if '📋' in nxt or nxt.strip().startswith('━') or '💬' in nxt or '── 株主反応' in nxt:
                    break
                block.append(nxt)
                j += 1
            # ブロック内の最初の🗳行を探す
            vote_idx = next((k for k, bl in enumerate(block) if '🗳' in bl), None)
            if vote_idx is not None:
                # 📋〜🗳の手前行を1行に結合（内部<br>を除去）
                agenda_part = ' '.join(bl.strip() for bl in block[:vote_idx] if bl.strip())
                vote_lines = block[vote_idx:]
                # 議案行と🗳行をスペース1つで結合（<br>なし）
                merged_first = agenda_part + ' ' + vote_lines[0].strip()
                merged_block = [merged_first] + vote_lines[1:]
                # 可決/否決を判定してブロック全体を着色
                block_text = ' '.join(merged_block)
                if '【可決】' in block_text:
                    color = '#00dd88'
                elif '【否決】' in block_text:
                    color = '#ffaa44'
                else:
                    color = None
                if color:
                    block_html = '<br>'.join(merged_block)
                    output.append(
                        f'<span style="color:{color};font-weight:700">{block_html}</span>'
                    )
                else:
                    output.extend(merged_block)
            else:
                output.extend(block)
            i = j
        else:
            output.append(line)
            i += 1
    return '<br>'.join(output)


def _strip_score_lines(text: str) -> str:
    """deferred outcomes表示時に、スコア変動数値行を除去する。
    「会計品質+20 / 監査法人信頼+20（報酬¥8M/Q）」「士気+10」など
    スコア変動を表す行はすべて除去する（同Q決算レポートで表示するため）。"""
    import re as _re2
    _SCORE_NAMES = (
        r'(?:内部統制(?:スコア)?|会計品質|コンプライアンス|コンプラ'
        r'|ガバナンス|投資家信頼|監査法人信頼|リスクスコア|士気)'
    )
    _score_chunk = _re2.compile(_SCORE_NAMES + r'[+\-±]\d+(?:\.\d+)?')
    # スコア記号・区切り・コスト表記などノイズ文字
    _noise = _re2.compile(
        r'[\s▶▷・／/　（）()\[\]【】「」+\-±0-9Mm¥￥円QqQQ百万兆億%％、。,.…─—　]'
    )
    lines = text.split('\n')
    filtered = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            filtered.append(line)
            continue
        # スコアパターンが全く含まれない行は保持
        if not _score_chunk.search(stripped):
            filtered.append(line)
            continue
        # スコアパターンを除去した残りの有意文字数を確認
        remainder = _score_chunk.sub('', stripped)
        remainder = _noise.sub('', remainder)
        # 残り8文字以下 → スコア変動行として除去
        if len(remainder) <= 8:
            continue
        filtered.append(line)
    return '\n'.join(filtered)


# ゲームセッション
# ══════════════════════════════════════════════
class Phase:
    TITLE = "title"
    BIZ_SELECT = "biz_select"
    MARKET_SELECT = "market_select"
    NAME_INPUT = "name_input"
    CONTINUE = "continue"
    EVENT_CHOICE = "event_choice"
    ALT_CHOICE = "alt_choice"
    FORTUNE_CHOICE = "fortune_choice"   # 突発イベント選択
    EXAM_BATTLE = "exam_battle"         # 審査ボス戦（審査官との質疑応答）
    ENDING = "ending"


class GameSession:
    def __init__(self):
        self.phase = Phase.TITLE
        self.company: Optional[Company] = None
        self.timeline: Optional[Timeline] = None
        self.pending_events: list = []
        self.pending_event_idx: int = 0
        self._game_events: list = []   # ゲームごとのイベントコピー（fired状態が混入しないよう隔離）
        self.selected_biz: int = 0
        self._next_action: str = ""
        self._alt_choices: List[Choice] = []
        self._placeholder: str = "► Enter キーを押してゲームを開始..."
        self._queue: List[dict] = []
        self.target_market: str = "growth"   # growth / standard / prime
        self._prev_cash: float = 0.0
        self._prev_rev: float = 0.0
        self._prev_scores: dict = {}
        self._world_events: list = []
        # 一時費用トラッキング（今Q支出した一時費用の累計）
        self._this_turn_one_time_costs: float = 0.0
        self._prev_turn_one_time_costs: float = 0.0
        # 四半期スロット用：吉凶カウンタ
        self._this_turn_good: int = 0
        self._this_turn_bad: int = 0
        # 突発イベント（スロット後に出現する世界イベント）
        self._pending_fortune = None        # Optional[WorldEvent]
        self._fortune_choices: List[Choice] = []
        # ターン開始時の財務スナップショット（ターン終了時の決算レポート用）
        self._turn_start_cash: float = 0.0
        self._turn_start_burn: float = 0.0
        self._turn_start_rev: float = 0.0
        self._turn_start_mktcap: float = 0.0
        self._turn_start_shareholders: int = 0
        # ターン内の決断ログ（決算レポート用）
        self._turn_decisions: List[str] = []
        # AI突発クライシス（毎ゲーム3件をランダムスケジュール）
        # [(turn_key, template_dict), ...]  turn_key = "n_period:quarter"
        self._scheduled_crises: List[tuple] = []
        # 最後のGemini APIエラー（UI診断用）
        self._last_gemini_error: str = ""
        # 前Qの意思決定結果を次ターン冒頭に表示するためのキュー
        # [(event_title, choice_label, result_msg, is_good), ...]
        self._deferred_outcomes: list = []
        # 上場延期後の監査ルーレット再挑戦フラグ
        self._audit_retry_pending: bool = False
        # 緊急体制整備後の2四半期カウントダウン（0=未発動）
        self._audit_emergency_countdown: int = 0
        # スコア変動要因トラッキング（決算レポート内で表示し、表示後クリア）
        self._score_change_reasons: list = []
        # 全イベント処理完了後の後続アクション（"tse_exam" など）
        self._post_events_action: str = ""
        # YTD累計（当期Q1〜前Q完了分、Q1開始時にリセット）
        self._ytd_rev:  float = 0.0
        self._ytd_burn: float = 0.0
        self._ytd_otc:  float = 0.0
        # AGM事前決議（Q4で意思決定 → Q1で結果表示）
        self._pending_agm_result:       str  = ""
        self._pending_agm_is_good:      bool = True
        self._pending_agm_choice_label: str  = ""
        # TSE審査 2フェーズ（チェック表示 → ルーレット → 判定）
        self._tse_pending_issues: list = []
        # AGMスコア変動の翌Q1への繰り延べ
        self._agm_pending_score_changes: dict = {}
        self._agm_deferred_reasons: list = []
        # N-1期冒頭でEVENT_OUTSIDE_DIRECTOR_N1を強制発火
        self._force_outside_director_n1: bool = False
        # マクロショック（パンデミック等）が強行された場合の情報
        self._macro_shock_active: dict = {}   # {"name": "...", "pass_prob": 0.2, "fail_reason": "..."}
        # ⏳ タイマークライシス：未解消の緊急課題（毎ターン対応選択を強制表示）
        self._timer_crises: list = []         # [{"kind": "cfo_successor", "remaining": 2}, ...]
        # 審査ボス戦（審査官との質疑応答）の状態
        self._exam_qs: list = []          # 出題された問題（dictのリスト）
        self._exam_idx: int = 0           # 現在の問題番号
        self._exam_gauge: int = 50        # 審査官の懸念ゲージ（0-100、低いほど良い）
        self._exam_correct: int = 0       # 正解数
        self._tse_pass_total: tuple = (0, 0)   # 書類審査の (クリア数, 総項目数)

    def _add(self, html_content: str, item_type: str = "normal"):
        self._queue.append({"html": html_content, "type": item_type})

    def _ph(self, text: str):
        self._placeholder = text

    # ──────────────────────────────────────────
    # 初期タイトル画面
    # ──────────────────────────────────────────
    def get_title_story(self) -> List[dict]:
        self._queue = []
        # セーブデータ確認
        resume_html = ""
        if _has_save():
            sv = _load_game()
            if sv and sv.company and sv.timeline:
                c, t = sv.company, sv.timeline
                resume_html = (
                    f'<div class="title-save-info">'
                    f'📂 セーブデータ：{esc(c.name)}（{esc(c.business_type.value)}）'
                    f' / {esc(t.period_name())} Q{t.quarter} / 残り{t.quarters_until_ipo()}Q'
                    f'</div>'
                    f'<button class="title-resume-btn" '
                    f'onclick="window.gameAction(\'__RESUME__\')">📂 前回の続きから再開</button><br>'
                )
        self._add(f'''
        <div class="title-screen">
            <div class="doves-container">
                <span class="dove dove-1">🕊</span>
                <span class="dove dove-2">🕊</span>
                <span class="dove dove-3">🕊</span>
                <span class="dove dove-4">🕊</span>
                <span class="dove dove-5">🕊</span>
                <span class="dove dove-6">🕊</span>
            </div>
            <div class="title-content">
                <div class="title-logo">THE IPO PATH</div>
                <div class="title-sub-ja">栄 光 へ の 決 断</div>
                <div class="title-tagline">— その一歩が、東証の鐘を鳴らす —</div>
                <div class="title-desc">
                    創業から4年。次の一歩は<strong>東証への上場</strong>。<br>
                    監査体制・内部統制・ガバナンス・資本政策・市場区分の選択——<br>
                    <span>40を超える決断</span>が、あなたの会社の運命を分けます。<br>
                    <span style="font-size:14px;font-style:italic">
                    上場の鐘を鳴らすその日、あなたは何を選び、何を守ったのか。
                    </span>
                </div>
                <div class="title-role-badge">👤 あなたの役割：代表取締役社長</div><br>
                <button class="title-start-btn" onclick="window.gameAction(\'\')">▶ 栄光への旅を始める</button><br>
                {resume_html}
            </div>
        </div>
        ''', "title")
        return self._queue

    # ──────────────────────────────────────────
    # メイン入力ハンドラ
    # ──────────────────────────────────────────
    def handle(self, value: str) -> tuple[List[dict], str, str]:
        self._queue = []
        self._dispatch(value)
        return self._queue, self._placeholder, self.build_sidebar()

    def _dispatch(self, value: str):
        if self.phase == Phase.TITLE:
            self._start_biz_select()

        elif self.phase == Phase.BIZ_SELECT:
            v = value.upper()
            valid = list("ABCD")[: len(BUSINESS_PARAMS)]
            if v in valid:
                self.selected_biz = valid.index(v)
                self._start_market_select()
            else:
                self._add(f'<div class="err-msg">  {" / ".join(valid)} のいずれかを入力してください</div>')

        elif self.phase == Phase.MARKET_SELECT:
            v = value.upper()
            market_map = {"A": "growth", "B": "standard", "C": "prime"}
            if v in market_map:
                self.target_market = market_map[v]
                self._start_name_input()
            else:
                self._add('<div class="err-msg">  A / B / C のいずれかを選択してください</div>')

        elif self.phase == Phase.NAME_INPUT:
            self._init_game(value or "テック株式会社")

        elif self.phase == Phase.CONTINUE:
            if self._next_action == "begin_turn":
                self._begin_turn()
            elif self._next_action == "next_event":
                self._show_next_event()
            elif self._next_action == "advance_turn":
                self._advance_turn()
            elif self._next_action == "show_fortune":
                self._show_fortune_event()
            elif self._next_action == "tse_verdict":
                self._run_tse_verdict()
            elif self._next_action == "tse_exam":
                self._run_tse_exam()
            elif self._next_action == "exam_battle":
                self._start_exam_battle()

        elif self.phase == Phase.EVENT_CHOICE:
            if value == "__ADVISOR__":
                self._show_advisor_advice()   # フェーズ変更なし・アドバイス表示のみ
            else:
                event = self.pending_events[self.pending_event_idx]
                valid = list("ABCD")[: len(event.choices)]
                if value.upper() in valid:
                    self._apply_choice(valid.index(value.upper()))
                else:
                    self._add(f'<div class="err-msg">  {" / ".join(valid)} のいずれかを選んでください</div>')

        elif self.phase == Phase.ALT_CHOICE:
            valid = list("ABCD")[: len(self._alt_choices)]
            if value.upper() in valid:
                self._apply_alt(valid.index(value.upper()))
            else:
                self._add(f'<div class="err-msg">  {" / ".join(valid)} のいずれかを選んでください</div>')

        elif self.phase == Phase.EXAM_BATTLE:
            if value.upper() in ("A", "B", "C", "D"):
                self._answer_exam_question("ABCD".index(value.upper()))
            else:
                self._add('<div class="err-msg">  A / B / C / D のいずれかを選んでください</div>')

        elif self.phase == Phase.FORTUNE_CHOICE:
            if value == "__ADVISOR__":
                self._show_advisor_advice()   # フェーズ変更なし
            else:
                valid = list("ABCD")[: len(self._fortune_choices)]
                if value.upper() in valid:
                    self._apply_fortune_choice(valid.index(value.upper()))
                else:
                    self._add(f'<div class="err-msg">  {" / ".join(valid)} のいずれかを選んでください</div>')

    # ──────────────────────────────────────────
    # 業種選択
    # ──────────────────────────────────────────
    def _start_biz_select(self):
        _delete_save()   # 新規ゲーム開始を選んだ瞬間に旧セーブを削除
        self.phase = Phase.BIZ_SELECT
        self._add(story_rule("社長、まず御社の業種をお選びください", "yellow"))
        self._add('<div class="hint-text">業種によって初期資金・成長率・リスクが異なります</div>')

        labels = ["A", "B", "C", "D"]
        cls_map = ["choice-a", "choice-b", "choice-c", "choice-d"]
        parts = []
        for i, (btype, params) in enumerate(BUSINESS_PARAMS.items()):
            parts.append(
                f'<div class="biz-choice {cls_map[i]}">'
                f'<span class="choice-letter">{labels[i]}</span>'
                f'<div class="biz-info">'
                f'<div class="biz-name">{esc(btype.value)}</div>'
                f'<div class="biz-desc">{esc(params["description"])}</div>'
                f'<div class="biz-stats">'
                f'初期資金 ¥{params["initial_cash"]:.0f}M'
                f' ｜ 成長率/Q {params["growth_rate"]:.0%}'
                f' ｜ 支出/Q ¥{params["burn_rate"]:.0f}M'
                f'</div>'
                f'</div>'
                f'</div>'
            )
        self._add(f'<div class="biz-list">{"".join(parts)}</div>')
        valid = labels[: len(BUSINESS_PARAMS)]
        self._ph(f"► 業種を選択 ({' / '.join(valid)})")

    # ──────────────────────────────────────────
    # 上場市場選択
    # ──────────────────────────────────────────
    def _start_market_select(self):
        self.phase = Phase.MARKET_SELECT
        self._add(story_rule("社長、目標とする上場市場をお選びください", "gold"))
        self._add('<div class="hint-text">市場によって審査基準と難易度が大きく異なります</div>')
        markets = [
            ("A", "グロース市場", "★☆☆ 入門", "#00cc66",
             "成長可能性重視の新興企業向け市場",
             "株主数: 150人以上 ／ 流通株式時価総額: 5億円以上",
             "財務要件（利益・純資産）なし。高い成長可能性が問われます。"),
            ("B", "スタンダード市場", "★★☆ 標準", "#ffcc00",
             "安定した収益基盤を持つ企業向け標準市場",
             "株主数: 400人以上 ／ 流通株式時価総額: 10億円以上",
             "純資産がプラス＋直近1年利益1億円以上。2期監査が必要。"),
            ("C", "プライム市場", "★★★ 最難関", "#ff4444",
             "最高水準のガバナンス・規模を誇る企業向けトップ市場",
             "株主数: 800人以上 ／ 流通株式時価総額: 100億円以上",
             "時価総額250億円以上。純資産50億円以上。利益25億円/2年。"),
        ]
        parts = []
        for letter, name, diff, col, desc, reqs, note in markets:
            parts.append(
                f'<div class="market-choice" style="border-left:4px solid {col};padding:12px;margin:8px 0;background:rgba(0,0,0,0.3)">'
                f'<span class="choice-letter" style="color:{col}">{letter}.</span> '
                f'<strong style="color:{col}">{name}</strong> '
                f'<span style="color:{col};font-size:12px">{diff}</span><br>'
                f'<div style="color:#cce8ff;margin-top:4px">{desc}</div>'
                f'<div style="color:#7aaccc;font-size:12px;margin-top:4px">📋 {reqs}</div>'
                f'<div style="color:#7aaccc;font-size:12px">{note}</div>'
                f'</div>'
            )
        self._add(f'<div class="market-list">{"".join(parts)}</div>')
        self._ph("► 市場を選択 (A / B / C)")

    # ──────────────────────────────────────────
    # 会社名入力
    # ──────────────────────────────────────────
    def _start_name_input(self):
        self.phase = Phase.NAME_INPUT
        btype = list(BUSINESS_PARAMS.keys())[self.selected_biz]
        self._add(f'<div class="ok-msg">✔ {esc(btype.value)}を選択しました</div>')
        self._add(story_rule("社長、創業した会社の名前を教えてください", "cyan"))
        self._add('<div class="hint-text">（空欄のまま「決定」を押すと「テック株式会社」になります）</div>')
        self._ph("► 会社名を入力...")

    # ──────────────────────────────────────────
    # ゲーム初期化
    # ──────────────────────────────────────────
    def _init_game(self, name: str):
        _delete_save()   # 新規ゲーム開始時は旧セーブを削除
        btype = list(BUSINESS_PARAMS.keys())[self.selected_biz]
        self.company = Company(name=name, business_type=btype)
        initialize_company(self.company)
        # ── プライム市場：大手企業スケール補正（×5） ──────────────────────
        self.company.target_market_code = self.target_market  # PER計算で参照
        if self.target_market == "prime":
            _PRIME_SCALE = 5.0
            self.company.cash                   *= _PRIME_SCALE
            self.company.revenue.recognized     *= _PRIME_SCALE
            self.company.revenue.deferred       *= _PRIME_SCALE
            self.company.quarterly_burn         *= _PRIME_SCALE
            self.company.market_cap_million     *= _PRIME_SCALE
        # ─────────────────────────────────────────────────────────────────
        self.company.flags.no_voucher_management = True
        self.company.flags.no_job_separation = True
        self.company.flags.no_outside_director = True
        self.company.flags.no_related_party_review = True
        self.company.flags.no_compliance_system = True
        self.company.has_underwriter = False
        self.timeline = Timeline()
        self._game_events = get_fresh_events()   # ← 毎ゲーム新規コピー
        self._world_events = get_fresh_world_events()
        self._schedule_ai_crises()               # ← AI突発クライシスをスケジュール
        # ── 🏁 ライバル企業（上場レース）の初期化 ──
        _rival_names = {
            "SaaS":     "クラウドフォース",
            "FinTech":  "ペイブリッジ",
            "製造業":    "ミライ精工",
            "小売業":    "マルシェHD",
        }
        self._rival = {
            "name": _rival_names.get(btype.value, "ライバル社"),
            "pos": 0,            # ワールドマップ上のマス（0〜26）
            "listed": False,     # 上場済みか
        }
        self._prev_cash = self.company.cash
        self._prev_rev  = self.company.revenue.recognized
        self._prev_scores = self._get_score_snapshot()

        mkt_labels = {"growth": "グロース市場", "standard": "スタンダード市場", "prime": "プライム市場"}
        mkt_label = mkt_labels.get(self.target_market, "グロース市場")

        if self.target_market == "prime":
            _biz_name = {
                "SaaS":          "大手SaaS企業（年商数十億円規模）",
                "FinTech":       "大手FinTech企業（年商数十億円規模）",
                "製造業":        "大手製造業（年商数十億円規模・工場複数拠点）",
                "小売業":        "全国展開の大手小売チェーン（年商数十億円規模）",
            }.get(btype.value if hasattr(btype, 'value') else str(btype), "大手企業")
            _start_panel_body = (
                f"<strong class='gold-text'>{esc(name)}</strong> 代表取締役社長、"
                f"プライム市場への上場準備を開始します！<br><br>"
                f"<span class='dim-text'>目標上場市場：<strong style='color:#ff8888'>★★★ {esc(mkt_label)}</strong><br><br>"
                f"あなたが率いるのは<strong>{esc(_biz_name)}</strong>です。<br>"
                f"すでに相当の事業規模を持ちますが、東証プライム市場の形式要件は最高水準——<br>"
                f"時価総額250億円以上・純資産50億円以上・株主800名以上が求められます。<br>"
                + (
                    f"<br><span style='color:#ffaa44;font-weight:700'>⚠ 製造業×プライム市場は本ゲーム最高難度の組み合わせです。<br>"
                    f"低PER業種の特性上、時価総額要件達成には全イベントで最善の選択が必要です。</span><br>"
                    if btype.value == "製造業" else ""
                )
                + f"<br>"
                f"N-3期（第1四半期）からスタートです。<br>"
                f"N期Q4の東証上場審査まで、社長として賢明な決断を積み重ねてください。<br><br>"
                f"◎ 各ターンで部下・監査法人・顧問からの報告が届きます。<br>"
                f"◎ 毎四半期、外部環境の変化（世界イベント）が会社に影響します。</span>"
            )
        else:
            _start_panel_body = (
                f"<strong class='gold-text'>{esc(name)}</strong> 代表取締役社長、IPO準備を開始します！<br><br>"
                f"<span class='dim-text'>目標上場市場：<strong style='color:#ffd700'>{esc(mkt_label)}</strong><br><br>"
                f"N-3期（第1四半期）からスタートです。<br>"
                f"N期Q4の東証上場審査まで、社長として賢明な決断を積み重ねてください。<br><br>"
                f"◎ 各ターンで部下・監査法人・顧問からの報告が届きます。<br>"
                f"◎ 毎四半期、外部環境の変化（世界イベント）が会社に影響します。</span>"
            )
        self._add(story_panel(
            _start_panel_body,
            "◆ 社長就任・IPO準備スタート ◆", "green"
        ))
        self.phase = Phase.CONTINUE
        self._next_action = "begin_turn"
        self._ph("► Enter でゲーム開始...")

    # ──────────────────────────────────────────
    # AI突発クライシス スケジューリング
    # ──────────────────────────────────────────
    def _schedule_ai_crises(self):
        """ゲーム開始時に12テンプレから3件をランダムに選び、ランダムターンに配置する。
        毎ゲーム異なる突発事態が発生し、リプレイ性を高める。
        さらに30%の確率でマクロショック（パンデミック等）を1件追加する。"""
        # ゲーム全体のターンキー一覧（n_period: -3〜0, quarter: 1〜4）
        all_turns = [f"{n}:{q}" for n in (-3, -2, -1, 0) for q in (1, 2, 3, 4)]
        # Q4は上場審査・決算が集中するため突発を避ける
        candidate_turns = [tk for tk in all_turns if not tk.endswith(":4")]

        templates = _rand.sample(CRISIS_TEMPLATES, min(3, len(CRISIS_TEMPLATES)))
        scheduled_keys = _rand.sample(candidate_turns, len(templates))

        self._scheduled_crises = list(zip(scheduled_keys, templates))

        # マクロショック（30%の確率で1件追加）— N-1期〜N期のQ1〜Q3に配置
        if _rand.random() < 0.30 and MACRO_SHOCK_TEMPLATES:
            macro_tmpl = _rand.choice(MACRO_SHOCK_TEMPLATES)
            macro_turns = [tk for tk in candidate_turns
                           if tk.startswith("-1:") or tk.startswith("0:")]
            if macro_turns:
                # 既にスケジュール済みのターンと被らないようにする
                used_keys = set(scheduled_keys)
                available_macro_turns = [tk for tk in macro_turns if tk not in used_keys]
                if available_macro_turns:
                    macro_key = _rand.choice(available_macro_turns)
                    self._scheduled_crises.append((macro_key, macro_tmpl))
                    print(f"  [MACRO SHOCK] Scheduled: {macro_tmpl['id']} at {macro_key}")

        ids = [t["id"] for t in [x[1] for x in self._scheduled_crises]]
        turns = [x[0] for x in self._scheduled_crises]
        print(f"  [CRISIS] Scheduled: {list(zip(ids, turns))}")

    def _check_and_fire_crisis(self) -> bool:
        """現在のターンにスケジュール済みのAIクライシスがあれば _pending_fortune に設定する。
        設定した場合 True を返す。世界イベントより優先されるため呼び出し側で上書きする。"""
        t = self.timeline
        current_key = f"{t.n_period}:{t.quarter}"
        for i, (key, tmpl) in enumerate(self._scheduled_crises):
            if key == current_key:
                self._scheduled_crises.pop(i)
                self._build_crisis_fortune(tmpl)
                return True
        return False

    def _build_crisis_fortune(self, tmpl: dict):
        """AIクライシスを _pending_fortune に設定する（表示はスロット後に行う）。
        Geminiが使えればシナリオを生成し、なければデフォルト文言で組み立てる。"""
        generated = self._call_gemini_crisis_scenario(tmpl)
        title = generated.get("title") or f"⚡ 突発：{tmpl['topic'][:18]}…"
        desc  = generated.get("description") or (
            f"【緊急事態】{tmpl['topic']}\n\n"
            f"社長、即断が求められています。どう対処しますか？"
        )
        la = generated.get("label_a") or f"対処する（コスト高）"
        da = generated.get("desc_a")  or tmpl["hint_a"]
        lb = generated.get("label_b") or f"先送り・妥協する"
        db = generated.get("desc_b")  or tmpl["hint_b"]

        choices = [
            Choice(label=la, description=da, immediate_effect=tmpl["effect_a"],
                   profit_hint=tmpl.get("hint_a", "")),
            Choice(label=lb, description=db, immediate_effect=tmpl["effect_b"],
                   risk_hint=tmpl.get("hint_b", "")),
        ]
        from types import SimpleNamespace
        self._pending_fortune = SimpleNamespace(
            id=tmpl["id"], title=title, category="crisis",
            description=desc, choices=choices, fired=False,
            macro_shock=tmpl.get("macro_shock", False),
            shock_name=tmpl.get("shock_name", ""),
            pass_prob=tmpl.get("pass_prob", 1.0),
            fail_reason=tmpl.get("fail_reason", ""),
        )
        # マクロショックイベント発生時は報告を待たず即時スコアへ影響を与える
        if tmpl.get("macro_shock", False):
            _shock_name = tmpl.get("shock_name", "マクロショック")
            _c = self.company
            _pre_macro = self._get_score_snapshot()
            # 深刻度に応じた士気ダメージ（pass_prob低いほど深刻）
            _pass = tmpl.get("pass_prob", 0.3)
            _morale_hit = -20 if _pass <= 0.20 else -12  # パンデミック/金融危機は-20
            _c.employee_morale = max(0, _c.employee_morale + _morale_hit)
            _c.flags.total_risk_score += 15  # 上場失敗リスク上昇
            # 時価総額の大幅下落（投資家心理悪化・市場環境急変）
            _mktcap_mul = 0.65 if _pass <= 0.20 else 0.75
            _c.market_cap_million = max(100.0, _c.market_cap_million * _mktcap_mul)
            _c.investor_trust = max(0, _c.investor_trust - 15)  # 投資家信頼急落
            _post_macro = self._get_score_snapshot()
            _macro_delta = {k: _post_macro[k] - _pre_macro[k] for k in _post_macro if _post_macro[k] != _pre_macro[k]}
            _macro_parts = ", ".join(f"{k}{'+'if v>=0 else ''}{v:.0f}" for k, v in _macro_delta.items())
            if _macro_parts:
                self._score_change_reasons.append(
                    f"⚡ {_shock_name}発生（経営環境急変）：{_macro_parts}・リスク+15"
                )

    def _call_gemini_crisis_scenario(self, tmpl: dict) -> dict:
        """Geminiにクライシスシナリオを生成させる。失敗時は空dictを返す。"""
        global _GEMINI_AVAILABLE
        if not _GEMINI_AVAILABLE:
            return {}

        c = self.company
        t = self.timeline

        prompt = f"""あなたはIPO準備シミュレーションゲームのシナリオライターです。
以下の突発事態シナリオをゲームの意思決定イベントとして作成してください。

【会社】{c.name}（{c.business_type.value}）/ {t.period_name()} Q{t.quarter}
【財務状態】手元資金¥{c.cash:.0f}M / 投資家信頼{c.investor_trust} / リスクスコア{c.flags.total_risk_score}
【事態の概要】{tmpl['topic']}
【選択肢Aの内容（対処）】{tmpl['hint_a']}
【選択肢Bの内容（妥協）】{tmpl['hint_b']}

以下のJSON形式で返答してください（日本語・他の文章は不要）:
{{
  "title": "15字以内の見出し（例：CTOが競合に引き抜かれた！）",
  "description": "150〜200字のドラマチックな状況描写。社長が受けた衝撃・緊迫感を含む",
  "label_a": "20字以内の選択肢Aのラベル",
  "desc_a": "30字以内の選択肢Aの補足説明",
  "label_b": "20字以内の選択肢Bのラベル",
  "desc_b": "30字以内の選択肢Bの補足説明"
}}"""

        raw = self._gemini_generate(
            prompt, max_tokens=400, temperature=0.88, timeout=10.0,
            context="crisis",
        )
        if not raw:
            return {}
        try:
            import json as _json
            # JSONブロックを抽出（```json...```に包まれていても対応）
            if "```" in raw:
                raw = raw.split("```")[-2] if raw.count("```") >= 2 else raw
                raw = raw.lstrip("json").strip()
            result = _json.loads(raw)
            print(f"  [AI-CRISIS] Parsed scenario: {result.get('title','?')}")
            return result
        except Exception as e:
            print(f"  [WARN] Gemini crisis JSON parse error: {e}")
            return {}

    # ──────────────────────────────────────────
    # スコアスナップショット
    # ──────────────────────────────────────────
    def _get_score_snapshot(self) -> dict:
        c = self.company
        return {
            "内統":    min(100, max(0, c.internal_control_score)),
            "コンプラ": min(100, max(0, c.compliance_score)),
            "会計":    min(100, max(0, c.accounting_quality)),
            "統治":    min(100, max(0, c.governance_score)),
            "監査信頼": min(100, max(0, c.auditor_trust)),
            "投資家信頼": min(100, max(0, c.investor_trust)),
            "士気":    min(100, max(0, c.employee_morale)),
        }

    @staticmethod
    def _scaled_score_delta(current: int, delta: int) -> tuple[int, str]:
        """80点超で逓減（×0.5）、90点超でさらに逓減（×0.25）してスコアを加算する。
        Returns (actual_delta_applied, note_str).
        note_str は表示用（空文字なら表示不要）。"""
        if delta <= 0:
            return delta, ""   # 減点は逓減なし
        note = ""
        if current >= 90:
            applied = max(1, round(delta * 0.25))
            if applied < delta:
                note = f"90点超のため{delta}→{applied}に逓減"
        elif current >= 80:
            applied = max(1, round(delta * 0.5))
            if applied < delta:
                note = f"80点超のため{delta}→{applied}に逓減"
        else:
            applied = delta
        return applied, note

    # ──────────────────────────────────────────
    # 📊 四半期決算レポート（ターン進行時）
    # ──────────────────────────────────────────
    def _render_quarter_closing_report(self, t, c, *,
                                       turn_start_cash, turn_start_burn, turn_start_rev,
                                       turn_start_mktcap, turn_start_shareholders,
                                       pre_fin_cash, post_fin_cash,
                                       pre_fin_rev, post_fin_rev,
                                       one_time_this_q, decisions_taken):
        """ターン進行時に、その四半期の決算結果を詳細表示する。
        - 意思決定の一時費用・恒久費用増
        - 売上計上・Burn差引
        - Cash・時価総額の変動
        を全部集計して見せる
        """
        # 四半期業績フロー
        rev_delta_from_choices = pre_fin_rev - turn_start_rev          # 決断による売上変化
        rev_gain_from_growth   = post_fin_rev - pre_fin_rev            # 通常成長＋繰延認識
        burn_applied_this_q    = c.quarterly_burn                       # 決断反映後Burn（CF計算で使用）
        burn_delta_recurring   = c.quarterly_burn - turn_start_burn     # 決断による毎Q費用変化
        cash_flow_from_ops     = post_fin_cash - pre_fin_cash           # 四半期CF（売上 - Burn - コンプラコスト）
        total_cash_delta       = c.cash - turn_start_cash               # ターン開始→終了のキャッシュ純増減
        mktcap_delta           = c.market_cap_million - turn_start_mktcap
        shr_delta              = c.shareholder_count - turn_start_shareholders

        # Q4は「年度決算レポート」、Q1〜Q3は「Q○ 決算レポート」
        if t.quarter == 4:
            period_label = f"{t.period_name()} 年度"
        else:
            period_label = t.full_label()
        rows = []

        # 1) 意思決定行（あれば）
        if decisions_taken:
            decs_html = "".join(
                f'<div style="word-break:break-all;overflow-wrap:anywhere;margin:2px 0">'
                f'&nbsp;&nbsp;• {esc(d)}</div>'
                for d in decisions_taken
            )
            rows.append(
                f'<div class="qcr-section">'
                f'<div class="qcr-sh">🎯 当Qの意思決定 ({len(decisions_taken)}件)</div>'
                f'<div class="qcr-sb">{decs_html}</div>'
                f'</div>'
            )

        # 2) 売上サマリ
        # Q1は「今Q発生売上＝累計売上」、Q2以降は「当Q売上」
        ytd_rev_disp = getattr(self, '_ytd_rev', 0.0) + post_fin_rev  # _ytd_rev は前Qまでの累計（まだ今Qを加算前）
        rev_lines = []
        if abs(rev_delta_from_choices) >= 0.5:
            rev_lines.append(
                f'&nbsp;&nbsp;決断による売上変化：{"+" if rev_delta_from_choices >= 0 else ""}¥{rev_delta_from_choices:,.0f}M'
            )
        # 「繰延認識」→「売上成長・当Q計上分」に改名＋注記
        growth_note = "（契約済み売上の当Q分割計上＋成長分）" if rev_gain_from_growth > 0 else ""
        rev_lines.append(
            f'&nbsp;&nbsp;売上成長・当Q計上分：+¥{rev_gain_from_growth:,.0f}M{growth_note}'
        )
        rev_lines.append(f'&nbsp;&nbsp;<strong>当Q売上：¥{post_fin_rev:,.0f}M</strong>')
        if t.quarter > 1:
            rev_lines.append(f'&nbsp;&nbsp;<strong>当期累計売上（Q1〜Q{t.quarter}）：¥{ytd_rev_disp:,.0f}M</strong>')
        rows.append(
            f'<div class="qcr-section">'
            f'<div class="qcr-sh">📈 売上</div>'
            f'<div class="qcr-sb">{"<br>".join(rev_lines)}</div>'
            f'</div>'
        )

        # 3) 費用サマリ
        cost_rows = []
        if abs(burn_delta_recurring) >= 0.5:
            sign = "+" if burn_delta_recurring >= 0 else ""
            cost_rows.append(
                f'&nbsp;&nbsp;決断による恒久費用変化：<span style="color:{"#ff8855" if burn_delta_recurring>0 else "#55dd99"}">'
                f'{sign}¥{burn_delta_recurring:,.0f}M/Q</span>'
            )
        cost_rows.append(
            f'&nbsp;&nbsp;<strong>当Q経常費用：¥{burn_applied_this_q:,.0f}M</strong>'
            f'（人件費・システム費など毎Q継続発生）'
        )
        if one_time_this_q >= 0.5:
            cost_rows.append(
                f'&nbsp;&nbsp;一時費用（当Q限り）：<span style="color:#ff8855">¥{one_time_this_q:,.0f}M</span>'
                f'<span style="color:#aaa;font-size:0.9em">（翌Q以降は発生しない非継続コスト）</span>'
            )
        if t.quarter > 1:
            ytd_burn_disp = getattr(self, '_ytd_burn', 0.0) + burn_applied_this_q
            ytd_otc_disp  = getattr(self, '_ytd_otc',  0.0) + one_time_this_q
            cost_rows.append(
                f'&nbsp;&nbsp;<strong>当期累計費用（Q1〜Q{t.quarter}）：'
                f'¥{ytd_burn_disp:,.0f}M</strong>（経常）'
                + (f' ＋ ¥{ytd_otc_disp:,.0f}M（一時）' if ytd_otc_disp >= 0.5 else '')
            )
        rows.append(
            f'<div class="qcr-section">'
            f'<div class="qcr-sh">💸 費用</div>'
            f'<div class="qcr-sb">{"<br>".join(cost_rows)}</div>'
            f'</div>'
        )

        # 4) キャッシュフロー
        net_income = post_fin_rev - burn_applied_this_q - one_time_this_q
        ni_col = "#55dd99" if net_income >= 0 else "#ff6677"
        rows.append(
            f'<div class="qcr-section">'
            f'<div class="qcr-sh">💰 キャッシュフロー</div>'
            f'<div class="qcr-sb">'
            f'&nbsp;&nbsp;期首現金：¥{turn_start_cash:,.0f}M<br>'
            f'&nbsp;&nbsp;当Q純利益：<span style="color:{ni_col}">{"+" if net_income>=0 else ""}¥{net_income:,.0f}M</span>（売上 − 経常費用 − 一時費用）<br>'
            f'&nbsp;&nbsp;資金調達等：{"+" if (total_cash_delta - cash_flow_from_ops) >= 0 else ""}¥{total_cash_delta - cash_flow_from_ops:,.0f}M<br>'
            f'&nbsp;&nbsp;<strong>期末現金：¥{c.cash:,.0f}M</strong>'
            f'（{"+" if total_cash_delta>=0 else ""}¥{total_cash_delta:,.0f}M）'
            f'</div></div>'
        )

        # 5) 時価総額・株主 ＋ ② 10%超変動理由
        if abs(mktcap_delta) >= 1 or shr_delta != 0:
            mr = []
            if abs(mktcap_delta) >= 1:
                col = "#55dd99" if mktcap_delta >= 0 else "#ff6677"
                mr.append(f'&nbsp;&nbsp;時価総額：¥{c.market_cap_million:,.0f}M '
                          f'<span style="color:{col}">({"+" if mktcap_delta>=0 else ""}¥{mktcap_delta:,.0f}M)</span>')
                # ② 10%以上変動時に変動理由を注記
                if turn_start_mktcap > 0:
                    mktcap_pct = mktcap_delta / turn_start_mktcap
                    if abs(mktcap_pct) >= 0.10:
                        _reasons_pos = []
                        _reasons_neg = []
                        # 業績要因
                        _ni = post_fin_rev - c.quarterly_burn - one_time_this_q
                        if _ni > 0:
                            _reasons_pos.append("四半期黒字による成長評価")
                        elif _ni < 0:
                            _reasons_neg.append("四半期赤字による収益懸念")
                        # 一時費用インパクト
                        if one_time_this_q >= 5:
                            _reasons_neg.append(f"大型一時費用 ¥{one_time_this_q:,.0f}M の影響")
                        # ガバナンス信頼要因
                        if c.auditor_trust <= 40:
                            _reasons_neg.append("監査法人からの信頼低下")
                        if c.investor_trust <= 40:
                            _reasons_neg.append("投資家信頼の低迷")
                        # リスクスコア要因
                        _risk = c.flags.total_risk_score
                        if _risk >= 60:
                            _reasons_neg.append(f"累積リスクスコア高水準（{_risk}/100）")
                        # 売上変動要因（PER算定ベースへの直接影響）
                        if post_fin_rev < pre_fin_rev * 0.98:
                            _reasons_neg.append("売上減少による時価総額評価の下落")
                        elif post_fin_rev > pre_fin_rev * 1.10:
                            _reasons_pos.append(f"売上成長（+{(post_fin_rev/pre_fin_rev-1)*100:.0f}%）による企業価値上昇")
                        # ガバナンス低水準によるPERディスカウント
                        if c.governance_score <= 40:
                            _reasons_neg.append(f"ガバナンス低水準（{c.governance_score}/100）によるPERディスカウント")
                        # 資金調達・株式変動
                        _fund_delta = total_cash_delta - cash_flow_from_ops
                        if _fund_delta > 5:
                            _reasons_pos.append("資金調達による企業価値上昇")
                        # mktcap_mulイベント由来の変化：_score_change_reasons から "mktcap:" プレフィックスで抽出
                        for _scr in getattr(self, '_score_change_reasons', []):
                            if _scr.startswith('mktcap:'):
                                _label = _scr[len('mktcap:'):]
                                if mktcap_pct < 0:
                                    _reasons_neg.append(_label)
                                else:
                                    _reasons_pos.append(_label)
                        # 変動方向に合った理由を優先表示（方向と逆の理由は除外）
                        if mktcap_pct < 0:
                            _reasons = _reasons_neg if _reasons_neg else ["イベント・市場要因による時価総額評価の下方修正"]
                        else:
                            _reasons = _reasons_pos if _reasons_pos else ["イベント・市場要因による企業価値の上方修正"]
                        if not _reasons:
                            _reasons = ["業績動向・市場環境の総合的変化"]
                        _pct_str = f"+{mktcap_pct*100:.0f}%" if mktcap_pct >= 0 else f"{mktcap_pct*100:.0f}%"
                        _reason_text = "、".join(_reasons)
                        mr.append(
                            f'&nbsp;&nbsp;<span style="color:#aaa;font-size:0.9em">'
                            f'📝 前Q比{_pct_str}変動 — {esc(_reason_text)}</span>'
                        )
            if shr_delta != 0:
                mr.append(f'&nbsp;&nbsp;株主数：{c.shareholder_count}名 ({"+" if shr_delta>0 else ""}{shr_delta})')
            rows.append(
                f'<div class="qcr-section">'
                f'<div class="qcr-sh">🏢 企業価値</div>'
                f'<div class="qcr-sb">{"<br>".join(mr)}</div>'
                f'</div>'
            )

        # 6) ランウェイ警告
        rw = c.runway_quarters()
        rw_color = "#55dd99" if rw >= 8 else ("#ffaa55" if rw >= 4 else "#ff5566")
        rw_text = "資金十分" if rw >= 99 else (
            "余裕あり" if rw >= 8 else ("注意" if rw >= 4 else "⚠️ 資金枯渇間近"))
        rows.append(
            f'<div class="qcr-runway" style="color:{rw_color}">'
            f'📍 資金残存：{_rw_label(rw)} — {rw_text}'
            f'</div>'
        )

        # 7) 前Q比スコア変化（旧 _add_quarter_brief から移植）
        current_scores = self._get_score_snapshot()
        # _prev_scoresを更新前に保存（_actual_delta計算に使用）
        _old_prev_scores = dict(self._prev_scores) if self._prev_scores else {}
        score_change_lines = []
        if _old_prev_scores:
            for k, v in current_scores.items():
                prev = _old_prev_scores.get(k, v)
                diff = v - prev
                if abs(diff) >= 1:
                    sign = "+" if diff > 0 else ""
                    col = "#00dd88" if diff > 0 else "#ff4455"
                    score_change_lines.append(
                        f'<span style="color:{col};margin-right:10px">{k}: {prev}→{v}（{sign}{diff}）</span>'
                    )
        # _prev_* を更新（次ターン用）
        self._prev_cash   = c.cash
        self._prev_rev    = post_fin_rev
        self._prev_scores = current_scores
        # スコア変動要因をキャプチャしてリセット
        _captured_reasons = list(getattr(self, '_score_change_reasons', []))
        self._score_change_reasons = []

        if score_change_lines:
            rows.append(
                f'<div class="qcr-section">'
                f'<div class="qcr-sh">📊 前Q比 スコア変化</div>'
                f'<div class="qcr-sb" style="font-size:12px;padding:4px 0">{"".join(score_change_lines)}</div>'
            )
            # ── 変動要因の表示（全スコア変動を説明する） ──
            # 1) 実際のスコア変動量を集計（更新前の_prev_scoresを使用）
            _actual_delta = {}
            for k, v in current_scores.items():
                prev = _old_prev_scores.get(k, v)
                diff = v - prev
                if abs(diff) >= 1:
                    _actual_delta[k] = diff

            # 2) _captured_reasonsから説明済みの変動量を抽出
            _explained_delta = {}
            _score_name_re = _re.compile(r'(内統|会計|コンプラ|統治|監査信頼|投資家信頼|士気)([+\-])(\d+)')
            for r in _captured_reasons:
                for m in _score_name_re.finditer(r):
                    sn = m.group(1)
                    val = int(m.group(3)) * (1 if m.group(2) == '+' else -1)
                    _explained_delta[sn] = _explained_delta.get(sn, 0) + val

            # 3) 変動要因テキストをフィルタリング（変動スコアに関連するもののみ）
            # 上限100に到達して実際には変化しなかったが説明文に記述があるものも保持
            _capped_no_change = {}  # explained claims but actual delta == 0 (already at cap)
            for sn, claimed in _explained_delta.items():
                if sn not in _actual_delta and abs(claimed) >= 1:
                    _capped_no_change[sn] = claimed
            _appeared = set(_actual_delta.keys()) | set(_capped_no_change.keys())
            _reason_score_re = _re.compile(r'(内統|会計|コンプラ|統治|監査信頼|投資家信頼|士気)')
            def _filter_reason(r: str) -> str:
                """理由文が変動したスコアを1つ以上言及していれば全体を保持する。
                スコア記述なしの理由は常に保持。変動していないスコアだけの理由は除外。"""
                mentions = {m.group(1) for m in _reason_score_re.finditer(r)}
                if not mentions:
                    return r
                if mentions & _appeared:
                    return r
                return ''
            filtered_reasons = [fr for r in _captured_reasons
                                if (fr := _filter_reason(r))]

            # 上限100到達で未加算だったスコアを表示
            if _capped_no_change:
                _parts = ", ".join(
                    f"{sn}{'+'if v>=0 else ''}{v:.0f}（上限100到達のため未加算）"
                    for sn, v in _capped_no_change.items()
                )
                filtered_reasons.append(f"上限到達・未反映：{_parts}")

            # 4) 未説明の変動量を計算して表示ラベルを正しく分類する
            # ── ケース分類 ──────────────────────────────────────────────
            # 上限到達 : explained > 0、delta >= 0、delta < explained  (天井で一部吸収)
            # 下限到達 : explained < 0、delta <= 0、delta > explained  (床で一部吸収)
            # AGM繰延・ペナルティ : delta が実際に負（スコア減少）で未説明 or 説明と逆方向
            # 単純未説明正 : explained と delta が同符号で remainder > 0
            _cap_ceiling = {}      # 上限(100)に当たって未加算分
            _agm_penalties = {}    # AGM繰延・実際の減点（上限/下限と無関係）
            _unexplained_pos = {}  # 説明なしの正方向未説明
            for sn, delta in _actual_delta.items():
                explained = _explained_delta.get(sn, 0)
                remainder = delta - explained
                if abs(remainder) < 1:
                    continue
                # 真の上限到達：加算が天井で止まった（delta >= 0 かつ explained > delta）
                if explained > 0 and delta >= 0 and delta < explained:
                    _cap_ceiling[sn] = remainder        # remainder は負（= 吸収量）
                # 真の下限到達：減算が床で止まった（delta <= 0 かつ explained < delta）
                elif explained < 0 and delta <= 0 and delta > explained:
                    _cap_ceiling[sn] = remainder        # remainder は正（= 吸収量）
                # 実際に減点されているが説明なし／説明と逆方向（AGM繰延・ペナルティ等）
                elif delta < 0 or (explained != 0 and (remainder * delta < 0)):
                    _agm_penalties[sn] = remainder
                elif remainder > 0:
                    _unexplained_pos[sn] = remainder
            if _unexplained_pos:
                _parts = ", ".join(f"{sn}+{v:.0f}" for sn, v in _unexplained_pos.items())
                filtered_reasons.insert(0, f"イベント効果・体制整備：{_parts}")
            if _agm_penalties:
                _parts = ", ".join(f"{sn}{'+'if v>=0 else ''}{v:.0f}" for sn, v in _agm_penalties.items())
                filtered_reasons.insert(0, f"AGM繰延・ペナルティ等：{_parts}")
            if _cap_ceiling:
                _parts = ", ".join(f"{sn}{'+'if v>=0 else ''}{v:.0f}" for sn, v in _cap_ceiling.items())
                filtered_reasons.insert(0, f"上限(100)到達により一部未加算：{_parts}")

            if filtered_reasons:
                reasons_html = "<br>".join(
                    f'<span style="color:#9bc8e8">・{esc(r)}</span>'
                    for r in filtered_reasons
                )
                rows.append(
                    f'<div style="font-size:11px;color:#7aaccc;margin-top:4px;padding:4px 6px;'
                    f'border-left:2px solid #3a7aa0;background:rgba(0,0,0,.2)">'
                    f'<span style="font-weight:700;color:#9bc8e8">変動要因：</span><br>{reasons_html}</div>'
                )
            rows.append('</div>')
        else:
            rows.append(
                '<div class="qcr-section">'
                '<div class="qcr-sh">📊 前Q比 スコア変化</div>'
                '<div class="qcr-sb" style="font-size:12px;padding:4px 0;color:var(--dim)">変動なし</div>'
                '</div>'
            )

        # 8) 社長への課題報告 / 良好な点（旧 _add_quarter_brief から移植）
        risk = c.flags.total_risk_score
        issues, goods = [], []
        if risk >= 80:
            issues.append(f"🚨 累積リスクスコア {risk}/100 — 上場審査NG水域！リスクを下げる意思決定を最優先してください。")
        elif risk >= 70:
            issues.append(f"🔴 累積リスクスコア {risk}/100 — 危険域（70超）。次のN期申請前に60以下へ引き下げてください。")
        elif risk >= 60:
            issues.append(f"⚠ 累積リスクスコア {risk}/100 — 要注意（60超）。リスクの高い意思決定を避けてください。")
        if net_income < 0:
            detail = f"（うち一時費用¥{one_time_this_q:.0f}M含む）" if one_time_this_q >= 0.5 else ""
            issues.append(f"四半期純利益が赤字（▲¥{abs(net_income):.0f}M）{detail}。増収または費用削減が急務です。")
        if rw <= 4:
            issues.append(f"⚠ 資金残存が{rw}Qのみ！追加調達が急務です。")
        elif rw <= 8:
            issues.append(f"資金残存は{rw}Q。追加調達のタイミングを検討してください。")
        if c.auditor_trust <= 30:
            issues.append("⚠ 監査法人からの信頼が危険水域です。")
        if c.investor_trust <= 30:
            issues.append("投資家からの信頼が低下しています。")
        if t.n_period >= -1 and not c.has_underwriter:
            issues.append("⚠ 主幹事証券会社が未決定です！N期前に必ず確定させてください。")
        if not c.has_audit_contract and t.n_period >= -1:
            issues.append("⚠ 監査契約が未締結です！上場申請の必要条件です。")
        # 良好判定（リスク高時は上書きしない）
        if risk < 60:
            if c.internal_control_score >= 70 and c.compliance_score >= 70:
                goods.append("内部管理体制・コンプライアンスが良好な水準です。")
            if net_income > 0 and rw > 8:
                goods.append("収支・資金繰りともに健全です。")
        if issues:
            goods.clear()

        if issues:
            issue_rows = "".join(f'<div style="color:#ff8855;padding:2px 0;font-size:12px">⚠ {esc(i)}</div>' for i in issues)
            rows.append(
                f'<div class="qcr-section">'
                f'<div class="qcr-sh">📋 社長への課題報告</div>'
                f'<div class="qcr-sb">{issue_rows}</div>'
                f'</div>'
            )
        elif goods:
            good_rows = "".join(f'<div style="color:#55dd99;padding:2px 0;font-size:12px">✅ {esc(g)}</div>' for g in goods)
            rows.append(
                f'<div class="qcr-section">'
                f'<div class="qcr-sh">✅ 良好な点</div>'
                f'<div class="qcr-sb">{good_rows}</div>'
                f'</div>'
            )
        else:
            rows.append(
                f'<div style="color:#55dd99;padding:4px 0;font-size:12px">✅ 現時点で重大な課題はありません。</div>'
            )

        body = "".join(rows)
        self._add(
            f'<div class="quarter-closing-report">'
            f'<div class="qcr-title">📊 {esc(period_label)} 決算レポート</div>'
            f'<div class="qcr-body">{body}</div>'
            f'</div>',
            "report"
        )

    # ──────────────────────────────────────────
    # ターン開始
    # ──────────────────────────────────────────
    def _period_cls(self) -> str:
        return {-3: "green", -2: "green", -1: "green", 0: "green"}.get(
            self.timeline.n_period, "green"
        )

    # ──────────────────────────────────────────
    # 社長のモノローグ（テンション演出）
    # ──────────────────────────────────────────
    def _add_ceo_monologue(self):
        """ゲーム状態に応じたCEOのモノローグ・緊迫感演出"""
        c = self.company
        t = self.timeline
        q_left = t.quarters_until_ipo()
        rw = c.runway_quarters()
        rev = c.revenue.recognized
        net = rev - c.quarterly_burn

        # 危機レベル判定
        crisis_messages = []
        urgency_messages = []
        mood_class = "ceo-normal"

        # 資金ショート危機
        if rw <= 2:
            crisis_messages.append(
                f"「残り資金は{rw}四半期分しかない… このままでは上場前に会社が潰れる。\n"
                f"  今すぐ追加調達か、コスト削減を決断しなければ！」"
            )
            mood_class = "ceo-crisis"
        elif rw <= 4:
            crisis_messages.append(
                f"「資金が底をつきかけている。残り{rw}四半期。焦りを感じる…\n"
                f"  上場審査まで資金が持つか、綱渡りだ。」"
            )
            mood_class = "ceo-warning"

        # カウントダウン演出
        if q_left <= 4 and t.n_period == 0:
            urgency_messages.append(
                f"【🔴 申請期 残り{q_left}Q】上場審査まで秒読み！\n"
                f"  東証の審査官が審査書類を精査している。今期の決断が全てを決める。"
            )
            mood_class = "ceo-final"
        elif q_left <= 8:
            urgency_messages.append(
                f"【⚡ 残り{q_left}Q】上場審査が視野に入ってきた。\n"
                f"  積み上げてきた経営判断の結果が、まもなく東証の審査で問われる。"
            )
            if mood_class == "ceo-normal":
                mood_class = "ceo-tension"

        # スコア危機
        low_scores = [k for k, v in self._get_score_snapshot().items() if v < 30]
        if low_scores:
            urgency_messages.append(
                f"⚠ 危険水域のスコア: {', '.join(low_scores)}。\n"
                f"  このまま上場審査に臨めば、確実に指摘を受ける。"
            )

        # 株主数チェック
        req_map = {"growth": 150, "standard": 400, "prime": 800}
        shr_req = req_map.get(self.target_market, 150)
        if c.shareholder_count < shr_req and q_left <= 4:
            # N期に入ってからも公募・売出しが未実施なら警告（N期以前は通例少ない）
            urgency_messages.append(
                f"⚠ 実株主数が{c.shareholder_count}名（要件：{shr_req}名）。\n"
                f"  ただし株主数要件は上場申請後の公募・売出しで充足するのが実務上の通例。\n"
                f"  主幹事証券会社と連携して上場時公募・売出しを適切に設計することが重要です。\n"
                f"  ※SOは潜在株主のため要件にはカウントされません。"
            )

        # 好調メッセージ（N-3〜N-2）
        if not crisis_messages and not urgency_messages and net > 0 and t.n_period <= -2:
            greetings = [
                f"「売上は順調だ。でも上場審査はまだ先が長い。\n  一つ一つの決断を慎重に積み重ねよう。」",
                f"「{c.name}は今、着実に成長している。\n  しかし管理体制が追いついていなければ意味がない。」",
                f"「数字は良い。だが東証が見るのは数字だけじゃない。\n  ガバナンス・内部統制・コンプライアンス。三拍子そろってこそだ。」",
            ]
            import random as _r
            crisis_messages.append(_r.choice(greetings))

        all_messages = crisis_messages + urgency_messages
        if all_messages:
            body = "<br>".join(
                f'<span class="mono-line">{esc(m)}</span>' for m in all_messages
            )
            self._add(
                f'<div class="ceo-monologue {mood_class}">'
                f'<span class="mono-icon">👤</span>'
                f'<div class="mono-body">{body}</div>'
                f'</div>'
            )

    def _process_agm_deferred(self):
        """前期定時株主総会で可決された定款変更の登記完了処理。
        定款変更は総会特別決議後、法務局への登記手続きに数週間を要する（会社法466条）。
        社外役員・会計監査人の選任はAGMがQ1開催になったため総会当日即時就任に変更済み。"""
        c = self.company

        if c.agm_deferred_articles_amendment:
            c.agm_deferred_articles_amendment = False
            c.has_articles_amendment = True
            c.compliance_score = min(100, c.compliance_score + 8)
            body = (
                "📄 N-1期定時株主総会の特別決議で承認された定款変更が<strong>法務局への登記を完了</strong>しました。<br><br>"
                "▶ コンプラ+8・定款変更 ✅<br>"
                "【会社法466条】定款変更は株主総会の特別決議（2/3以上）が必要。<br>"
                "登記完了により効力が確定します（申請から通常2〜3週間）。"
            )
            self._add(story_panel(body, "📋 定款変更 登記完了", "cyan"))
            self._score_change_reasons.append("📄 定款変更登記完了：コンプラ+8")

    def _map_jump(self, steps: int, label: str = "🚀 一気に前進！"):
        """🗺 ワールドマップ：コマを前進させる（切り札等のポジティブ演出）"""
        cur = getattr(self, "_map_pos", 0)
        to = min(MAP_GOAL_TILE - 1, cur + steps)
        if to <= cur:
            return
        self._map_pos = to
        self._add(map_move_html(cur, to, label, **self._rival_static()), "map_move")

    # ──────────────────────────────────────────
    # 🃏 社長の切り札（1ゲーム1回・逆転カード）
    # ──────────────────────────────────────────
    def _trump_media(self, c: Company) -> str:
        self._trump_used = True
        c.cash -= 30.0
        c.investor_trust = min(100, c.investor_trust + 10)
        c.market_index = min(95.0, getattr(c, "market_index", 55.0) + 8.0)
        self._map_jump(2, "📰 知名度急上昇 — 2マス前進！")
        return (
            "📰 全国メディアでの戦略的広報キャンペーンを展開しました。（¥30M）\n\n"
            "   テレビ・経済誌・SNSで自社の成長ストーリーが話題に。\n"
            "   ▶ 投資家信頼+10 / 市況指数+8 / 🗺 2マス前進\n\n"
            "   ▶ 【実務】上場前の広報は「上場準備に関する事実の公表」に\n"
            "     とどめる必要があります（推奨・勧誘と受け取られる表現はNG）。\n"
            "     計画的なIR・PR戦略は知名度と公募需要の形成に有効です。"
        )

    def _trump_alliance(self, c: Company) -> str:
        self._trump_used = True
        c.growth_perm_delta = getattr(c, "growth_perm_delta", 0.0) + 0.02
        c.offense_score = getattr(c, "offense_score", 0) + 1
        c.flags.total_risk_score += 8
        self._map_jump(3, "🤝 大型提携発表 — 3マス前進！")
        return (
            "🤝 業界大手との資本業務提携を電撃発表しました。\n\n"
            "   販路・技術の両面で成長が加速します。\n"
            "   ▶ 成長率+2pt（恒久） / 🚀 事業投資+1 / 🗺 3マス前進\n"
            "   ▶ リスクスコア+8\n\n"
            "   ▶ 【実務】資本提携先との取引は「関連当事者取引」として\n"
            "     上場審査で整理・開示が求められます。提携の経済合理性と\n"
            "     取引条件の妥当性を説明できる準備が必要です。"
        )

    def _trump_headhunt(self, c: Company) -> str:
        self._trump_used = True
        rv = getattr(self, "_rival", None)
        r_from = rv["pos"] if rv else -1
        if rv:
            rv["pos"] = max(0, rv["pos"] - 3)
        cur = getattr(self, "_map_pos", 0)
        to = min(MAP_GOAL_TILE - 1, cur + 1)
        self._map_pos = to
        self._add(map_move_html(cur, to, "🕵 引き抜き成功 — ライバル3マス後退！",
                                r_from=r_from, r_to=(rv["pos"] if rv else -1),
                                r_fall=True, r_name=(rv["name"] if rv else "")), "map_move")
        if _rand.random() < 0.50:
            c.flags.total_risk_score += 12
            c.investor_trust = max(0, c.investor_trust - 10)
            c.employee_morale = max(0, c.employee_morale - 5)
            return (
                "🕵 ライバルのキーパーソン引き抜きに成功——しかし発覚しました。\n\n"
                f"   {rv['name'] if rv else 'ライバル'}のCTOを獲得し、相手の上場準備は大きく後退。\n"
                "   ▶ 🗺 自社1マス前進 / ライバル3マス後退\n\n"
                "   ⚠ しかし業界紙に「強引な引き抜き」と報じられ紛争に発展。\n"
                "   ▶ リスクスコア+12 / 投資家信頼-10 / 従業員士気-5\n"
                "   ▶ 【実務】競業避止義務・秘密保持契約をめぐる紛争は\n"
                "     上場審査の「係争リスク」として開示・説明が求められます。"
            )
        return (
            "🕵 ライバルのキーパーソン引き抜きに成功しました。\n\n"
            f"   {rv['name'] if rv else 'ライバル'}のCTOを獲得。相手の上場準備は大きく後退しました。\n"
            "   ▶ 🗺 自社1マス前進 / ライバル3マス後退\n"
            "   ▶ 紛争にもならず、クリーンな移籍として処理されました。\n\n"
            "   ▶ 【実務】人材獲得自体は正当な競争ですが、競業避止義務・\n"
            "     営業秘密の持ち込みには細心の注意が必要です。"
        )

    def _trump_pass(self, c: Company) -> str:
        return (
            "⚖ 切り札は使わず、正攻法を貫くことにしました。\n\n"
            "   「小手先の逆転より、審査に耐える体制づくりだ。」\n"
            "   ▶ 切り札は温存されました。レース状況次第で再び検討できます。"
        )

    def _build_trump_event(self) -> GameEvent:
        rv = getattr(self, "_rival", None)
        rname = rv["name"] if rv else "ライバル社"
        rpos = rv["pos"] if rv else 0
        mypos = getattr(self, "_map_pos", 0)
        return GameEvent(
            id="trump_card",
            title=f"⚡ 緊急取締役会 — 社長の切り札（1回限り）",
            description=(
                f"CFOが緊急の取締役会を招集しました。\n\n"
                f"「社長、{rname}が山頂に迫っています（相手{rpos}マス目／当社{mypos}マス目）。\n"
                f"先に上場されれば、当社の評価額は15%下がります。\n\n"
                f"ここで使える『切り札』は一度きり。どれも実務上のリスクと\n"
                f"隣り合わせですが——decision time です、社長。」\n\n"
                f"【ポイント】逆転手段にもそれぞれ審査上の論点（広報規制・関連当事者・\n"
                f"人材紛争）が付きまといます。リスクとリターンを天秤にかけてください。"
            ),
            choices=[
                Choice(
                    label="A. 📰 メディア戦略・知名度キャンペーン（¥30M）",
                    description="全国メディアで成長ストーリーを発信。確実だが効果は中程度",
                    immediate_effect=lambda c: self._trump_media(c),
                    risk_hint="ローリスク：自社+2マス / 投資家信頼+10 / 市況+8",
                ),
                Choice(
                    label="B. 🤝 大型アライアンス電撃発表（資本業務提携）",
                    description="業界大手と提携し成長を加速。関連当事者取引の論点が増える",
                    immediate_effect=lambda c: self._trump_alliance(c),
                    risk_hint="ミドルリスク：自社+3マス / 成長+2pt恒久 / リスク+8",
                ),
                Choice(
                    label="C. 🕵 ライバルのキーパーソン引き抜き",
                    description="相手の上場準備を直接遅らせる。ただし50%で紛争に発展",
                    immediate_effect=lambda c: self._trump_headhunt(c),
                    risk_hint="ハイリスク：ライバル-3マス＋自社+1。50%で紛争（リスク+12等）",
                ),
                Choice(
                    label="D. ⚖ 正攻法を貫く（切り札を温存）",
                    description="今は使わない。条件を満たせば後のターンで再検討できる",
                    immediate_effect=lambda c: self._trump_pass(c),
                ),
            ],
            min_n_period=-3,
            max_n_period=0,
            one_shot=True,
        )

    # ──────────────────────────────────────────
    # ⏳ タイマークライシス：共通フレームワーク
    # ──────────────────────────────────────────
    def _build_crisis_event(self, crisis: dict) -> GameEvent:
        """crisis = {"kind": "...", "remaining": N} からGameEventを生成する"""
        builders = {
            "cfo_successor": self._build_cfo_successor_crisis_event,
            "data_leak_report": self._build_data_leak_crisis_event,
            "bcp_recovery": self._build_bcp_recovery_crisis_event,
            "labor_compliance": self._build_labor_compliance_crisis_event,
        }
        return builders[crisis["kind"]](crisis)

    def _crisis_postpone(self, crisis: dict, expire_label: str, expire_fn) -> str:
        """先送りの共通処理。期限切れ時は expire_fn() を呼んでクライシスを除去する。"""
        crisis["remaining"] -= 1
        if crisis["remaining"] <= 0:
            if crisis in self._timer_crises:
                self._timer_crises.remove(crisis)
            self._map_fall(1, f"⚠ {expire_label} 期限切れ — 後退…")
            return expire_fn()
        return (
            f"⏳ 対応を先送りしました。\n\n"
            f"   ・対応できる期数は残り{crisis['remaining']}期です。"
        )

    # ──────────────────────────────────────────
    # ⏳ タイマークライシス：後任CFO選定
    # ──────────────────────────────────────────
    def _build_cfo_successor_crisis_event(self, crisis: dict) -> GameEvent:
        remaining = crisis["remaining"]
        return GameEvent(
            id="cfo_successor_crisis",
            title=f"⏳ タイマークライシス：後任CFO選定（残り{remaining}期）",
            description=(
                "CFO逮捕以降、経理部長がCFO職務を代行していますが、これは応急的な体制です。\n\n"
                "主幹事証券会社・監査法人からは「後任CFOを選任し、財務責任者の体制を\n"
                "正式に再構築してほしい」との要請が繰り返し届いています。\n\n"
                f"このまま対応を先送りできるのは、あと{remaining}期までです。\n"
                "期限を過ぎても代行体制が続く場合、Ⅰの部作成・内部統制報告に遅れが生じ、\n"
                "上場準備の後退は避けられません。"
            ),
            choices=[
                Choice(
                    label="A. 後任CFOを選任する（¥30M）",
                    description="財務責任者の体制を正式に再構築し、クライシスを解消する",
                    immediate_effect=lambda c: self._resolve_cfo_successor(c, crisis),
                ),
                Choice(
                    label="B. 先送りする（経理部長代行を継続）",
                    description="コストはかからないが、対応できる期数が1つ減る",
                    immediate_effect=lambda c: self._postpone_cfo_successor(c, crisis),
                ),
            ],
            min_n_period=-3,
            max_n_period=0,
            one_shot=False,
        )

    def _resolve_cfo_successor(self, c: Company, crisis: dict) -> str:
        c.cash -= 30
        c.internal_control_score = min(100, c.internal_control_score + 10)
        c.investor_trust = min(100, c.investor_trust + 5)
        if crisis in self._timer_crises:
            self._timer_crises.remove(crisis)
        return (
            "🧑‍💼 後任CFOの選任が完了しました。（¥30M）\n\n"
            "   ・経理部長による代行体制を解消し、財務責任者の体制を正式に再構築しました。\n"
            "   ・内部統制+10 / 投資家信頼+5\n\n"
            "   ▶ タイマークライシス「後任CFO選定」は解消されました。"
        )

    def _postpone_cfo_successor(self, c: Company, crisis: dict) -> str:
        def _expire():
            c.flags.total_risk_score += 15
            c.investor_trust = max(0, c.investor_trust - 10)
            return (
                "⚠️ 後任CFO選定が期限切れとなりました。\n\n"
                "   ・経理部長代行体制の長期化により、Ⅰの部作成・内部統制報告に遅れが生じました。\n"
                "   ・リスクスコア+15 / 投資家信頼-10\n\n"
                "   ▶ ワールドマップ：1マス後退"
            )
        return self._crisis_postpone(crisis, "後任CFO選定", _expire)

    # ──────────────────────────────────────────
    # ⏳ タイマークライシス：個人情報漏洩 再発防止策の策定
    # ──────────────────────────────────────────
    def _build_data_leak_crisis_event(self, crisis: dict) -> GameEvent:
        remaining = crisis["remaining"]
        return GameEvent(
            id="data_leak_report_crisis",
            title=f"⏳ タイマークライシス：個人情報漏洩 再発防止策の策定（残り{remaining}期）",
            description=(
                "先日発生した個人情報漏洩について、監督官庁・利用者への対応はまだ完了していません。\n\n"
                "個人情報保護法に基づき、監督官庁への報告と再発防止策の策定・公表が\n"
                "求められています。\n\n"
                f"対応を先送りできるのは、あと{remaining}期までです。\n"
                "対応が遅れれば行政指導の対象となり、企業イメージの悪化はライバル企業にとって\n"
                "追い風となります。"
            ),
            choices=[
                Choice(
                    label="A. 報告書を提出し、再発防止策を実施する（¥12M）",
                    description="監督官庁への報告を完了し、再発防止策を公表する",
                    immediate_effect=lambda c: self._resolve_data_leak_report(c, crisis),
                ),
                Choice(
                    label="B. 先送りする（対応を保留）",
                    description="コストはかからないが、対応できる期数が1つ減る",
                    immediate_effect=lambda c: self._postpone_data_leak_report(c, crisis),
                ),
            ],
            min_n_period=-3,
            max_n_period=0,
            one_shot=False,
        )

    def _resolve_data_leak_report(self, c: Company, crisis: dict) -> str:
        c.cash -= 12
        c.compliance_score = min(100, c.compliance_score + 10)
        c.internal_control_score = min(100, c.internal_control_score + 5)
        c.flags.total_risk_score = max(0, c.flags.total_risk_score - 5)
        if crisis in self._timer_crises:
            self._timer_crises.remove(crisis)
        return (
            "📄 監督官庁への報告と再発防止策の公表を完了しました。（¥12M）\n\n"
            "   ・コンプライアンス+10 / 内部統制+5 / リスクスコア-5\n\n"
            "   ▶ タイマークライシス「個人情報漏洩 再発防止策の策定」は解消されました。"
        )

    def _postpone_data_leak_report(self, c: Company, crisis: dict) -> str:
        def _expire():
            c.compliance_score = max(0, c.compliance_score - 15)
            c.investor_trust = max(0, c.investor_trust - 10)
            c.flags.total_risk_score += 15
            _rv = getattr(self, "_rival", None)
            rival_msg = ""
            if _rv and not _rv["listed"]:
                _rv["pos"] += 1
                rival_msg = f"\n   ・企業イメージの悪化により、{_rv['name']}が1マス前進しました。"
            return (
                "⚠️ 個人情報漏洩への対応が期限切れとなりました。\n\n"
                "   ・監督官庁から行政指導を受け、コンプライアンス-15 / 投資家信頼-10 / リスクスコア+15"
                f"{rival_msg}\n\n"
                "   ▶ ワールドマップ：1マス後退"
            )
        return self._crisis_postpone(crisis, "個人情報漏洩 再発防止策の策定", _expire)

    # ──────────────────────────────────────────
    # ⏳ タイマークライシス：BCP見直し・拠点復旧
    # ──────────────────────────────────────────
    def _build_bcp_recovery_crisis_event(self, crisis: dict) -> GameEvent:
        remaining = crisis["remaining"]
        return GameEvent(
            id="bcp_recovery_crisis",
            title=f"⏳ タイマークライシス：BCP見直し・拠点復旧（残り{remaining}期）",
            description=(
                "被災した拠点の復旧、および事業継続計画（BCP）の見直しはまだ完了していません。\n\n"
                "復旧投資を行わなければ、被災の影響が業績に長引くおそれがあります。\n\n"
                f"対応を先送りできるのは、あと{remaining}期までです。"
            ),
            choices=[
                Choice(
                    label="A. 復旧投資を実施し、BCPを見直す（¥20M）",
                    description="拠点の復旧とBCP見直しを完了し、クライシスを解消する",
                    immediate_effect=lambda c: self._resolve_bcp_recovery(c, crisis),
                ),
                Choice(
                    label="B. 先送りする（復旧を保留）",
                    description="コストはかからないが、対応できる期数が1つ減る",
                    immediate_effect=lambda c: self._postpone_bcp_recovery(c, crisis),
                ),
            ],
            min_n_period=-3,
            max_n_period=0,
            one_shot=False,
        )

    def _resolve_bcp_recovery(self, c: Company, crisis: dict) -> str:
        c.cash -= 20
        c.employee_morale = min(100, c.employee_morale + 10)
        c.market_cap_million = max(100.0, c.market_cap_million * 1.05)
        c.flags.total_risk_score = max(0, c.flags.total_risk_score - 5)
        if crisis in self._timer_crises:
            self._timer_crises.remove(crisis)
        return (
            "🏗️ 拠点の復旧投資とBCPの見直しを完了しました。（¥20M）\n\n"
            "   ・士気+10 / 時価総額+5% / リスクスコア-5\n\n"
            "   ▶ タイマークライシス「BCP見直し・拠点復旧」は解消されました。"
        )

    def _postpone_bcp_recovery(self, c: Company, crisis: dict) -> str:
        def _expire():
            c.investor_trust = max(0, c.investor_trust - 10)
            c.market_cap_million = max(100.0, c.market_cap_million * 0.95)
            c.flags.total_risk_score += 10
            return (
                "⚠️ BCP見直し・拠点復旧への対応が期限切れとなりました。\n\n"
                "   ・復旧の遅れにより売上回復が長引き、投資家信頼-10 / 時価総額-5% / リスクスコア+10\n\n"
                "   ▶ ワールドマップ：1マス後退"
            )
        return self._crisis_postpone(crisis, "BCP見直し・拠点復旧", _expire)

    # ──────────────────────────────────────────
    # ⏳ タイマークライシス：労務改善・コンプライアンス体制の報告
    # ──────────────────────────────────────────
    def _build_labor_compliance_crisis_event(self, crisis: dict) -> GameEvent:
        remaining = crisis["remaining"]
        return GameEvent(
            id="labor_compliance_crisis",
            title=f"⏳ タイマークライシス：労務改善・コンプライアンス体制の報告（残り{remaining}期）",
            description=(
                "従業員からの告発を受けた労務問題について、改善報告はまだ完了していません。\n\n"
                "主幹事証券会社・監査法人へ改善報告を行わなければ、信頼低下が続くおそれがあります。\n\n"
                f"対応を先送りできるのは、あと{remaining}期までです。"
            ),
            choices=[
                Choice(
                    label="A. 改善報告を提出する（¥10M）",
                    description="労務改善・コンプライアンス体制の報告を完了し、クライシスを解消する",
                    immediate_effect=lambda c: self._resolve_labor_compliance(c, crisis),
                ),
                Choice(
                    label="B. 先送りする（報告を保留）",
                    description="コストはかからないが、対応できる期数が1つ減る",
                    immediate_effect=lambda c: self._postpone_labor_compliance(c, crisis),
                ),
            ],
            min_n_period=-3,
            max_n_period=0,
            one_shot=False,
        )

    def _resolve_labor_compliance(self, c: Company, crisis: dict) -> str:
        c.cash -= 10
        c.compliance_score = min(100, c.compliance_score + 10)
        c.employee_morale = min(100, c.employee_morale + 8)
        c.auditor_trust = min(100, c.auditor_trust + 5)
        if crisis in self._timer_crises:
            self._timer_crises.remove(crisis)
        return (
            "📋 労務改善・コンプライアンス体制の報告を完了しました。（¥10M）\n\n"
            "   ・コンプライアンス+10 / 士気+8 / 監査信頼+5\n\n"
            "   ▶ タイマークライシス「労務改善・コンプライアンス体制の報告」は解消されました。"
        )

    def _postpone_labor_compliance(self, c: Company, crisis: dict) -> str:
        def _expire():
            c.compliance_score = max(0, c.compliance_score - 10)
            c.auditor_trust = max(0, c.auditor_trust - 10)
            c.flags.total_risk_score += 10
            return (
                "⚠️ 労務改善・コンプライアンス体制の報告が期限切れとなりました。\n\n"
                "   ・主幹事証券会社・監査法人からの信頼低下により、"
                "コンプライアンス-10 / 監査信頼-10 / リスクスコア+10\n\n"
                "   ▶ ワールドマップ：1マス後退"
            )
        return self._crisis_postpone(crisis, "労務改善・コンプライアンス体制の報告", _expire)

    def _rival_static(self) -> dict:
        """🏁 マップ演出にライバルを静止表示するためのパラメータ"""
        rv = getattr(self, "_rival", None)
        if not rv:
            return {}
        return {"r_from": rv["pos"], "r_to": rv["pos"], "r_name": rv["name"]}

    def _map_fall(self, steps: int = 1, label: str = "⚠ 転落！"):
        """🗺 ワールドマップ：コマを後退させる（悪い出来事の演出）"""
        cur = getattr(self, "_map_pos", 0)
        to = max(0, cur - steps)
        if to == cur:
            return
        self._map_pos = to
        self._add(map_move_html(cur, to, label, fall=True, **self._rival_static()), "map_move")

    def _map_goal(self):
        """🗺 ワールドマップ：山頂の鐘へ（上場成功）"""
        cur = getattr(self, "_map_pos", 0)
        self._map_pos = MAP_GOAL_TILE
        self._add(map_move_html(cur, MAP_GOAL_TILE, "🔔 登頂 — 上場達成！", goal=True,
                                **self._rival_static()), "map_move")

    def _begin_turn(self):
        c = self.company
        t = self.timeline
        self._closing_period = None  # 前ターンの年度末遷移表示をリセット

        # ── 上場延期後の監査ルーレット再挑戦 ──
        if getattr(self, '_audit_retry_pending', False):
            self._audit_retry_pending = False
            self._add(story_rule("◆ 1年間の体制整備完了 — 監査法人への再打診 ◆", "yellow"))
            self._add(story_panel(
                "1年間の集中整備を経て、体制は大幅に改善されました。<br><br>"
                "改めて監査法人への受嘱打診を行います。<br>"
                "今回の成功確率は体制整備の成果に応じて上昇しています。",
                "🔄 監査契約 — 再挑戦", "yellow"
            ))
            self._run_audit_roulette()
            return

        # ── 🏁 ライバルの進行（マップ表示前に算出し、同じマップ演出で見せる）──
        _rv = getattr(self, "_rival", None)
        _r_from = _r_to = -1
        _r_fall = False
        _r_news = ""        # マップ表示後に流すニュース
        _r_name = _rv["name"] if _rv else ""
        if _rv is not None and _rv["listed"]:
            _r_from = _r_to = MAP_GOAL_TILE   # 上場済み：山頂に静止表示
        if _rv is not None and not _rv["listed"]:
            _r_from = _rv["pos"]
            _tidx_check = (t.n_period + 3) * 4 + (t.quarter - 1)
            # 🚀 前Qにプレイヤーが事業投資を実行していたら、ライバルのシェアを奪える
            _off_now = getattr(c, "offense_score", 0)
            _off_prev = getattr(self, "_prev_offense_for_rival", 0)
            self._prev_offense_for_rival = _off_now
            if _tidx_check > 0:   # 開幕ターンはライバルも麓で待機
                if _off_now > _off_prev and _rand.random() < 0.35:
                    # 御社の攻勢が直撃 → ライバル後退
                    _r_steps = 1 if _rand.random() < 0.7 else 2
                    _rv["pos"] = max(0, _rv["pos"] - _r_steps)
                    _r_fall = True
                    _r_news = (
                        f"📰 <strong>御社の攻勢が{esc(_rv['name'])}を直撃！</strong><br><br>"
                        f"先の事業投資が市場で高く評価され、{esc(_rv['name'])}から"
                        f"顧客・人材が流出しています。<br>"
                        f"▶ ライバルは{_r_steps}マス後退しました。攻めの経営が差を生みます。"
                    )
                elif _rand.random() < 0.12:
                    # 不祥事報道 → 滑落
                    _r_steps = _rand.randint(2, 4)
                    _rv["pos"] = max(0, _rv["pos"] - _r_steps)
                    _r_fall = True
                    _r_news = (
                        f"📰 <strong>{esc(_rv['name'])}に不祥事報道！</strong><br><br>"
                        f"競合の{esc(_rv['name'])}で内部管理体制の不備が報じられ、"
                        f"上場準備が後退している模様です。<br>"
                        f"▶ ライバルは{_r_steps}マス後退しました。"
                    )
                else:
                    _roll = _rand.random()
                    _r_steps = 1 if _roll < 0.15 else (2 if _roll < 0.65 else 3)
                    _rv["pos"] = min(MAP_GOAL_TILE, _rv["pos"] + _r_steps)
                    if _r_steps >= 3:
                        # 大きく前進した時のニュース（パターンをランダムに変える）
                        _r_news = _rand.choice([
                            (f"📰 <strong>{esc(_rv['name'])}が急成長！</strong><br><br>"
                             f"競合の{esc(_rv['name'])}が大型契約を獲得し、"
                             f"上場準備を加速させています。<br>"
                             f"▶ ライバルは{_r_steps}マス前進しました。先を越されるかもしれません。"),
                            (f"📰 <strong>{esc(_rv['name'])}、大型資金調達を完了！</strong><br><br>"
                             f"有力VCから大型出資を受け、{esc(_rv['name'])}は採用と開発を"
                             f"一気に拡大しています。<br>"
                             f"▶ ライバルは{_r_steps}マス前進。資金力で押し切られるかもしれません。"),
                            (f"📰 <strong>{esc(_rv['name'])}が監査法人と契約、主幹事も内定か</strong><br><br>"
                             f"業界紙によると{esc(_rv['name'])}の上場準備体制が整いつつあり、"
                             f"証券会社の引受審査も順調と報じられています。<br>"
                             f"▶ ライバルは{_r_steps}マス前進。着実に山頂へ近づいています。"),
                            (f"📰 <strong>{esc(_rv['name'])}のCEO、メディアで上場へ意欲</strong><br><br>"
                             f"経済番組に出演した{esc(_rv['name'])}のCEOが「上場は時間の問題」と発言。"
                             f"市場の注目が集まっています。<br>"
                             f"▶ ライバルは{_r_steps}マス前進しました。"),
                        ])
                if _rv["pos"] >= MAP_GOAL_TILE:
                    _rv["listed"] = True
                    c.rival_listed_first = True
                    # 自社が山頂近く（20マス以上）まで迫っていれば影響は限定的（-15%→-7%）
                    _near_summit = getattr(self, "_map_pos", 0) >= 20
                    c.rival_discount = 0.93 if _near_summit else 0.85
                    mkt_lbl = {"growth": "グロース", "standard": "スタンダード", "prime": "プライム"}.get(self.target_market, "グロース")
                    _r_news = (
                        f"📰 <strong>【速報】{esc(_rv['name'])}、東証{esc(mkt_lbl)}市場に上場！</strong><br><br>"
                        f"ライバルに先を越されました。同業IPOの新鮮味が薄れ、<br>"
                        f"投資家の関心が分散します。<br><br>"
                        + (
                            f"▶ ただし御社も山頂目前（{getattr(self, '_map_pos', 0)}マス目）。"
                            f"市場は「次はこの会社」と認知しており、<br>"
                            f"<strong>ディスカウントは -7% に軽減</strong>されます。<br>"
                            if _near_summit else
                            f"▶ <strong>御社の時価総額評価に -15% のディスカウント</strong>が掛かります。<br>"
                        )
                        + f"▶ それでも山頂は待っています。自社のペースで登り切りましょう。"
                    )
            _r_to = _rv["pos"]

        # ── 🗺 ワールドマップ：今四半期のマスへコマを進める ──
        _tidx = (t.n_period + 3) * 4 + (t.quarter - 1)
        if 0 <= _tidx < len(MAP_TILE_FOR_TURN):
            _target = MAP_TILE_FOR_TURN[_tidx]
            _cur = getattr(self, "_map_pos", 0)
            if _tidx == 0:
                self._map_pos = 0
                self._add(map_move_html(0, 0, f"{t.full_label()} — 栄光への旅、開幕", intro=True,
                                        r_from=0, r_to=0, r_name=_r_name), "map_move")
            elif _target > _cur:
                self._add(map_move_html(_cur, _target, f"{t.full_label()} へ出発！",
                                        r_from=_r_from, r_to=_r_to, r_fall=_r_fall,
                                        r_name=_r_name), "map_move")
                self._map_pos = _target
            # 🏁 ライバルのニュースはマップ演出の直後に表示
            if _r_news:
                self._add(story_panel(_r_news, f"📰 業界ニュース — 上場レース", "yellow"), "event_panel")

        # ─ 従業員持株会：毎Q+3名の実株主が積み上がる ─
        if getattr(c, 'has_esop', False):
            c.shareholder_count += 3

        # ─ Q1開始時にYTD累計をリセット（前期通年実績を保存してからリセット） ─
        if t.quarter == 1:
            self._prev_year_net = (
                getattr(self, "_ytd_rev", 0.0)
                - getattr(self, "_ytd_burn", 0.0)
                - getattr(self, "_ytd_otc", 0.0)
            )
            self._ytd_rev  = 0.0
            self._ytd_burn = 0.0
            self._ytd_otc  = 0.0

        # ─ ターン開始時の財務スナップショット（決算レポート用） ─
        self._turn_start_cash         = c.cash
        self._turn_start_burn         = c.quarterly_burn
        self._turn_start_rev          = c.revenue.recognized
        self._turn_start_mktcap       = c.market_cap_million
        self._turn_start_shareholders = c.shareholder_count
        self._turn_decisions          = []

        self._add(story_rule(
            f"{t.period_name()} — {t.full_label()}  残り{t.quarters_until_ipo()}Q",
            self._period_cls()
        ))

        # ── 前Q意思決定の遅延結果レポートを冒頭に表示 ──
        if self._deferred_outcomes:
            for (ev_title, ch_label, res_msg, good) in self._deferred_outcomes:
                res_msg = _strip_score_lines(res_msg)
                icon = "✅" if good else "⚠️"
                border = "#00cc66" if good else "#ff6644"
                header_color = "#00ffaa" if good else "#ff8866"
                self._add(
                    f'<div class="deferred-outcome" style="border-left:5px solid {border};'
                    f'background:rgba(255,255,255,.07);padding:12px 16px;margin-bottom:8px;border-radius:4px;'
                    f'box-shadow:0 0 10px rgba(0,0,0,.3);">'
                    f'<div style="font-size:14px;font-weight:800;color:{header_color};margin-bottom:6px;'
                    f'letter-spacing:.5px;text-shadow:0 0 4px rgba(0,0,0,.5)">'
                    f'📋 前Q意思決定の結果報告 — {esc(ev_title)}</div>'
                    f'<div style="font-size:12px;font-weight:700;margin-bottom:4px">'
                    f'{icon} {esc(ch_label.lstrip("ABCD. ")[:60])}</div>'
                    f'<div class="do-text" style="font-size:12px;color:{"#99ffcc" if good else "#ffaa88"}">'
                    f'{esc(res_msg).replace(chr(10), "<br>")}</div>'
                    f'</div>'
                )
            # AIドラマ：複数の意思決定結果をまとめて1回のGemini呼び出しで生成
            ai_drama = self._call_gemini_outcome_batch(self._deferred_outcomes)
            if ai_drama:
                drama_border = "#00cc66" if all(g for _, _, _, g in self._deferred_outcomes) else "#ff4455"
                drama_icon = "✨" if all(g for _, _, _, g in self._deferred_outcomes) else "💔"
                drama_color = "#c8f0c8" if all(g for _, _, _, g in self._deferred_outcomes) else "#ffd0d0"
                self._add(
                    f'<div class="ai-drama" style="border-left-color:{drama_border}">'
                    f'<div class="aid-header">{drama_icon} その後の展開</div>'
                    f'<div class="aid-body" style="color:{drama_color}">'
                    f'{esc(ai_drama).replace(chr(10), "<br>")}'
                    f'</div></div>'
                )
            self._deferred_outcomes.clear()

        # AIナラティブ（Gemini or ルールベース）
        self._add_situation_narrative()

        # 緊急体制整備カウントダウン処理
        if getattr(self, '_audit_emergency_countdown', 0) > 0:
            self._audit_emergency_countdown -= 1
            if self._audit_emergency_countdown == 0:
                self._run_audit_emergency_result()
                return

        if check_cash_crisis(c):
            self._show_ending("bankruptcy", [])
            return
        if c.investor_trust <= 5 or c.auditor_trust <= 5:
            self._show_ending("dismissed", [])
            return
        # クライシスカスケードチェック（連鎖破綻・強制上場延期）
        if self._check_crisis_cascade():
            return

        # 上場審査10論点に基づく突発的警告イベント
        self._check_spontaneous_audit_warnings()

        ipo_events = get_available_events(c, t.n_period, self._game_events, quarter=t.quarter)

        # N-1期冒頭：社外役員警告後フラグが立っていればEVENT_OUTSIDE_DIRECTOR_N1を先頭挿入
        if self._force_outside_director_n1 and t.n_period == -1:
            from scenario.ipo_knowledge import EVENT_OUTSIDE_DIRECTOR_N1
            ipo_events = [e for e in ipo_events if getattr(e, 'id', '') != 'outside_director_urgent']
            ipo_events.insert(0, EVENT_OUTSIDE_DIRECTOR_N1)
            self._force_outside_director_n1 = False

        # N-1期Q1：主幹事未選定なら強制注入（N-2期警告後のラストチャンス）
        if (t.n_period == -1 and t.quarter == 1
                and not c.has_underwriter):
            _uw_evt = next((e for e in self._game_events
                            if getattr(e, 'id', '') == 'underwriter_selection'), None)
            if _uw_evt and not any(getattr(e, 'id', '') == 'underwriter_selection' for e in ipo_events):
                # one_shot で fired=True になっていても強制再注入（先送り後のラストチャンス）
                _uw_evt.fired = False
                ipo_events.insert(0, _uw_evt)

        # N-1期：インサイダー取引防止規程が未整備なら必ず意思決定機会を提供（チェックリスト整合性）
        if (t.n_period == -1 and t.quarter == 1
                and not c.has_insider_prevention):
            from scenario.ipo_knowledge import EVENT_INSIDER_TRADING
            if not getattr(EVENT_INSIDER_TRADING, 'fired', False) \
                    and not any(getattr(e, 'id', '') == 'insider_trading_prevention' for e in ipo_events):
                ipo_events.insert(0, EVENT_INSIDER_TRADING)

        # N期：N-1期AGMで定款変更が否決されている場合、臨時株主総会イベントを強制注入
        if (t.n_period == 0
                and getattr(c, 'articles_amendment_rejected_needs_eogm', False)
                and not c.has_articles_amendment
                and not c.agm_deferred_articles_amendment):
            from scenario.ipo_knowledge import EVENT_EOGM_ARTICLES_AMENDMENT
            if not any(getattr(e, 'id', '') == 'eogm_articles_amendment' for e in ipo_events):
                if not getattr(EVENT_EOGM_ARTICLES_AMENDMENT, 'fired', False):
                    ipo_events.insert(0, EVENT_EOGM_ARTICLES_AMENDMENT)

        # 🚀 成長投資の意思決定を年度ごとに最低1回保証
        #   抽選の偶然で成長戦略イベントが一度も出ないと、プレイヤーは成長性を
        #   高める機会がないまま審査の「高い成長可能性」で落ちてしまうため、
        #   Q3までに出ていなければ強制注入する。
        _growth_ids = ("sales_growth_early", "sales_growth_late")
        if getattr(self, "_growth_event_done_period", None) != t.n_period:
            if any(getattr(e, 'id', '') in _growth_ids for e in ipo_events):
                self._growth_event_done_period = t.n_period
            elif t.quarter >= 3:
                _want_id = "sales_growth_early" if t.n_period <= -2 else "sales_growth_late"
                _ge = next((e for e in self._game_events
                            if getattr(e, 'id', '') == _want_id), None)
                if _ge is not None:
                    _ge.fired = False
                    ipo_events.insert(0, _ge)
                    self._growth_event_done_period = t.n_period

        # 🃏 社長の切り札：ライバルに先行されそうな時の1回限りの逆転カード
        #   条件: ライバルが山頂まで残り8マス以内 or 5マス以上先行されている
        #   「温存」した場合は2Q後に再提示され得る
        if (not getattr(self, "_trump_used", False)
                and _rv is not None and not _rv["listed"]):
            _trump_cond = (_rv["pos"] >= 18) or (_rv["pos"] - getattr(self, "_map_pos", 0) >= 5)
            _trump_last = getattr(self, "_trump_last_offer", -99)
            if _trump_cond and (_tidx - _trump_last) >= 2:
                self._trump_last_offer = _tidx
                ipo_events.insert(0, self._build_trump_event())

        # ⏳ タイマークライシス：未解消なら最優先で対応選択を毎ターン提示
        #   （先送りも選べるが、放置したまま自然消滅することはない）
        for _tc in getattr(self, "_timer_crises", []):
            ipo_events.insert(0, self._build_crisis_event(_tc))

        # ── Q1: 🎪バナー + AGM議決結果表示 ──
        # 日本の定時株主総会は期末後3ヶ月以内（≒翌期Q1）に開催される
        if t.quarter == 1:
            prev_n = t.n_period - 1  # 前期
            period_labels = {-4: "N-4期", -3: "N-3期", -2: "N-2期（直前々期）",
                             -1: "N-1期（直前期）", 0: "N期（申請期）"}
            prev_label = period_labels.get(prev_n, f"N{prev_n}期")
            self._add(story_rule("🎪 ════ 定時株主総会 開催 ════ 🎪", "gold"))
            self._add(story_panel(
                f"<strong>{esc(prev_label)} 定時株主総会</strong> が本日開催されます。<br><br>"
                "定時株主総会は年に一度、前期の事業・決算を株主に報告し、<br>"
                "役員の信任・主要議案を決議する最も重要な会議体です。<br><br>"
                + (
                    "💡 前期Q4に社長が事前決定した議案を本日の総会で正式決議します。"
                    if t.n_period > -3 else
                    "💡 会社設立後はじめての定時株主総会です。<br>"
                    "創業からN-4期の事業実績を株主に報告し、役員の信任を得る重要な機会です。"
                ),
                f"📣 重要イベント：{esc(prev_label)} 定時株主総会", "gold"
            ), "event_panel")

            if t.n_period == -3:
                # ── N-3期Q1専用：N-4期定時株主総会の固定議決報告 ──
                self._add(
                    f'<div class="deferred-outcome" style="border-left:5px solid #00cc66;'
                    f'background:rgba(255,255,255,.07);padding:12px 16px;margin-bottom:8px;'
                    f'border-radius:4px;box-shadow:0 0 10px rgba(0,0,0,.3);">'
                    f'<div style="font-size:14px;font-weight:800;color:#00ffaa;margin-bottom:8px;'
                    f'letter-spacing:.5px">📋 N-4期 定時株主総会 議決結果</div>'
                    f'<div style="font-size:12px;color:#99ffcc;line-height:1.8">'
                    f'✅ <strong>第1号議案：事業報告・計算書類の承認</strong> — 原案通り承認可決<br>'
                    f'✅ <strong>第2号議案：取締役の選任</strong> — 代表取締役社長を含む役員全員が信任<br>'
                    f'✅ <strong>第3号議案：監査役の選任</strong> — 監査役1名を新たに選任<br>'
                    f'✅ <strong>第4号議案：役員報酬の決定</strong> — 現行水準にて承認<br><br>'
                    f'<span style="color:#aaddff">創業期の株主総会は、創業メンバーと少数の初期投資家で構成されており、<br>'
                    f'すべての議案が賛成多数で可決されました。</span>'
                    f'</div></div>'
                )
                # AGM後のナラティブ（N-4期振り返り・創業の思いも含む）
                agm_narrative = self._call_gemini_agm_narrative(
                    prev_label, "N-4期定時総会（全議案可決）", is_good=True, is_founding=True
                )
                self._render_agm_narrative(agm_narrative, is_good=True,
                    n_period=prev_n)

            elif self._pending_agm_result:
                # ── N-2期〜N期Q1：Q4で事前決議した結果を即時表示 ──
                icon = "✅" if self._pending_agm_is_good else "⚠️"
                border = "#00cc66" if self._pending_agm_is_good else "#ff6644"
                header_color = "#00ffaa" if self._pending_agm_is_good else "#ff8866"
                # 株主反応・閉会行を分離（株主反応は投資家アバターで1文字表示）
                _agm_main, _agm_react, _agm_closing = _split_agm_result(self._pending_agm_result)
                self._add(
                    f'<div class="deferred-outcome" style="border-left:5px solid {border};'
                    f'background:rgba(255,255,255,.07);padding:12px 16px;margin-bottom:8px;'
                    f'border-radius:4px;box-shadow:0 0 10px rgba(0,0,0,.3);">'
                    f'<div style="font-size:14px;font-weight:800;color:{header_color};margin-bottom:6px;'
                    f'letter-spacing:.5px;text-shadow:0 0 4px rgba(0,0,0,.5)">'
                    f'📋 定時株主総会 議決結果 — {esc(self._pending_agm_choice_label)}</div>'
                    f'<div style="font-size:12px;color:{"#99ffcc" if self._pending_agm_is_good else "#ffaa88"}">'
                    f'{_colorize_agm_votes(esc(_agm_main).replace(chr(10), "<br>"))}</div>'
                    f'</div>'
                )
                # 株主反応（投資家アバター＋1文字表示）
                if _agm_react.strip():
                    _react_body = _agm_react.replace("── 株主反応 ──", "").strip()
                    self._add(story_panel(
                        esc(_react_body).replace(chr(10), "<br>"),
                        "🗣 株主・投資家の反応", "gold"
                    ), "investor_panel")
                # 閉会行（即時表示）
                if _agm_closing.strip():
                    self._add(f'<div class="story-rule gold">{esc(_agm_closing.strip())}</div>')
                # AGM後ナラティブ（安堵・今後の課題）
                agm_narrative = self._call_gemini_agm_narrative(
                    prev_label, self._pending_agm_choice_label,
                    is_good=self._pending_agm_is_good, is_founding=False
                )
                self._render_agm_narrative(agm_narrative, is_good=self._pending_agm_is_good,
                    agm_result=self._pending_agm_result, n_period=prev_n)
                self._pending_agm_result = ""
                self._pending_agm_choice_label = ""
            # Q4 AGMで繰り延べたスコア変動をQ1冒頭に適用
            if self._agm_pending_score_changes:
                _score_keys_all = ['internal_control_score', 'accounting_quality', 'compliance_score',
                                   'governance_score', 'investor_trust', 'auditor_trust', 'employee_morale']
                _capped_keys = []
                for k, delta in self._agm_pending_score_changes.items():
                    if k in _score_keys_all:
                        old_val = getattr(self.company, k, 0)
                        new_val = max(0, min(100, old_val + delta))
                        actual_delta = new_val - old_val
                        setattr(self.company, k, new_val)
                        if actual_delta != delta:
                            _capped_keys.append(k)
                if _capped_keys:
                    _name_map = {
                        'internal_control_score': '内部統制', 'accounting_quality': '会計品質',
                        'compliance_score': 'コンプライアンス', 'governance_score': 'ガバナンス',
                        'investor_trust': '投資家信頼', 'auditor_trust': '監査法人信頼',
                        'employee_morale': '従業員士気',
                    }
                    _cap_names = [_name_map.get(k, k) for k in _capped_keys]
                    self._score_change_reasons.append(f"📊 {', '.join(_cap_names)}が上限/下限に到達")
                if self._agm_deferred_reasons:
                    self._score_change_reasons.extend(self._agm_deferred_reasons)
                    self._agm_deferred_reasons = []
                self._agm_pending_score_changes = {}

            # 前期総会特別決議の登記完了処理（AGM議決結果表示の後に実行する）
            self._process_agm_deferred()

            # ── Q1 AGM：前期に内定した社外役員の選任投票 ──
            # 社外役員の議決は Q4 ではなく翌期Q1（AGM当日）に行う設計
            # N-3期に内定 → N-2期Q1 AGM で選任投票
            # N-2期に内定 → N-1期Q1 AGM で選任投票
            # OD投票は create_agm_event 効果関数内（閉会直前）で実施済み
            if False:  # WEB-2: 廃止（IKN-2/3に移動）
                import random as _rod_r
                _prev_n_label = {-2: "N-3期", -1: "N-2期（直前々期）"}.get(t.n_period, "前期")
                od_pp = min(0.93, max(0.55, 0.76 + (c.investor_trust - 50) / 200))
                _agenda5_hdr = (
                    f"  📋 議案：独立社外取締役・社外監査役の選任（会社法329条・普通決議）<br>"
                    f"  　　（{esc(_prev_n_label)}中に内定した候補者の正式選任決議）"
                )
                if _rod_r.random() < od_pp:
                    c.agm_deferred_outside_director = False
                    c.flags.no_outside_director = False
                    c.governance_score   = min(100, c.governance_score + 18)
                    c.investor_trust     = min(100, c.investor_trust   + 12)
                    _od_vote_html = (
                        f'<div class="deferred-outcome" style="border-left:5px solid #00cc66;'
                        f'background:rgba(255,255,255,.07);padding:12px 16px;margin-bottom:8px;'
                        f'border-radius:4px;">'
                        f'<div style="font-size:13px;font-weight:800;color:#00ffaa;margin-bottom:6px">'
                        f'👔 社外役員 選任投票</div>'
                        f'<div style="font-size:12px;color:#99ffcc;line-height:1.8">'
                        f'{_agenda5_hdr}<br>'
                        f'  🗳 賛成多数【可決】（賛成率約{int(od_pp*100)}%）<br>'
                        f'  ✅ 社外役員が正式選任・本日即日就任しました。<br>'
                        f'  ▶ ガバナンス+30・投資家信頼+20（監視機能が本格稼働）'
                        f'</div></div>'
                    )
                    self._score_change_reasons.append(
                        f"📋 {_prev_n_label}定時AGM 社外役員選任可決：統治+18, 投資家信頼+12"
                    )
                else:
                    c.agm_deferred_outside_director = False
                    c.flags.total_risk_score += 10
                    c.outside_director_rejected_needs_eogm = True
                    _od_vote_html = (
                        f'<div class="deferred-outcome" style="border-left:5px solid #ff6644;'
                        f'background:rgba(255,255,255,.07);padding:12px 16px;margin-bottom:8px;'
                        f'border-radius:4px;">'
                        f'<div style="font-size:13px;font-weight:800;color:#ff8866;margin-bottom:6px">'
                        f'👔 社外役員 選任投票</div>'
                        f'<div style="font-size:12px;color:#ffaa88;line-height:1.8">'
                        f'{_agenda5_hdr}<br>'
                        f'  🗳 否決【否決】（賛成率{int(od_pp*100)}%に届かず）<br>'
                        f'  ❌ 社外役員選任議案が否決されました。リスクスコア+10。<br>'
                        f'  ▶ 【会社法第297条】臨時株主総会の招集により再度選任を諮れます。<br>'
                        f'  ▶ 次の四半期冒頭に臨時株主総会の開催可否を判断してください。'
                        f'</div></div>'
                    )
                    self._score_change_reasons.append(
                        f"📋 {_prev_n_label}定時AGM 社外役員選任否決：リスク+10"
                    )
                self._add(_od_vote_html)

        # ── N-3期 Q4: 監査契約ルーレット（AGM前に内諾を取得）──
        if t.quarter == 4 and t.n_period == -3 and not c.has_audit_contract and not c.audit_firm_agreed:
            if c.audit_firm_tier:  # 監査法人候補が選定済み
                self._add(story_rule("◆ 監査法人との受嘱交渉 ◆", "cyan"))
                sr_note = "✅ ショートレビュー実施済み" if c.flags.short_review_done else "⚠️ ショートレビュー未実施"
                accrual_note = "✅ 発生主義移行済み" if not c.flags.cash_basis_accounting else "⚠️ 発生主義移行未完了"
                _tier_labels = {"big": "大手監査法人（Big4系）", "mid": "中堅監査法人", "small": "小規模監査法人"}
                firm_note = f"候補先：{_tier_labels.get(c.audit_firm_tier, '未選定')}"
                self._add(story_panel(
                    "📋 N-2期（直前々期）からの監査開始に向けて、監査法人と受嘱交渉を行います。<br><br>"
                    "上場申請には N-2期・N-1期ともに<b>無限定適正意見</b>が必要です。<br>"
                    "【監査難民リスク】監査法人の人手不足により新規受嘱を断るケースが急増しています。<br><br>"
                    f"準備状況：{esc(sr_note)} / {esc(accrual_note)}<br>"
                    f"　　　　　{esc(firm_note)}",
                    "🔑 監査法人 受嘱交渉", "yellow"
                ))
                self._run_audit_roulette()
                if not self.company.audit_firm_agreed:
                    return  # 拒絶 → ALT_CHOICE待ち

        # N-2期Q4：主幹事未選定の場合は警告パネルを表示
        if t.n_period == -2 and t.quarter == 4 and not c.has_underwriter:
            # 先送り済み（イベント経験済み）か、まだイベント未到達かで文言を分岐
            if c.flags.underwriter_intentionally_skipped:
                _uw_timing_msg = (
                    "前回、主幹事選定を意図的に先送りされました。<br>"
                    "<strong>N-1期Q1</strong>に主幹事選定の意思決定機会が再度提供されますが、<br>"
                    "公開指導期間が大幅に短縮され、上場審査に影響します。"
                )
            else:
                _uw_timing_msg = (
                    "<strong>今四半期（N-2期Q4）中に主幹事選定の意思決定機会が提供されます。</strong><br>"
                    "早急に選定してください。"
                )
            self._add(story_panel(
                "⚠️ <strong>主幹事証券会社がまだ選定されていません。</strong><br><br>"
                "主幹事証券会社の選定はN-3期が理想、<strong>N-2期が最遅</strong>です。<br>"
                "N-1期以降の選定では公開指導（引受審査）期間が大幅に短縮され、<br>"
                f"指摘事項の改善が間に合わないリスクがあります。<br><br>"
                f"{_uw_timing_msg}",
                "⏳ タイマークライシス：主幹事証券選定（残り1期） — 緊急警告", "red"
            ))

        # ── Q4 (N-3期〜N-1期): AGM議案の事前決定イベントを注入 ──
        if t.quarter == 4 and -3 <= t.n_period <= -1:
            agm_prep_evt = create_agm_event(c, t.n_period)
            period_labels_q4 = {-3: "N-3期", -2: "N-2期（直前々期）", -1: "N-1期（直前期）"}
            curr_label = period_labels_q4.get(t.n_period, f"N{t.n_period}期")
            self._add(story_rule("📋 ════ 定時株主総会 議案準備 ════ 📋", "gold"))
            self._add(story_panel(
                f"<strong>{esc(curr_label)} 定時株主総会</strong>は翌期Q1に開催されます。<br><br>"
                "日本の定時株主総会は期末後3ヶ月以内（翌期Q1）に開催されます。<br>"
                "本日の取締役会で総会提案議案を最終決定します。<br><br>"
                "💡 今ここで決定した内容が翌Q1の総会で正式決議されます。",
                f"📣 事前準備：{esc(curr_label)} 定時株主総会 議案決定", "gold"
            ), "event_panel")
            # AGM議案事前決定イベントを末尾に挿入
            # Q4の他イベント（内定等）を先に処理することで agm_deferred フラグが確定する
            ipo_events = ipo_events + [agm_prep_evt]

        # N期Q4は東証上場審査へ
        if t.n_period == N_PERIOD and t.quarter == 4:
            self._post_events_action = "tse_exam"

        world_evt  = roll_world_event(self._world_events, t.n_period, c.business_type.value)

        # AI突発クライシスが予定されていれば世界イベントより優先してセット
        crisis_this_turn = self._check_and_fire_crisis()
        if not crisis_this_turn:
            self._pending_fortune = world_evt   # 通常の世界イベント
        self.pending_events = ipo_events
        self.pending_event_idx = 0

        if self.pending_events:
            self._show_next_event()
        else:
            # IPOイベントなし → スロット + 突発イベントへ
            self._finish_events()

    # ──────────────────────────────────────────
    # イベント表示
    # ──────────────────────────────────────────
    def _show_next_event(self):
        event = self.pending_events[self.pending_event_idx]
        # 売上成長イベントは毎期発火するため、報告文をランダムに変えて単調さを防ぐ
        _var_descs = SALES_GROWTH_DESCRIPTIONS.get(getattr(event, "id", ""))
        if _var_descs:
            event.description = _rand.choice(_var_descs)
        # 【ポイント】【実務ポイント】【学習ポイント】等は取締役会では非表示
        # （IPO先生に相談すると表示される）
        # マーカー行以降（続行行も含む）をまとめて除去
        raw_desc = event.description
        # 主幹事未選定時は「主幹事証券会社からの」→「IPOアドバイザーからの」に変換
        if not self.company.has_underwriter:
            raw_desc = raw_desc.replace(
                "主幹事証券会社からのフィードバックです",
                "IPOアドバイザーからの助言です（主幹事証券会社は未選定）"
            ).replace(
                "主幹事証券会社からの指摘です",
                "IPOアドバイザーからの指摘です（主幹事証券会社は未選定）"
            ).replace(
                "主幹事証券会社からの連絡：",
                "IPOアドバイザーからの連絡（主幹事証券会社は未選定）："
            )
        # CFO逮捕後は「CFOからの提言」をIPO顧問に差し替え（経理部長が職務代行中）
        if getattr(self.company, "cfo_arrested", False) and "CFOからの提言：「" in raw_desc:
            raw_desc = raw_desc.replace(
                "CFOからの提言：「",
                "IPO顧問からの提言：「CFO逮捕を受け、当面は経理部長が財務責任を代行しています。\n"
            )
        filtered_desc = _re.sub(r'\n*【[^】]*ポイント[^】]*】.*', '', raw_desc, flags=_re.DOTALL)
        # 末尾の空白・改行をクリーンアップ
        filtered_desc = filtered_desc.rstrip()
        desc = esc(filtered_desc).replace("\n", "<br>")
        # WorldEvent has category attribute; GameEvent does not
        is_world = hasattr(event, 'category')
        panel_title = f"🌍 外部環境イベント：{esc(event.title)}" if is_world else f"📋 社長へのご報告：{esc(event.title)}"
        panel_color = "red" if is_world else "yellow"
        self._add(story_panel(desc, panel_title, panel_color), "event_panel")
        prompt_text = "👤 社長、緊急対応が必要です。どう判断しますか？" if is_world else "👤 社長、あなたならどう判断しますか？"
        self._add(f'<div class="decision-prompt">{prompt_text}</div>')
        self._add("", "clear_advisor")   # 前イベントのアドバイスパネルをクリア
        self._add(choices_html(event.choices))
        valid = list("ABCD")[: len(event.choices)]
        self.phase = Phase.EVENT_CHOICE
        self._ph(f"► 社長のご判断 ({' / '.join(valid)})")

    # ──────────────────────────────────────────
    # 選択肢適用
    # ──────────────────────────────────────────
    def _apply_choice(self, idx: int):
        event = self.pending_events[self.pending_event_idx]
        choice = event.choices[idx]

        self._add(f'<div class="ceo-decision">👤 社長のご決断：{"ABCD"[idx]}を選択</div>')

        # ── 決定前の財務・スコアスナップショット ──
        c = self.company
        pre_cash       = c.cash
        pre_burn       = c.quarterly_burn
        pre_rev        = c.revenue.recognized
        pre_mktcap     = c.market_cap_million
        pre_shareholders = c.shareholder_count
        _pre_scores    = self._get_score_snapshot()
        # AGMスコア繰り延べ用スナップショット（immediate_effect前に取得）
        _agm_score_keys = ['internal_control_score', 'accounting_quality', 'compliance_score',
                           'governance_score', 'investor_trust', 'auditor_trust', 'employee_morale']
        _pre_snap = {k: getattr(c, k, 0) for k in _agm_score_keys}
        # AGM処理前の理由リスト長を保存（AGMイベントが追加した理由のみ繰り延べるため）
        _reasons_before_choice = len(self._score_change_reasons)

        result_msg = choice.immediate_effect(self.company)

        # スコア変動を記録（次Qのブリーフに要因表示）
        _post_scores = self._get_score_snapshot()
        _score_delta = {k: _post_scores[k] - _pre_scores.get(k, _post_scores[k]) for k in _post_scores}
        _sig_delta = {k: v for k, v in _score_delta.items() if abs(v) >= 1}
        if _sig_delta:
            _parts = ", ".join(f"{k}{'+'if v>=0 else ''}{v:.0f}" for k, v in _sig_delta.items())
            _title_clean = event.title.split('（')[0].strip()
            self._score_change_reasons.append(f"{_title_clean[:22]}：{_parts}")
        # 安全ガード: immediate_effect が文字列を返さない場合でも壊れない
        if not isinstance(result_msg, str):
            result_msg = f"（処理完了）{repr(result_msg)}"
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
            kw in result_msg for kw in ["⚠️", "❗", "❌", "💰（短期のみ）", "【否決】"]
        )

        # ── 意思決定を受理したことのみ即時表示（効果の詳細は次Q冒頭に遅延） ──
        action_icon = "✅" if is_good else "⚙️"
        _choice_label_clean = esc(_re.sub(r"^[A-D]\.\s*", "", choice.label)[:60])
        self._add(
            f'<div class="decision-accepted">'
            f'<span class="da-icon">{action_icon}</span>'
            f'<div class="da-body">'
            f'<div class="da-title">意思決定を実行しました</div>'
            f'<div class="da-choice">「{_choice_label_clean}」</div>'
            f'<div class="da-note">📋 この判断の結果は次の四半期末に社長報告でご確認ください。</div>'
            f'</div>'
            f'</div>'
        )
        # 効果詳細・AIドラマを次ターン冒頭表示用にキューへ積む
        # AGMイベント（agm_n3/n2/n1/n0）はdeferredに入れず、翌Q1バナーで即時表示
        if getattr(event, 'id', '').startswith('agm_n'):
            self._pending_agm_result       = result_msg
            self._pending_agm_is_good      = is_good
            self._pending_agm_choice_label = _re.sub(r'^[A-D]\.\s*', '', choice.label)[:60]
            # Q4 AGMスコア変動をQ1へ繰り延べ（スナップショット差分を記録して即時リバート）
            _post_snap = {k: getattr(self.company, k, 0) for k in _agm_score_keys}
            for k in _agm_score_keys:
                delta = _post_snap[k] - _pre_snap[k]
                if delta != 0:
                    self._agm_pending_score_changes[k] = self._agm_pending_score_changes.get(k, 0) + delta
                    setattr(self.company, k, _pre_snap[k])   # リバート
            # スコア変動理由は繰り延べ（Q1決算レポートで表示）
            # ※ AGMイベントが追加した理由のみ繰り延べる（非AGMイベントの理由は当期レポートに残す）
            _deferred_reasons = list(self._score_change_reasons[_reasons_before_choice:])
            self._score_change_reasons = self._score_change_reasons[:_reasons_before_choice]
            self._agm_deferred_reasons.extend(_deferred_reasons)
        else:
            self._deferred_outcomes.append((event.title, choice.label, result_msg, is_good))

        # ── 財務インパクット（今ターン末に決算レポートで集計表示） ──
        d_cash   = c.cash - pre_cash
        d_burn   = c.quarterly_burn - pre_burn
        one_time_cost = -d_cash if d_cash < 0 else 0.0
        if one_time_cost > 0:
            self._this_turn_one_time_costs += one_time_cost

        # 決断ログに積み上げ（ターン末決算レポートで表示）
        decision_log = f"{event.title} → {choice.label[:60]}"
        if one_time_cost >= 0.5:
            decision_log += f" ｜一時費用¥{one_time_cost:,.0f}M"
        if d_cash > 0.5:
            decision_log += f" ｜資金調達+¥{d_cash:,.0f}M"
        if abs(d_burn) >= 0.5:
            sign = "+" if d_burn >= 0 else ""
            decision_log += f" ｜継続費用{sign}¥{d_burn:,.0f}M/Q"
        self._turn_decisions.append(decision_log)

        # 選択肢反映の簡潔な予約告知（詳細はターン進行時に表示）
        pending_parts = []
        if one_time_cost >= 0.5:
            pending_parts.append(f'<span style="color:#ffaa55">当Q一時費用 ¥{one_time_cost:,.0f}M計上予定</span>')
        if d_cash > 0.5:
            pending_parts.append(f'<span style="color:#55ddaa">当Q資金調達 +¥{d_cash:,.0f}M</span>')
        if abs(d_burn) >= 0.5:
            sign = "+" if d_burn >= 0 else ""
            col = "#ffaa55" if d_burn > 0 else "#55ddaa"
            arrow = "▲" if d_burn > 0 else "▼"
            pending_parts.append(f'<span style="color:{col}">{arrow} 継続費用{sign}¥{d_burn:,.0f}M/Q（次Qから反映）</span>')
        if pending_parts:
            self._add(
                f'<div class="pending-fin-note">'
                f'<span class="pfn-label">📋 当Q決算に反映予定</span> '
                + ' ｜ '.join(pending_parts)
                + f'<br><span class="pfn-sub">▼ 詳細はターン末の四半期決算レポートで確認できます</span>'
                + f'</div>'
            )

        # 吉凶カウント（四半期スロット用）
        # ※ AIドラマは次ターン冒頭の「当Q意思決定の結果報告」と一緒にまとめて表示
        if is_good:
            self._this_turn_good += 1
        else:
            self._this_turn_bad += 1

        self.pending_event_idx += 1
        if self.pending_event_idx < len(self.pending_events):
            self.phase = Phase.CONTINUE
            self._next_action = "next_event"
            self._ph("► Enter で次のイベントへ...")
        else:
            # 全通常イベント完了 → スロット → 突発イベントへ
            self._finish_events()

    # ──────────────────────────────────────────
    # 全イベント完了後の処理（スロット → 突発イベント or 次ターン）
    # ──────────────────────────────────────────
    def _finish_events(self):
        """通常イベントを全て処理し終えたあとの分岐処理"""
        # N期Q4：上場審査に直行（財務確定 → TSE審査）
        if self._post_events_action == "tse_exam":
            self._post_events_action = ""
            c = self.company
            t = self.timeline
            advance_quarter_financials(c, t.n_period, t.quarter)
            # 📊 IPOウィンドウ：弱気市況なら申請タイミングの判断を迫る（1回まで）
            if (getattr(c, "market_index", 55.0) < 35.0
                    and not getattr(self, "_ipo_window_deferred", False)):
                self._offer_ipo_window_choice()
                return
            self._run_tse_exam()
            return

        has_decisions = self._this_turn_good + self._this_turn_bad > 0
        if has_decisions or self._pending_fortune:
            self._add_quarterly_slot()

        if self._pending_fortune:
            self.phase = Phase.CONTINUE
            self._next_action = "show_fortune"
            self._ph("► 突発イベントを確認する...")
        else:
            self.phase = Phase.CONTINUE
            self._next_action = "advance_turn"
            self._ph("► ターンを進める...")

    # ──────────────────────────────────────────
    # 四半期スロット（ターン終了時インライン演出）
    # ──────────────────────────────────────────
    def _add_quarterly_slot(self):
        """今Qの采配結果をインラインスロット演出で表示"""
        c = self.company

        # ── リール1: 財務（純利益ベース）──
        net = c.revenue.recognized - c.quarterly_burn
        if net > 20:
            r1, l1 = "💰", "黒字好調"
        elif net > 0:
            r1, l1 = "📈", "微黒字"
        elif net > -20:
            r1, l1 = "📉", "赤字"
        else:
            r1, l1 = "💸", "大赤字"

        # ── リール2: 管理体制（スコア変化）──
        snap = self._get_score_snapshot()
        score_delta = sum(
            snap[k] - self._prev_scores.get(k, snap[k])
            for k in snap
        )
        if score_delta >= 15:
            r2, l2 = "✅", "体制大強化"
        elif score_delta >= 5:
            r2, l2 = "📋", "着実な改善"
        elif score_delta >= 0:
            r2, l2 = "🔍", "現状維持"
        else:
            r2, l2 = "⚠️", "体制後退"

        # ── リール3: 突発イベント（世界イベントのタイトルをそのまま表示）──
        CAT_ICON = {
            "geopolitics": "⚔️",
            "epidemic":    "🦠",
            "demand":      "📈",
            "scandal":     "💣",
            "social":      "🌊",
            "economy":     "📉",
        }
        if self._pending_fortune:
            cat = getattr(self._pending_fortune, "category", "economy")
            r3 = CAT_ICON.get(cat, "⚡")
            # タイトルをそのまま使用（12文字でトリム）
            _ft_title = getattr(self._pending_fortune, "title", "外部ショック")
            l3 = _ft_title[:12] if len(_ft_title) > 12 else _ft_title
            fortune_positive = cat == "demand"
        else:
            r3, l3 = "🌿", "平穏な四半期"
            fortune_positive = True

        # ── 総評 ──
        total = self._this_turn_good + self._this_turn_bad
        good_ratio = self._this_turn_good / total if total > 0 else 0.5
        good_signs = sum([
            r1 in ("💰", "📈"),
            r2 in ("✅", "📋"),
            good_ratio >= 0.5,
        ])

        if self._pending_fortune:
            if fortune_positive:
                verdict = "✦ 今季は順調！さらにチャンスが到来している！▶"
                vcls = "qs-verdict-good"
            else:
                verdict = "⚡ まずまずの四半期。しかし突発事態が迫っている！"
                vcls = "qs-verdict-bad"
        elif good_signs >= 3:
            verdict = "✦ 今季の采配は上々！上場への道は開けている ✦"
            vcls = "qs-verdict-good"
        elif good_signs == 0:
            verdict = "▼ 今季は苦しい四半期。次季の巻き返しが必要だ ▼"
            vcls = "qs-verdict-bad"
        else:
            verdict = "◆ まずまずの四半期。着実に積み上げている ◆"
            vcls = "qs-verdict-mid"

        self._add(
            f'<div class="quarterly-slot"'
            f' data-r1="{r1}" data-r2="{r2}" data-r3="{r3}"'
            f' data-l1="{esc(l1)}" data-l2="{esc(l2)}" data-l3="{esc(l3)}"'
            f' data-verdict="{esc(verdict)}" data-vcls="{vcls}">'
            f'<div class="qs-title">🎰 四半期スロット ── 今季の成果は？</div>'
            f'<div class="qs-reels">'
            f'<div class="qs-col"><div class="qs-reel">❓</div><div class="qs-rlbl">財務</div></div>'
            f'<div class="qs-sep">◆</div>'
            f'<div class="qs-col"><div class="qs-reel">❓</div><div class="qs-rlbl">管理体制</div></div>'
            f'<div class="qs-sep">◆</div>'
            f'<div class="qs-col"><div class="qs-reel">❓</div><div class="qs-rlbl">突発イベント</div></div>'
            f'</div>'
            f'<div class="qs-extra">'
            f'<div class="qs-labels">'
            f'<span class="qs-lbl-item"></span>'
            f'<span class="qs-lbl-item"></span>'
            f'<span class="qs-lbl-item"></span>'
            f'</div>'
            f'<div class="qs-verdict {vcls}"></div>'
            f'</div>'
            f'</div>',
            "quarterly_slot"
        )

    # ──────────────────────────────────────────
    # IPO先生アドバイザー（意思決定時の相談機能）
    # ──────────────────────────────────────────
    # キーワード → IPO実務アドバイス
    _IPO_TIPS: dict = {
        # ── 会計・内部統制（②）────────────────────────────────────────────
        "証憑":       "【②会計・内部統制】監査法人はN-3期まで遡って証憑を確認します。今が整備の好機です。",
        "発生主義":   "【②会計・内部統制】N-2期期首から監査開始。それ以前に移行を完了させておくことが必須です。",
        "棚卸":       "【②会計・内部統制】監査法人は実地棚卸立会を行います。N-2期から参加させるための準備を今から。",
        "原価":       "【②会計・内部統制】原価計算体制がない場合、製造業は監査を受けられません。早急な整備が必要です。",
        "収益認識":   "【②会計・内部統制】5ステップモデルによる収益認識は上場審査の重点確認項目。出荷基準から検収・進捗基準への移行を。",
        "月次決算":   "【②④経営管理】月次決算の翌月10日以内の締めは上場後の適時開示の基盤。N-2期から運用実績を積んでください。",
        "内部統制":   "【②会計・内部統制】J-SOX対応はN-1期が本格化。N-3期から着手すれば余裕を持って仕上げられます。",
        "内部監査":   "【②会計・内部統制】独立した内部監査は自浄作用の根幹。経理部員の兼務では独立性がなく審査NGになる場合があります。",
        "開示":       "【②会計・内部統制】適時開示体制は上場後の最重要義務。N-1期中に開示判断フローと担当者を確立してください。",
        # ── ガバナンス・コンプライアンス（①）─────────────────────────────
        "労務":       "【①ガバナンス・コンプライアンス】未払残業代は労基署申告で発覚。N-3期中に勤怠管理を整備しないと上場直前に爆発します。",
        "関連当事者": "【⑥関連当事者・支配関係】オーナー会社・役員への貸付など全て開示対象。価格の妥当性が説明できないと利益相反を疑われます。",
        "社外":       "【①ガバナンス・コンプライアンス】独立社外役員の選任はN-2期期首までが理想。形式要件でもあり、実際に機能しているかが見られます。",
        "コンプライアンス": "【①ガバナンス・コンプライアンス】規程の有無より『実際に守られているか』が審査の核心。文化として根付いているかが問われます。",
        "不正":       "【①ガバナンス・コンプライアンス】不正発覚時は速やかな開示が最善。隠蔽は経営者解任の直接原因。『知らなかった』も最悪の評価を受けます。",
        "パワハラ":   "【①ガバナンス・コンプライアンス】防止規程・相談窓口は上場企業の最低要件。今すぐ整備してください。",
        "反社":       "【①ガバナンス・コンプライアンス】反社チェックは全取引先が対象。一件でも見落とすと上場審査で致命傷。継続的なチェック体制が必要です。",
        "横領":       "【①ガバナンス・コンプライアンス】横領は職務分掌の分離で防ぎます。出納と記帳を同一人物が担うのは最大のリスクです。",
        "インサイダー": "【①ガバナンス・コンプライアンス】金商法166条違反は刑事罰。上場後の最頻発コンプライアンス違反。N-1期中に規程整備と全社研修を完了させてください。",
        # ── 事業継続性・収益性（③）─────────────────────────────────────
        "顧客集中":   "【③事業継続性・収益性】売上上位顧客への依存度が高いと『再現性ある収益』と認められにくい。分散実績か、集中の合理性説明が不可欠です。",
        "事業計画":   "【③④事業継続性・経営管理】中期経営計画は数値の裏付けとKPIとの連動が必要。達成プロセスの合理性が問われます。単なる目標では不十分です。",
        "資金":       "【③事業継続性・⑤資本政策】IPO前の資金調達は主幹事証券会社との関係構築がカギ。上場直前の不自然な増資は厳しくチェックされます。",
        # ── 経営管理体制（④）───────────────────────────────────────────
        "予算":       "【④経営管理体制】予算と実績の大幅乖離より、原因分析と改善策を説明できるかが重要。差異率±10%以内が目安です。",
        "KPI":        "【④経営管理体制】KPIが整理されていないと成長ドライバーが不明確と判断。経営陣が数値を理解・説明できることが審査で問われます。",
        # ── 資本政策・株主構成（⑤）────────────────────────────────────
        "株主":       "【⑤資本政策・株主構成】株主数は形式要件（グロース150人・スタンダード400人・プライム800人）。ファイナンスラウンドで積み上げを。",
        "ストックオプション": "【⑤資本政策・株主構成】非公開会社では役員・従業員いずれへのSO付与も株主総会の特別決議（2/3以上）が原則必要（会社法238条・309条2項）。総会で付与枠・条件の上限を承認後、具体的付与は取締役会に委任できます（委任期間：最長1年）。",
        "資本政策":   "【⑤資本政策・株主構成】流通株式比率・持分構成を早期に設計。上場直前の不自然な増資・ストックオプション設計は厳しくチェックされます。",
        "総会上程":   "SOの付与決議は特別決議（議決権の過半数出席＋2/3以上の賛成）が必要です。否決された場合は次期総会に再上程するか、規模を縮小して再提案します。",
        # ── 組織・人材（⑦）─────────────────────────────────────────────
        "キーパーソン": "【⑦組織・人材】特定個人への依存が大きいと離脱リスクと評価。『人ではなく組織で回る会社』かどうかが判断軸です。",
        "後継者":     "【⑦組織・人材】後継者計画と権限委譲の体制整備が必要。CFO・CTOなど経営幹部の後継者候補育成が上場後の持続性を示します。",
        "CFO":        "【⑦組織・人材】CFOはIPO準備の要。有価証券届出書作成・ロードショー・監査法人との窓口。常勤の正社員CFOが実質的な審査要件です。",
        # ── リスク・訴訟・外部要因（⑧）────────────────────────────────
        "知財":       "【⑧リスク・訴訟・外部要因】特許・商標の権利化と他社権利侵害の予防調査が必要。知財係争は上場後の業績下振れ要因として目論見書に記載必須です。",
        "訴訟":       "【⑧リスク・訴訟・外部要因】訴訟・紛争は金額だけでなく企業イメージにも影響。リスクの存在より『把握し適切に管理しているか』が評価されます。",
        "BCP":        "【⑧リスク・訴訟・外部要因】事業継続計画は上場審査でも確認されます。文書化と訓練実績が評価されます。",
        # ── インフラ・業務プロセス（⑨）────────────────────────────────
        "システム":   "【⑨インフラ・業務プロセス】基幹システムが弱いと財務情報の正確性に影響。属人化・手作業依存は不正・ミスの温床と評価されます。",
        "セキュリティ": "【⑨インフラ・業務プロセス】近年はサイバーセキュリティも重要視。情報システムへのアクセス権管理・不正アクセス対策が内部統制の一部として審査されます。",
        # ── 主幹事・審査プロセス（⑩）──────────────────────────────────
        "主幹事":     "【⑩主幹事・審査プロセス】主幹事証券会社の引受姿勢が審査の実質的ゲートキーパー。早期に関係構築し、リスクの早期発見・修正が鍵です。",
        "説明":       "【⑩主幹事・審査プロセス】投資家・審査官に対して数値を理解・説明できるかが最終判断基準。経営陣の説明力不足は信頼を大きく損ないます。",
        # ── 汎用 ─────────────────────────────────────────────────────────
        "監査":       "【②会計・内部統制】監査法人の受嘱判断は内部統制スコアが大きく影響。スコア50以上が目安です。",
        "ショートレビュー": "【②会計・内部統制】IPO準備の最初の一歩。財務・内部統制・労務・ガバナンス全体のリスクを可視化し、N-3期の方針を決めます。",
        "AI":         "AI・DX投資は成長ストーリーに直結。ただし過剰投資は財務を傷めます。ROIを意識して。",
        "補助金":     "補助金は正規の申請書類が命。後の監査で書類の適正性が確認されます。",
    }

    # カテゴリ別ガイダンス（突発イベント用）
    _CAT_GUIDANCE: dict = {
        "geopolitics": "⚔️ 地政学リスクへの対応は「外部環境変化への備え」としてBCP文書化と開示方針の明確化が重要です。",
        "epidemic":    "🦠 感染症・災害対応はBCP（事業継続計画）として文書化が必須。上場審査でリスク管理体制として確認されます。",
        "scandal":     "💣 不祥事の初動対応が全てを決めます。「知らなかった」「揉み消した」は上場審査で最悪の評価を受けます。透明性と速さが命です。",
        "social":      "🌊 社会変化への対応はESG・コンプライアンス評価に影響します。短期コストより中長期の信頼構築を優先すると審査でプラスです。",
        "economy":     "📉 財務リスクへの対応方針は「リスク管理体制」として審査されます。「何もしない」は最も評価が低く、対応を誤ると財務モデルが崩壊します。",
        "demand":      "📈 市場機会への対応スピードは成長ストーリーに直結します。ただし過剰投資は財務を傷めます。ROI（投資対効果）を意識して。",
        "governance":  "🏛️ 経営体制・株主構成の安定性は上場審査の根幹です。創業者間の株式関係・キャップテーブルの整理状況は主幹事証券会社が最初に確認する論点。早期に合意・整理し、説明できる状態を保つことが重要です。",
    }

    def _show_advisor_advice(self):
        """IPO先生：現在のイベントに対する意思決定アドバイスを表示（フェーズ不変）"""
        c = self.company
        if self.phase == Phase.EVENT_CHOICE:
            event = self.pending_events[self.pending_event_idx]
        elif self.phase == Phase.FORTUNE_CHOICE:
            event = self._pending_fortune
        else:
            return

        title   = getattr(event, 'title', 'イベント')
        choices = event.choices
        cat     = getattr(event, 'category', '')

        # ── カテゴリガイダンス ──
        cat_text = self._CAT_GUIDANCE.get(
            cat,
            "上場審査では経営判断の合理性・一貫性が問われます。コスト・リスク・長期効果を総合判断してください。"
        )

        # ── キーワードベース IPO実務ヒント ──
        ipo_tip = ""
        for kw, tip in self._IPO_TIPS.items():
            if kw in title:
                ipo_tip = f'<div class="adv-ipo-tip">📌 {esc(tip)}</div>'
                break

        # ── イベント説明文の【〇〇ポイント】を抽出（取締役会では非表示 → IPO先生に表示） ──
        point_html = ""
        raw_evt_desc = getattr(event, 'description', '')
        _m = _re.search(r'【([^】]*ポイント[^】]*)】(.*)', raw_evt_desc, flags=_re.DOTALL)
        if _m:
            marker_name = _m.group(1)   # 例: "ポイント", "実務ポイント", "学習ポイント"
            pt_text     = _m.group(2).strip()
            if pt_text:
                point_html = (
                    f'<div class="adv-ipo-tip" style="background:rgba(255,200,80,.10);'
                    f'border-left:3px solid #ffcc44;padding:8px 12px;margin:6px 0;'
                    f'color:#ffe7a0;font-weight:600">'
                    f'🎓 【{esc(marker_name)}】{esc(pt_text).replace(chr(10), "<br>")}</div>'
                )

        # ── 資金残存アラート ──
        rw = c.runway_quarters()
        if rw < 5:
            cash_warn = (
                f'<div class="adv-warning">'
                f'⚠ 残り資金{_rw_label(rw)}！現金支出が大きい選択肢は慎重に。'
                f'</div>'
            )
        else:
            cash_warn = ""

        # ── アドバイスパネル本体 ──
        # 各選択肢の💰/⚠ヒントは別枠に出さず、選択肢カード上に表示する
        # （revealHints() スクリプトで非表示クラスを外す）
        # 選択肢にhintがあるか確認（ない場合はヒント表示メッセージを変える）
        has_any_hints = any(
            (getattr(ch, 'profit_hint', '') or getattr(ch, 'risk_hint', ''))
            for ch in choices
        )
        footer = (
            f'各選択肢に <span style="color:var(--green)">💰利益</span>・'
            f'<span style="color:var(--yellow)">⚠リスク</span> のヒントを表示しました。'
            if has_any_hints else
            f'各選択肢の説明をご参考の上、コスト・リスク・長期効果を総合的に判断してください。'
        )
        body = (
            f'<div class="adv-header">💡 IPO先生のアドバイス：{esc(title)}</div>'
            f'<div class="adv-context">{cat_text}</div>'
            f'{ipo_tip}'
            f'{point_html}'
            f'{cash_warn}'
            f'<div class="adv-footer">{footer}</div>'
        )
        self._add(f'<div class="advisor-chat">{body}</div>')
        # 選択肢カード上の💰/⚠ヒントを表示する合図
        # (appendStory 側が item_type=="reveal_hints" を検出してJSを実行)
        self._add("", "reveal_hints")

    # ──────────────────────────────────────────
    # 突発イベント（スロット後に出現）
    # ──────────────────────────────────────────
    def _show_fortune_event(self):
        """スロット後に突発イベント（世界イベント）を表示し、選択を促す"""
        event = self._pending_fortune
        desc = esc(event.description).replace("\n", "<br>")
        self._add(story_panel(desc,
                               f"🌍 突発イベント！：{esc(event.title)}",
                               "red"), "event_panel")
        self._add(f'<div class="decision-prompt">👤 社長、緊急対応が必要です。どう判断しますか？</div>')
        self._add("", "clear_advisor")   # 前イベントのアドバイスパネルをクリア
        self._add(choices_html(event.choices))
        valid = list("ABCD")[: len(event.choices)]
        self._fortune_choices = event.choices
        self.phase = Phase.FORTUNE_CHOICE
        self._ph(f"► 緊急判断 ({' / '.join(valid)})")

    def _apply_fortune_choice(self, idx: int):
        """突発イベントの選択肢を適用し、ターン進行へ"""
        event = self._pending_fortune
        choice = self._fortune_choices[idx]
        self._add(f'<div class="ceo-decision">👤 社長のご決断：{"ABCD"[idx]}を選択</div>')

        c = self.company
        pre_cash = c.cash
        pre_burn = c.quarterly_burn
        pre_rev  = c.revenue.recognized
        _pre_scores_f = self._get_score_snapshot()

        result_msg = choice.immediate_effect(c)
        if not isinstance(result_msg, str):
            result_msg = f"（処理完了）{repr(result_msg)}"

        # スコア変動を記録
        _post_scores_f = self._get_score_snapshot()
        _delta_f = {k: _post_scores_f[k] - _pre_scores_f.get(k, _post_scores_f[k]) for k in _post_scores_f}
        _sig_f = {k: v for k, v in _delta_f.items() if abs(v) >= 1}
        if _sig_f:
            _parts_f = ", ".join(f"{k}{'+'if v>=0 else ''}{v:.0f}" for k, v in _sig_f.items())
            _title_clean_f = event.title.split('（')[0].strip()
            self._score_change_reasons.append(f"[外部]{_title_clean_f[:18]}への対応：{_parts_f}")

        event.fired = True
        event.last_fired_n_period = self.timeline.n_period
        self.company.add_event_log(
            f"[{self.timeline.full_label()}] 突発：{event.title}: {choice.label[:30]}"
        )

        is_good = not any(kw in result_msg for kw in ["⚠️", "❗", "❌", "💣"])

        # ── 意思決定受理メッセージ（ゲームイベントと同様に即時表示） ──
        action_icon = "✅" if is_good else "⚙️"
        _choice_label_clean2 = esc(_re.sub(r"^[A-D]\.\s*", "", choice.label)[:60])
        self._add(
            f'<div class="decision-accepted">'
            f'<span class="da-icon">{action_icon}</span>'
            f'<div class="da-body">'
            f'<div class="da-title">対応を実行しました</div>'
            f'<div class="da-choice">「{_choice_label_clean2}」</div>'
            f'<div class="da-note">📋 この対応の結果は次の四半期末にご報告します。</div>'
            f'</div>'
            f'</div>'
        )
        # マクロショック処理
        if getattr(event, 'macro_shock', False):
            # 🏁 マクロショック（災害・パンデミック・金融危機等）は経済全体への打撃。
            #    ライバル社も例外ではなく、1〜2マス後退する。
            _rv_ms = getattr(self, "_rival", None)
            if _rv_ms and not _rv_ms["listed"] and _rv_ms["pos"] > 0:
                _r_back = _rand.randint(1, 2)
                _rv_ms["pos"] = max(0, _rv_ms["pos"] - _r_back)
                self._add(story_panel(
                    f"📰 <strong>{esc(event.shock_name)}は業界全体を直撃</strong><br><br>"
                    f"競合の{esc(_rv_ms['name'])}も例外ではなく、"
                    f"上場準備の後退を余儀なくされている模様です。<br>"
                    f"▶ ライバルは{_r_back}マス後退しました。",
                    "📰 業界ニュース — 上場レース", "yellow"), "event_panel")
            # ⏳ 大規模災害 → タイマークライシス「BCP見直し・拠点復旧」を開始
            #    （延期・強行どちらを選んでも、拠点復旧は別途必要）
            if getattr(event, "id", "") == "macro_earthquake" \
                    and not any(tc["kind"] == "bcp_recovery" for tc in self._timer_crises):
                self._timer_crises.append({"kind": "bcp_recovery", "remaining": 2})

            if idx == 0:
                # 延期を選択 → 1年後同時期から再スタート
                self._handle_ipo_delay(event.shock_name, after_story_html=result_html(result_msg, is_good))
                return
            else:
                # 強行を選択 → TSE審査で確率判定
                self._macro_shock_active = {
                    "name": event.shock_name,
                    "pass_prob": event.pass_prob,
                    "fail_reason": event.fail_reason,
                }

        # 🗺 悪い結果はワールドマップにも反映（その場で1マス後退）
        #    ※マクロショック延期は上の _handle_ipo_delay 内で大滑落(4)済み
        #    CFO逮捕は対応の良し悪しに関わらず会社への打撃なので必ず後退する
        _force_fall = getattr(event, "id", "") == "WORLD_EXEC_ARREST"
        if not is_good or _force_fall:
            _fall_label = event.title.split('（')[0].strip()[:14]
            self._map_fall(1, f"⚠ {_fall_label} — 後退…")

        # ⏳ CFO逮捕 → タイマークライシス「後任CFO選定」を開始
        #    以降、解消されるまで毎ターン必ず対応選択を提示する
        if getattr(event, "id", "") == "WORLD_EXEC_ARREST" \
                and not any(tc["kind"] == "cfo_successor" for tc in self._timer_crises):
            self._timer_crises.append({"kind": "cfo_successor", "remaining": 2})

        # ⏳ 個人情報漏洩 → タイマークライシス「再発防止策の策定」を開始
        if getattr(event, "id", "") == "data_leak" \
                and not any(tc["kind"] == "data_leak_report" for tc in self._timer_crises):
            self._timer_crises.append({"kind": "data_leak_report", "remaining": 1})

        # ⏳ 従業員不祥事 → タイマークライシス「労務改善・コンプライアンス体制の報告」を開始
        if getattr(event, "id", "") == "sns_scandal" \
                and not any(tc["kind"] == "labor_compliance" for tc in self._timer_crises):
            self._timer_crises.append({"kind": "labor_compliance", "remaining": 2})

        # 結果詳細は次ターン冒頭に表示（ゲームイベントと同じ遅延表示）
        self._deferred_outcomes.append((event.title, choice.label, result_msg, is_good))

        # ── 財務インパクト（ターン末決算レポートに集計表示） ──
        d_cash = c.cash - pre_cash
        d_burn = c.quarterly_burn - pre_burn
        one_time_cost = -d_cash if d_cash < 0 else 0.0
        if one_time_cost > 0:
            self._this_turn_one_time_costs += one_time_cost

        decision_log = f"[突発] {event.title} → {choice.label[:30]}"
        if one_time_cost >= 0.5:
            decision_log += f" ｜一時費用¥{one_time_cost:,.0f}M"
        if d_cash > 0.5:
            decision_log += f" ｜資金調達+¥{d_cash:,.0f}M"
        if abs(d_burn) >= 0.5:
            sign = "+" if d_burn >= 0 else ""
            decision_log += f" ｜継続費用{sign}¥{d_burn:,.0f}M/Q"
        self._turn_decisions.append(decision_log)

        pending_parts = []
        if one_time_cost >= 0.5:
            pending_parts.append(f'<span style="color:#ffaa55">当Q一時費用 ¥{one_time_cost:,.0f}M計上予定</span>')
        if d_cash > 0.5:
            pending_parts.append(f'<span style="color:#55ddaa">資金流入 +¥{d_cash:,.0f}M</span>')
        if abs(d_burn) >= 0.5:
            sign = "+" if d_burn >= 0 else ""
            col = "#ffaa55" if d_burn > 0 else "#55ddaa"
            arrow = "▲" if d_burn > 0 else "▼"
            pending_parts.append(f'<span style="color:{col}">{arrow} 継続費用{sign}¥{d_burn:,.0f}M/Q</span>')
        if pending_parts:
            self._add(
                f'<div class="pending-fin-note">'
                f'<span class="pfn-label">📋 当Q決算に反映予定</span> '
                + ' ｜ '.join(pending_parts)
                + f'<br><span class="pfn-sub">▼ ターン末の四半期決算レポートで全体影響を確認できます</span>'
                + f'</div>'
            )

        self._pending_fortune = None
        self.phase = Phase.CONTINUE
        self._next_action = "advance_turn"
        self._ph("► ターンを進める...")

    # ──────────────────────────────────────────
    # ターン進行
    # ──────────────────────────────────────────
    def _advance_turn(self):
        c = self.company
        t = self.timeline

        # ─ 四半期決算の前に、決断によるPre変化量を記録 ─
        pre_adv_cash   = c.cash
        pre_adv_burn_applied = c.quarterly_burn   # 決断で変わった後のburn
        decisions_taken = list(self._turn_decisions)
        one_time_this_q = self._this_turn_one_time_costs

        # 今Qの一時費用を「前Q費用」に引き渡し、リセット
        self._prev_turn_one_time_costs   = self._this_turn_one_time_costs
        self._this_turn_one_time_costs   = 0.0
        # 四半期スロット用 吉凶カウントをリセット
        self._this_turn_good             = 0
        self._this_turn_bad              = 0
        self._pending_fortune            = None   # 安全リセット

        # ─ 四半期財務処理（売上成長・繰延認識・Burn差引） ─
        _pre_adv_scores = self._get_score_snapshot()
        pre_fin_cash = c.cash
        pre_fin_rev  = c.revenue.recognized
        advance_quarter_financials(c, t.n_period, t.quarter)
        post_fin_cash = c.cash
        post_fin_rev  = c.revenue.recognized
        # YTD累計に当Q分を加算（Q1開始時にリセット済み）
        self._ytd_rev  += c.revenue.recognized
        self._ytd_burn += c.quarterly_burn
        self._ytd_otc  += one_time_this_q
        # 財務処理によるスコア変動を記録
        _post_adv_scores = self._get_score_snapshot()
        _adv_delta = {k: _post_adv_scores[k] - _pre_adv_scores.get(k, _post_adv_scores[k]) for k in _post_adv_scores}
        _adv_sig = {k: v for k, v in _adv_delta.items() if abs(v) >= 1}
        if _adv_sig:
            _ap = ", ".join(f"{k}{'+'if v>=0 else ''}{v:.0f}" for k, v in _adv_sig.items())
            self._score_change_reasons.append(f"四半期財務進行：{_ap}")

        # ─ 💣 爆弾発動（決算レポート前に適用してスコア差分に含める） ─
        _pre_bomb_scores = self._get_score_snapshot()
        _bomb_messages = list(tick_bombs(c))   # 会社状態を変更してメッセージを収集
        for _bm in _bomb_messages:
            c.add_event_log(f"[{t.full_label()}] 爆弾発動!")
        _post_bomb_scores = self._get_score_snapshot()
        _bomb_sig = {k: _post_bomb_scores[k] - _pre_bomb_scores.get(k, _post_bomb_scores[k]) for k in _post_bomb_scores if abs(_post_bomb_scores[k] - _pre_bomb_scores.get(k, _post_bomb_scores[k])) >= 1}
        if _bomb_sig:
            _bp = ", ".join(f"{k}{'+'if v>=0 else ''}{v:.0f}" for k, v in _bomb_sig.items())
            self._score_change_reasons.append(f"💣 爆弾発動：{_bp}")

        # ─ 💣 爆弾 HTML を決算レポートの前に表示（スコアへの影響は既に計算済み） ─
        if _bomb_messages:
            # 「しかし」vs「さらに」：当Qにイベントが発生した場合は追い打ち演出
            _had_event = (self._this_turn_good + self._this_turn_bad) > 0
            _karma_prefix = (
                "さらに、過去の決断が追い打ちをかける…"
                if _had_event else
                "しかし、過去の決断の代償が静かに牙を剥く…"
            )
            self._add(
                f'<div style="text-align:center;color:#ff8844;font-size:13px;'
                f'font-weight:700;padding:6px 0;letter-spacing:1px">'
                f'{_karma_prefix}</div>'
            )
            for bomb_msg in _bomb_messages:
                self._add(bomb_html(bomb_msg), "bomb")
            # 🗺 過去の代償でコマが滑落（爆弾1個=1マス、複数なら2マス）
            self._map_fall(1 if len(_bomb_messages) == 1 else 2, "💣 過去の代償 — 滑落！")

        # ─ 📊 四半期決算レポート 表示（爆弾効果込みのスコア差分を反映） ─
        self._render_quarter_closing_report(
            t, c,
            turn_start_cash=self._turn_start_cash,
            turn_start_burn=self._turn_start_burn,
            turn_start_rev=self._turn_start_rev,
            turn_start_mktcap=self._turn_start_mktcap,
            turn_start_shareholders=self._turn_start_shareholders,
            pre_fin_cash=pre_fin_cash,
            post_fin_cash=post_fin_cash,
            pre_fin_rev=pre_fin_rev,
            post_fin_rev=post_fin_rev,
            one_time_this_q=one_time_this_q,
            decisions_taken=decisions_taken,
        )

        old_n = t.n_period
        # 全四半期末: 決算レポートと同じ期・四半期をサイドバーに表示するため保存
        self._closing_period = (t.n_period, t.quarter, t.period_name())
        period_events = t.advance()

        if period_events.get("year_end"):
            # AGMはQ4ターン冒頭のインタラクティブイベントとして処理済み
            # ここでは期末のサマリー表示のみ行う（スコア追記は不要）
            period_label = {
                -3: "N-3期", -2: "N-2期（直前々期）",
                -1: "N-1期（直前期）", 0: "N期（申請期）",
            }.get(old_n, "")
            if period_label:
                self._add(story_rule(f"◆ {period_label} 終了 ◆", "white"))

        if period_events.get("enter_n2"):
            self._add(story_rule("◆ N-2期（直前々期）に突入！ ◆", "cyan"))
            c = self.company
            if c.has_audit_contract:
                _tier_labels = {"big": "大手監査法人（Big4系）", "mid": "中堅監査法人", "small": "小規模監査法人"}
                _tier = getattr(c, 'audit_firm_tier', '') or 'mid'
                _tier_label = _tier_labels.get(_tier, '監査法人')
                if self._pending_agm_result:
                    # N-3期Q4総会の議決結果がまだ未表示 → 「確認中」として表示
                    self._add(story_panel(
                        "📋 N-2期（直前々期）がスタートしました。<br><br>"
                        f"✅ {esc(_tier_label)}との監査契約締結が確定する予定です。<br>"
                        "▼ N-3期定時株主総会の議決結果をご確認ください。<br><br>"
                        "上場申請には N-2期・N-1期ともに<b>無限定適正意見</b>が必要です。",
                        "🔑 N-2期 監査スタート（総会議決結果を確認）", "cyan"
                    ), "advisor_panel")
                else:
                    self._add(story_panel(
                        "📋 N-2期（直前々期）がスタートしました。<br><br>"
                        f"✅ {esc(_tier_label)}との監査契約が締結済みです。<br>"
                        "N-2期から2期間の財務監査が始まります。<br>"
                        "上場申請には N-2期・N-1期ともに<b>無限定適正意見</b>が必要です。",
                        "🔑 N-2期 監査スタート", "cyan"
                    ), "advisor_panel")
            elif not c.audit_firm_agreed:
                sr_note = "✅ ショートレビュー実施済み" if c.flags.short_review_done else "⚠️ ショートレビュー未実施"
                accrual_note = "✅ 発生主義移行済み" if not c.flags.cash_basis_accounting else "⚠️ 発生主義移行未完了"
                _tier_labels = {"big": "大手監査法人（Big4系）", "mid": "中堅監査法人", "small": "小規模監査法人"}
                _tier = getattr(c, 'audit_firm_tier', '') or ''
                firm_note = f"候補先：{_tier_labels.get(_tier, '未選定')}" if _tier else "⚠️ 監査法人候補が未選定 — 中堅監査法人として受嘱審査を実施"
                if getattr(self, '_audit_emergency_countdown', 0) > 0:
                    # 緊急体制整備の再交渉が進行中 — 別途ルーレット不要（カウントダウンで処理）
                    self._add(story_panel(
                        "📋 N-2期（直前々期）がスタートしました。<br><br>"
                        "⚠️ 緊急体制整備プロジェクトの監査法人再交渉が進行中です。<br>"
                        "結果は次のターンにご報告します。<br><br>"
                        f"準備状況：{esc(sr_note)} / {esc(accrual_note)}<br>"
                        f"　　　　　{esc(firm_note)}",
                        "🔑 監査法人 受嘱交渉 — 緊急体制整備進行中", "yellow"
                    ))
                    # return しない — カウントダウンが次の begin_turn で自動処理される
                else:
                    # 緊急体制整備なし → 通常の受嘱交渉ルーレット
                    self._add(story_panel(
                        "📋 N-2期（直前々期）がスタートしました。<br><br>"
                        "⚠️ 監査法人の内諾が得られていません。緊急の受嘱交渉を行います。<br><br>"
                        f"準備状況：{esc(sr_note)} / {esc(accrual_note)}<br>"
                        f"　　　　　{esc(firm_note)}",
                        "🔑 監査契約 — 上場への最重要関門", "yellow"
                    ))
                    self._run_audit_roulette()
                    return
            else:
                # 内諾済みだがAGMで否決された等の場合
                self._add(story_panel(
                    "📋 N-2期（直前々期）がスタートしました。<br><br>"
                    "⚠️ 監査法人の内諾は得ていますが、株主総会での会計監査人選任が未完了です。<br>"
                    "次回の定時株主総会での選任決議が必要です。",
                    "🔑 N-2期 — 会計監査人選任待ち", "yellow"
                ))

        if period_events.get("enter_n1"):
            self._add(story_rule("◆ N-1期（直前期）スタート ◆", "yellow"))
            # N-1期突入で自動整備される項目
            c = self.company
            _auto_items = []
            if c.has_underwriter and not c.has_disclosure_system:
                c.has_disclosure_system = True
                _auto_items.append("✅ 適時開示体制を構築（主幹事証券と共同整備）")
            if c.has_underwriter and not c.has_insider_prevention:
                c.has_insider_prevention = True
                _auto_items.append("✅ インサイダー取引防止規程を整備（主幹事の指導により策定）")
            _auto_html = "<br>".join(_auto_items)
            if _auto_html:
                _auto_html = f"<br><br>【N-1期において現場主導で整備された体制】<br>{_auto_html}"
            self._add(story_panel(
                "直前期に入りました。2期目の監査が始まります。<br>"
                f"内部統制報告制度への対応も本格化します。{_auto_html}",
                "", "yellow"
            ))

        if period_events.get("enter_n"):
            self._add(story_rule("◆ 申請期 N期 スタート！ ◆", "red"))
            self._add(story_panel(
                "N期Q4に東証上場審査が行われます。<br>今までの準備の総決算です！",
                "", "red"
            ))
            if not c.has_underwriter:
                if c.investor_trust >= 50 and c.compliance_score >= 40:
                    c.has_underwriter = True
                    c.has_share_admin = True  # 主幹事選定に伴い株主名簿管理人を設置
                    self._add('<div class="ok-msg">✅ 主幹事証券会社が決定しました！</div>')
                else:
                    self._add('<div class="ng-msg">⚠️ 主幹事証券会社が未決定のまま申請期に入りました！</div>')
            # ③ 主幹事事前審査（N期突入時に実施）
            if c.has_underwriter:
                self._run_underwriter_pre_exam()
                return

        self.phase = Phase.CONTINUE
        self._next_action = "begin_turn"
        self._ph("► Enter で次のターンへ...")

    # ──────────────────────────────────────────
    # ③ 主幹事証券会社の引受事前審査（N期突入時）
    # ──────────────────────────────────────────
    def _run_underwriter_pre_exam(self):
        """主幹事証券会社による引受事前審査（模擬審査）。
        N-1期の運用実績を基に、主幹事がN期の本審査に推薦できるか判断。"""
        c = self.company

        # 成功確率の計算
        prob = 0.50
        _factors = []
        if c.internal_control_score >= 70:
            prob += 0.15
            _factors.append(("内部統制スコア良好", "+15%"))
        elif c.internal_control_score >= 50:
            prob += 0.08
            _factors.append(("内部統制スコア基準以上", "+8%"))
        else:
            prob -= 0.10
            _factors.append(("内部統制スコア不足", "-10%"))

        if c.compliance_score >= 70:
            prob += 0.10
            _factors.append(("コンプラスコア良好", "+10%"))
        elif c.compliance_score < 50:
            prob -= 0.10
            _factors.append(("コンプラスコア不足", "-10%"))

        if c.governance_score >= 60:
            prob += 0.08
            _factors.append(("ガバナンス体制良好", "+8%"))

        if c.accounting_quality >= 60:
            prob += 0.08
            _factors.append(("会計品質良好", "+8%"))
        elif c.accounting_quality < 40:
            prob -= 0.10
            _factors.append(("会計品質不足", "-10%"))

        if c.has_audit_contract:
            prob += 0.05
            _factors.append(("監査契約締結済み", "+5%"))
        else:
            prob -= 0.20
            _factors.append(("監査契約未締結", "-20%"))

        if c.has_monthly_closing:
            prob += 0.05
            _factors.append(("月次決算早期化済み", "+5%"))

        if not c.flags.no_outside_director:
            prob += 0.05
            _factors.append(("社外役員選任済み", "+5%"))

        if c.flags.profit_manipulation:
            prob -= 0.15
            _factors.append(("不適切な会計処理あり", "-15%"))

        prob = max(0.10, min(0.95, prob))

        # 評価要因の表示
        factor_lines = "<br>".join(
            f'&nbsp;&nbsp;{"✅" if "+" in f[1] else "❌"} {f[0]}（{f[1]}）'
            for f in _factors
        )

        self._add(story_panel(
            "📋 <strong>主幹事証券会社による引受事前審査</strong>が開始されました。<br><br>"
            "これはN期の本審査に進む前の「模擬審査」です。<br>"
            "主幹事の審査部から数百問に及ぶ質問書が送られ、<br>"
            "管理部門の総力が試される<strong>「最大の山場」</strong>です。<br><br>"
            f"<strong>評価要因：</strong><br>{factor_lines}<br><br>"
            f"<strong>推薦確率：{prob:.0%}</strong>",
            "🏦 主幹事 引受事前審査", "yellow"
        ))

        success = roll(prob)

        if success:
            c.underwriter_pre_exam_passed = True
            c.investor_trust = min(100, c.investor_trust + 10)
            self._add(story_panel(
                f"✅ <strong>引受事前審査 合格！</strong>（成功確率{prob:.0%}）<br><br>"
                "主幹事証券会社は「本審査に推薦可能」と判断しました。<br><br>"
                "💬 主幹事担当者：「N-1期の運用実績を精査した結果、<br>"
                "　管理体制は上場基準を概ね満たしていると判断します。<br>"
                "　N期Q4の東証上場審査に向けて、最終準備に入りましょう。」<br><br>"
                "▶ 投資家信頼+10",
                "🎊 事前審査 合格", "green"
            ))
            self.phase = Phase.CONTINUE
            self._next_action = "begin_turn"
            self._ph("► Enter で次のターンへ...")
        else:
            self._add(story_panel(
                f"❌ <strong>引受事前審査 不合格</strong>（成功確率{prob:.0%}）<br><br>"
                "主幹事証券会社は「現時点での推薦は見送り」と判断しました。<br><br>"
                "💬 主幹事審査部長：「管理体制に複数の改善が必要です。<br>"
                "　改善計画を提出し、N期中に再審査を受けてください。<br>"
                "　改善なき場合、上場推薦を行うことはできません。」<br><br>"
                "▶ 社長、どう対応しますか？",
                "💔 事前審査 不合格", "red"
            ))
            self._alt_choices = [
                Choice(
                    label="A. 全面改善に着手する（¥15M）",
                    description="指摘事項を全て改善。N期Q2に再審査を受ける",
                    immediate_effect=lambda comp: self._pre_exam_full_fix(comp),
                ),
                Choice(
                    label="B. 重点項目のみ対応（¥5M）",
                    description="コストを抑えるが、再審査でリスクが残る",
                    immediate_effect=lambda comp: self._pre_exam_partial_fix(comp),
                ),
            ]
            self._add(choices_html(self._alt_choices, "AB"))
            self.phase = Phase.ALT_CHOICE
            self._ph("► 選択 (A / B)")

    def _pre_exam_full_fix(self, company: Company) -> str:
        company.cash -= 15.0
        company.internal_control_score = min(100, company.internal_control_score + 15)
        company.compliance_score = min(100, company.compliance_score + 10)
        company.accounting_quality = min(100, company.accounting_quality + 10)
        company.underwriter_pre_exam_passed = True  # 全面改善→合格扱い
        return (
            "🏗️ 主幹事の指摘事項に全面対応しました。（¥15M投下）\n\n"
            "   ・内部統制+15 / コンプラ+10 / 会計品質+10\n"
            "   ・改善計画書を主幹事に提出し、再審査で承認を得ました\n\n"
            "   💬 主幹事担当者：「改善への真摯な姿勢を評価します。\n"
            "     N期Q4の上場審査に向けて正式に推薦いたします。」\n\n"
            "   ▶ 事前審査 合格（改善後）"
        )

    def _pre_exam_partial_fix(self, company: Company) -> str:
        company.cash -= 5.0
        company.internal_control_score = min(100, company.internal_control_score + 5)
        company.compliance_score = min(100, company.compliance_score + 3)
        company.underwriter_pre_exam_passed = True  # 条件付き合格
        company.flags.total_risk_score += 8
        return (
            "🏗️ 重点項目のみ改善しました。（¥5M投下）\n\n"
            "   ・内部統制+5 / コンプラ+3\n"
            "   ・主幹事は条件付きで推薦を承諾\n\n"
            "   💬 主幹事担当者：「最低限の対応は確認しましたが、\n"
            "     一部未改善の項目があります。東証審査で指摘される\n"
            "     可能性は残ります。リスクを承知の上で進めます。」\n\n"
            "   ▶ 事前審査 条件付き合格 / リスクスコア+8"
        )

    # ──────────────────────────────────────────
    # 監査契約ルーレット
    # ──────────────────────────────────────────
    def _run_audit_roulette(self):
        success, msg, prob = audit_contract_roulette(self.company)
        cls     = "green" if success else "red"
        icon    = "🎊" if success else "💔"
        title   = f"{icon} 監査法人 内諾！" if success else f"{icon} 監査契約 拒絶"
        body    = esc(msg).replace("\n", "<br>")

        # ── スピニングルーレットアニメーション付きパネル ──
        prob_pct = int(prob * 100)
        green_deg = prob * 360
        red_deg   = 360 - green_deg
        roulette_html = (
            '<div class="roulette-wrap">'
            '<div class="roulette-header">🎲 監査契約ルーレット</div>'
            '<div class="roulette-legend">'
            f'<span class="rl-green">■ 受嘱成功 {prob_pct}%</span>'
            '<span class="rl-sep">｜</span>'
            f'<span class="rl-red">■ 拒絶 {100-prob_pct}%</span>'
            '</div>'
            '<div class="roulette-disk-wrap">'
            '  <div class="roulette-pointer"></div>'
            f'  <div class="roulette-disk" data-prob="{prob:.4f}" data-success="{"1" if success else "0"}"'
            f'    style="background:conic-gradient(var(--green) 0deg {green_deg:.2f}deg, var(--red) {green_deg:.2f}deg 360deg);">'
            '  </div>'
            '  <div class="roulette-center"></div>'
            '</div>'
            '<div class="roulette-spin-label">受嘱審査中<span class="roulette-dots">...</span></div>'
            f'<div class="roulette-result {cls}" style="opacity:0;transform:translateY(8px);">'
            f'  <div class="roulette-result-title">{title}</div>'
            '</div>'
            '</div>'
        )
        self._add(roulette_html)
        # 結果の詳細はIPO顧問が説明（アバター＋1文字表示）
        self._add(story_panel(
            esc(msg).replace(chr(10), "<br>"),
            title, "green" if success else "red"
        ), "advisor_panel")

        if not success:
            self._add('<div class="decision-prompt">👤 社長、監査法人に受嘱を断られました。どう対応しますか？</div>')
            self._alt_choices = [
                Choice(
                    label="A. 急いで体制整備して別の監査法人に再チャレンジ（¥20M）",
                    description="コストはかかるが上場スケジュールを維持しようとする",
                    immediate_effect=lambda c: self._emergency_ctrl(c),
                ),
                Choice(
                    label="B. 上場を1年延期して体制整備に専念する",
                    description="確実な上場のため、じっくり準備する",
                    immediate_effect=lambda c: self._postpone(c),
                ),
            ]
            self._add(choices_html(self._alt_choices, "AB"))
            self.phase = Phase.ALT_CHOICE
            self._ph("► 選択 (A / B)")
        else:
            self.phase = Phase.CONTINUE
            self._next_action = "begin_turn"
            self._ph("► Enter で次のターンへ...")

    def _apply_alt(self, idx: int):
        choice = self._alt_choices[idx]
        self._add(f'<div class="ceo-decision">👤 社長のご決断：{"AB"[idx]}を選択</div>')
        result_msg = choice.immediate_effect(self.company)
        if not isinstance(result_msg, str):
            result_msg = f"（処理完了）{repr(result_msg)}"
        self._add(result_html(result_msg, True))
        self.phase = Phase.CONTINUE
        # ALT選択後の遷移先（既定: 次ターン。IPOウィンドウ判断後は審査へ等）
        self._next_action = getattr(self, "_alt_next_action", "") or "begin_turn"
        self._alt_next_action = ""
        self._ph("► Enter で次へ...")

    def _emergency_ctrl(self, company: Company) -> str:
        company.cash -= 20.0
        company.internal_control_score = min(100, company.internal_control_score + 20)
        company.accounting_quality = min(100, company.accounting_quality + 15)
        # 拒絶原因に基づいた改善も自動実施
        _fixes = []
        if company.flags.no_voucher_management:
            company.flags.no_voucher_management = False
            _fixes.append("証憑管理体制を緊急整備")
        if company.flags.cash_basis_accounting:
            company.accounting_quality = min(100, company.accounting_quality + 10)
            _fixes.append("発生主義会計への移行を加速（会計品質+10）")
        if not company.has_cfo:
            _fixes.append("CFO採用を並行推進中")
        fix_text = "\n   ・".join(_fixes) if _fixes else "全般的な体制強化を実施"
        self._audit_emergency_countdown = 1  # 翌四半期に再交渉結果が判明
        return (
            f"🏗️  緊急体制整備プロジェクトを立ち上げました。（¥20M投下）\n\n"
            f"   ・内部統制を全面強化中（内部統制+20 / 会計品質+15）\n"
            f"   ・{fix_text}\n"
            f"   ・新たな監査法人への打診準備を進めています"
        )

    def _run_audit_emergency_result(self):
        """緊急体制整備から2四半期後の監査法人打診結果
        成功確率は現在の体制状況に基づいて動的に計算"""
        c = self.company
        self._add(story_rule("◆ 緊急体制整備完了 — 監査法人への再打診 ◆", "yellow"))
        # 体制改善度に応じた再挑戦成功率（固定55%ではなく動的計算）
        retry_prob = 0.50
        if c.internal_control_score >= 50:
            retry_prob += 0.15
        if not c.flags.no_voucher_management:
            retry_prob += 0.10
        if not c.flags.cash_basis_accounting:
            retry_prob += 0.10
        if c.flags.short_review_done:
            retry_prob += 0.05
        if c.has_cfo:
            retry_prob += 0.05
        retry_prob = min(0.90, retry_prob)

        if roll(retry_prob):
            c.audit_firm_agreed = True
            c.has_audit_contract = True
            c.has_accounting_auditor = True
            c.auditor_trust = min(100, c.auditor_trust + 10)
            self._add(story_panel(
                f"✅ <strong>2四半期の集中整備が実を結びました！</strong>（成功確率{retry_prob:.0%}）<br><br>"
                "新たな監査法人との受嘱交渉が成立しました。<br>"
                "臨時株主総会での会計監査人選任も完了し、監査契約を正式に締結しました。<br>"
                "▶ 監査契約 ✅ / 監査法人信頼+10",
                "🎊 監査契約 締結（再挑戦成功）", "green"
            ), "advisor_panel")
        else:
            c.flags.total_risk_score += 15
            # 残存する問題点を具体的に表示
            remaining = []
            if c.flags.cash_basis_accounting:
                remaining.append("発生主義移行が未完了")
            if c.flags.no_voucher_management:
                remaining.append("証憑管理がまだ不十分")
            if not c.has_cfo:
                remaining.append("CFO不在")
            if c.internal_control_score < 50:
                remaining.append(f"内部統制スコアが依然低水準（{c.internal_control_score}）")
            remain_text = "、".join(remaining) if remaining else "総合的な体制不備"
            self._add(story_panel(
                f"❌ <strong>体制整備を進めましたが、再度断られました。</strong>（成功確率{retry_prob:.0%}）<br><br>"
                f"監査法人の指摘：「{esc(remain_text)}。さらなる改善が必要」<br>"
                "▶ リスクスコア+15<br><br>"
                "上場延期（選択肢B）を検討してください。",
                "💔 監査契約 再拒絶", "red"
            ))
        self.phase = Phase.CONTINUE
        self._next_action = "begin_turn"
        self._ph("► Enter で次のターンへ...")

    def _postpone(self, company: Company) -> str:
        company.internal_control_score = min(100, company.internal_control_score + 30)
        company.accounting_quality     = min(100, company.accounting_quality     + 25)
        company.compliance_score       = min(100, company.compliance_score       + 15)
        company.governance_score       = min(100, company.governance_score       + 10)
        company.auditor_trust          = min(100, company.auditor_trust          + 10)
        company.flags.total_risk_score = max(0,   company.flags.total_risk_score - 10)
        company.has_audit_contract     = False
        # 次の begin_turn で「1年後の体制整備完了＋監査ルーレット再挑戦」を行うフラグ
        self._audit_retry_pending = True
        return (
            "📅 上場を1年延期して体制整備に専念することを決断しました。\n\n"
            "   【1年間の集中整備】\n"
            "   ・内部管理体制の全面見直し（内部統制+30 / 会計品質+25）\n"
            "   ・コンプライアンス体制の強化（コンプラ+15）\n"
            "   ・ガバナンス改善（ガバナンス+10）\n"
            "   ・監査法人との信頼関係構築（監査信頼+10）\n"
            "   ・リスクスコア-10\n\n"
            "   ▶ 1年間の体制整備を経て、監査法人への再打診を行います。\n"
            "     次のターンで監査契約ルーレットに再挑戦します。"
        )

    # ──────────────────────────────────────────
    # 📊 IPOウィンドウ：弱気市況での申請タイミング判断
    # ──────────────────────────────────────────
    def _offer_ipo_window_choice(self):
        c = self.company
        idx = getattr(c, "market_index", 55.0)
        mult = market_multiplier(c)
        self._add(story_panel(
            f"主幹事担当者から緊急の連絡が入りました。<br><br>"
            f"「社長、申し上げにくいのですが——<strong>市況が悪化しています</strong>。<br>"
            f"現在の市況指数は <strong style='color:#ff4444'>{idx:.0f}（弱気）</strong>。"
            f"時価総額評価は通常の<strong>×{mult:.2f}</strong>まで割り引かれています。<br><br>"
            f"このまま申請すれば公開価格は大幅ディスカウント、<br>"
            f"形式要件（流通株式時価総額）の充足も危うい水準です。<br><br>"
            f"<strong>IPOウィンドウが閉じかけています。どうされますか？」</strong>",
            "📉 緊急判断：IPOウィンドウの悪化", "red"
        ), "event_panel")
        self._alt_choices = [
            Choice(
                label="A. 予定通り申請を強行する",
                description="ディスカウント覚悟で審査へ。市況がさらに悪化する前に勝負",
                immediate_effect=lambda comp: (
                    "🏃 予定通りの申請を決断しました。\n"
                    "   「待っても良くなる保証はない。今の体制で勝負する。」\n"
                    "   ▶ 現在の市況評価のまま上場審査に進みます。"
                ),
            ),
            Choice(
                label="B. 申請を3ヶ月延期し、市況回復を待つ（1四半期分の費用を消費）",
                description="準備をさらに磨きつつ回復に賭ける。ただし市況がさらに沈む可能性も",
                immediate_effect=lambda comp: self._defer_ipo_window(comp),
            ),
        ]
        self._add(choices_html(self._alt_choices, "AB"))
        self._alt_next_action = "tse_exam"
        self.phase = Phase.ALT_CHOICE
        self._ph("► 選択 (A / B)")

    def _defer_ipo_window(self, c: Company) -> str:
        from engine.finance import update_market_index
        self._ipo_window_deferred = True
        before = getattr(c, "market_index", 55.0)
        # 3ヶ月分の資金燃焼と最終仕上げ
        c.cash -= c.quarterly_burn * 0.5
        c.internal_control_score = min(100, c.internal_control_score + 5)
        c.accounting_quality     = min(100, c.accounting_quality + 5)
        c.flags.total_risk_score = max(0, c.flags.total_risk_score - 3)
        # 市況の再抽選（回復に賭ける——保証はない）
        update_market_index(c)
        after = getattr(c, "market_index", 55.0)
        trend = "回復" if after > before else "さらに悪化"
        # 新しい市況で時価総額を再評価
        from engine.finance import _get_per_multiple
        c.market_cap_million = c.revenue.recognized * _get_per_multiple(c) * market_multiplier(c)
        return (
            f"⏳ 申請を3ヶ月延期しました。（待機費用 ¥{c.quarterly_burn * 0.5:,.0f}M）\n\n"
            f"   ・最終準備を磨き込み：内部統制+5 / 会計品質+5 / リスク-3\n"
            f"   ・市況指数：{before:.0f} → {after:.0f}（{trend}）\n\n"
            f"   ▶ これ以上の延期はできません。この市況で上場審査に臨みます。"
        )

    # ──────────────────────────────────────────
    # 東証上場審査
    # ──────────────────────────────────────────
    def _run_tse_exam(self):
        c = self.company
        mkt = self.target_market

        # Market requirements
        mkt_labels = {"growth": "グロース", "standard": "スタンダード", "prime": "プライム"}
        mkt_label = mkt_labels.get(mkt, "グロース")

        # 上場審査 専用ヘッダー（大きく目立つデザイン）
        self._add(
            f'<div class="tse-exam-header">'
            f'<div class="tse-exam-label">📜 TOKYO STOCK EXCHANGE</div>'
            f'<div class="tse-exam-title">東京証券取引所<br>上場審査</div>'
            f'<div class="tse-exam-market">対象市場：{esc(mkt_label)}市場</div>'
            f'<div class="tse-exam-company">審査対象：{esc(c.name)}</div>'
            f'</div>'
        )
        self._add(story_panel(
            "「これまでの全ての意思決定が今、審査官の目に晒される——」<br><br>"
            "📋 審査官が上場審査のための有価証券報告書（Iの部）を開きます。<br>"
            "🔍 形式要件・実質審査、全項目を一つずつ確認していきます。<br><br>"
            f"<span style='color:#ffcc00;font-weight:700'>★ {esc(mkt_label)}市場 上場審査を開始します ★</span>",
            "🏢 上場審査開始", "red"
        ))

        issues: List[str] = []

        def check_section(section_title, color_cls, checks):
            rows = f'<div class="exam-section-title {color_cls}">{section_title}</div>'
            for label, ok, detail in checks:
                if ok:
                    rows += f'<div class="exam-item pass">✔ PASS &nbsp; {esc(label)}</div>'
                else:
                    rows += (
                        f'<div class="exam-item fail">✘ FAIL &nbsp; {esc(label)}'
                        f' <span class="dim-text">← {esc(detail)}</span></div>'
                    )
                    issues.append(f"{label} — {detail}")
            return f'<div class="exam-section">{rows}</div>'

        # Requirements by market
        shareholder_req = {"growth": 150, "standard": 400, "prime": 800}[mkt]
        mktcap_req = {"growth": 500, "standard": 1000, "prime": 25000}[mkt]  # 百万円
        net_assets_req = {"growth": 0, "standard": 1, "prime": 5000}[mkt]  # 百万円 (0=no req)
        profit_req_annual = {"growth": 0, "standard": 100, "prime": 2500}[mkt]  # 百万円/年 (0=no req)
        # 全市場とも直前2期分の監査証明が必要（監修済みQ2と整合）
        audit_years = {"growth": 2, "standard": 2, "prime": 2}[mkt]

        # Net assets approximation (cash as proxy)
        net_assets_ok = True if net_assets_req == 0 else c.cash >= net_assets_req
        # Annual profit (quarterly * 4)
        annual_profit = (c.revenue.recognized - c.quarterly_burn) * 4
        profit_ok = True if profit_req_annual == 0 else annual_profit >= profit_req_annual

        mktcap_label = "5億" if mkt == "growth" else ("10億" if mkt == "standard" else "100億")
        formal_checks = [
            (f"👥 株主数 {shareholder_req}人以上", c.shareholder_count >= shareholder_req, f"現在{c.shareholder_count}人"),
            (f"🏢 流通株式時価総額 {mktcap_label}円以上", c.market_cap_million >= mktcap_req, f"現在¥{c.market_cap_million:.0f}M"),
            (f"📋 監査契約締結済み（{audit_years}期監査）", c.has_audit_contract, f"直前{audit_years}期分の監査証明が必要"),
            ("🏦 主幹事証券会社選定済み", c.has_underwriter, "引受契約が必要"),
            ("🏦 主幹事引受事前審査合格", c.underwriter_pre_exam_passed, "主幹事証券の事前審査が未合格"),
        ]
        if net_assets_req > 0:
            formal_checks.append((f"💰 純資産 ¥{net_assets_req:,}M以上", net_assets_ok, f"現在¥{c.cash:.0f}M（推定）"))
        if profit_req_annual > 0:
            formal_checks.append((f"📈 年間純利益 ¥{profit_req_annual:,}M以上", profit_ok, f"推定年間¥{annual_profit:.0f}M"))

        # ── 形式要件プレチェック（2件以上未達 → 特別ゲームオーバー）──
        _formal_fails = [desc for desc, ok, _ in formal_checks if not ok]
        if len(_formal_fails) >= 2:
            mkt_label_local = {"growth": "グロース市場", "standard": "スタンダード市場", "prime": "プライム市場"}.get(mkt, "市場")
            fails_html = "".join(f'<li style="color:var(--red);margin:3px 0">❌ {esc(f)}</li>' for f in _formal_fails)
            alt_mkt = {"prime": "スタンダード市場 / グロース市場", "standard": "グロース市場"}.get(mkt, "なし（グロース市場が最低難易度）")
            self._add(story_panel(
                f"上場申請書の形式要件審査において、{mkt_label_local}の要件を複数充足できていません。<br><br>"
                f"<ul style='list-style:none;padding:0;margin:8px 0'>{fails_html}</ul>"
                f"<br>形式要件は上場審査の前提条件であり、2件以上未達の場合は申請書が受理されません。<br><br>"
                f"▶ <strong>代替案</strong>：{alt_mkt}への変更、または追加準備期間（最低1年）を検討してください。",
                f"🚫 形式要件未達 — {mkt_label_local}上場申請受理困難", "red"
            ))
            self._show_ending("tse_fail", _formal_fails)
            return

        formal_html = check_section(f"第一審査：形式要件（{mkt_label}市場）", "cyan", formal_checks)

        # ── 第二審査：実質審査（上場審査10論点ベース） ──
        # ① ガバナンス・コンプライアンス
        gov_checks = [
            ("🏛️ ① 独立社外役員の選任",
             not c.flags.no_outside_director,
             "社外取締役・社外監査役が未選任（①ガバナンス）" if not getattr(c, 'outside_director_late_appointment', False)
             else "N-1期途中選任（①ガバナンス — 審査で運用実績を追加説明要）"),
            ("⚖️ ① コンプライアンス体制（50以上）", c.compliance_score >= 50,          f"スコア{c.compliance_score}（①コンプライアンス）"),
            ("🔍 ① 反社会的勢力との関係",        not c.flags.antisocial_vendor,      "反社チェック不備（①コンプライアンス・致命的リスク）"),
            ("👷 ① 労務コンプライアンス",         not c.flags.unpaid_overtime,        "未払残業代リスク残存（①コンプライアンス）"),
        ]
        gov_html = check_section("第二審査①：ガバナンス・コンプライアンス", "yellow", gov_checks)

        # ② 会計・内部統制・開示
        acct_checks = [
            ("📒 ② 発生主義会計への完全移行",     not c.flags.cash_basis_accounting,  "現金主義会計が残存（②会計）"),
            ("📊 ② 不適切な会計処理なし",         not c.flags.profit_manipulation,    "利益操作の痕跡あり（②会計・致命的）"),
            ("🔒 ② 内部統制システム構築",          c.has_internal_control_system,      "内部統制報告制度への対応が未完了（②内部統制）"),
            ("🏗️ ② 内部管理体制（50以上）",        c.internal_control_score >= 50,     f"スコア{c.internal_control_score}（②内部統制）"),
            ("📋 ② 会計監査人の正式選任",          c.has_accounting_auditor,           "会計監査人が未選任・登記事項（②開示）"),
            ("📈 ② 会計品質（50以上）",            c.accounting_quality >= 50,         f"スコア{c.accounting_quality}（②会計品質）"),
        ]
        acct_html = check_section("第二審査②：会計・内部統制・開示", "yellow", acct_checks)

        # ③④⑤⑥⑦⑧⑨ 実質審査（事業・経営・組織・リスク）
        # ③ 高い成長可能性（グロース市場の審査の核心）
        # 守りの選択を重ねすぎて成長エンジンが弱った会社は、ここで足切りされる
        _base_g = BUSINESS_PARAMS[c.business_type].get("growth_rate", 0.05)
        _eff_g = effective_growth_rate(c)
        _growth_req = _base_g * 0.65
        sub_checks = [
            *([("📈 ③ 高い成長可能性（成長率の維持）",
                _eff_g >= _growth_req,
                f"実効成長率{_eff_g*100:.1f}%/Q — 業種水準{_base_g*100:.0f}%の65%（{_growth_req*100:.1f}%）が必要（③成長性）")]
              if mkt == "growth" else []),
            ("📋 ③ 中期経営計画の策定",           c.has_mid_term_plan,                "中期経営計画が未策定（③事業継続性）"),
            ("💰 ③ 赤字でない / 事業継続性",       c.revenue.recognized >= c.quarterly_burn * 0.7,
             f"売上¥{c.revenue.recognized:.0f}M / 費用¥{c.quarterly_burn:.0f}M（③事業継続性）"),
            ("📊 ④ 予算管理制度の整備",            c.has_budget_control,               "予算管理制度が未整備（④経営管理）"),
            ("🤝 ⑥ 関連当事者取引の整理",         not c.flags.no_related_party_review, "関連当事者取引が未整理（⑥支配関係）"),
            ("🏛️ ⑦ ガバナンス体制（50以上）",      c.governance_score >= 50,           f"スコア{c.governance_score}（⑦組織・人材）"),
            ("📄 ⑨ 定款変更・保振参加",            c.has_articles_amendment and c.has_hofuri,
             "定款変更またはほふり参加が未完了（⑨インフラ）"),
            ("🔒 ⑨ 職務分掌の整備",               not c.flags.no_job_separation,       "出納・記帳の分離が未実施（⑨業務プロセス）"),
            ("💣 総合リスクスコア（60未満）",       c.flags.total_risk_score < 60,       f"現在{c.flags.total_risk_score}（上限60）"),
        ]
        sub_html = check_section("第二審査③〜⑩：事業・経営管理・組織・リスク", "yellow", sub_checks)

        substance_html = gov_html + acct_html + sub_html
        self._add(f'<div class="exam-container">{formal_html}{substance_html}</div>')
        self._add(story_panel(
            "▶ 上場審査10論点（東証実質審査の重点確認事項）<br><br>"
            "① ガバナンス・コンプライアンス（反社、労務、取締役会機能）<br>"
            "② 会計・内部統制・開示（収益認識、監査意見、決算体制）<br>"
            "③ 事業継続性・収益性（赤字、顧客集中、ビジネスモデル）<br>"
            "④ 経営管理体制（予実・KPI・数値管理）<br>"
            "⑤ 資本政策・株主構成（流通株式比率、SO設計）<br>"
            "⑥ 関連当事者・支配関係（利益相反、オーナー取引）<br>"
            "⑦ 組織・人材（キーパーソン依存、管理部門の充足）<br>"
            "⑧ リスク・訴訟・外部要因（知財、紛争、外部リスク管理）<br>"
            "⑨ インフラ・業務プロセス（基幹系、属人化、セキュリティ）<br>"
            "⑩ 主幹事・審査プロセス（引受姿勢、説明力、対応品質）",
            "📚 上場審査10論点 — 審査官の評価軸", "cyan"
        ))

        # ── 審査結果を次フェーズへ持ち越す ──
        self._tse_pending_issues = issues
        all_substance = gov_checks + acct_checks + sub_checks
        pass_count = sum(1 for _, ok, _ in formal_checks if ok) + sum(1 for _, ok, _ in all_substance if ok)
        total_count = len(formal_checks) + len(all_substance)
        fail_count = len(issues)

        self._tse_pass_total = (pass_count, total_count)

        # ── 書類審査 → 審査官との質疑応答（ボス戦）へ ──
        self._add(story_panel(
            "書類審査が終わりました。続いて、審査官との<strong>質疑応答（面談審査）</strong>が行われます。<br><br>"
            "審査官は社長であるあなた自身に、上場制度・内部管理体制への理解を直接問います。<br>"
            "回答内容次第で審査官の心証（懸念ゲージ）が変動し、<strong>最終判定に影響します</strong>。<br><br>"
            "🟢 懸念が十分に解消 → 指摘事項1件が条件付きで容認されることも<br>"
            "🔴 懸念が増大 → 指摘事項が追加され、審査不通過のリスクが高まる",
            "👨‍⚖️ 審査官との質疑応答へ", "red"
        ))
        self.phase = Phase.CONTINUE
        self._next_action = "exam_battle"
        self._ph("► 質疑応答に進む...")

    # ──────────────────────────────────────────
    # TSE審査 ボス戦：審査官との質疑応答
    # ──────────────────────────────────────────
    EXAM_BATTLE_QUESTIONS = 5   # 1回の審査で出題される問題数

    def _exam_q_text(self, q) -> str:
        v = q["question"]
        if isinstance(v, dict):
            return v.get(self.target_market, next(iter(v.values())))
        return v

    def _exam_q_answer(self, q) -> int:
        v = q["answer"]
        if isinstance(v, dict):
            return v.get(self.target_market, next(iter(v.values())))
        return v

    def _exam_gauge_html(self) -> str:
        g = max(0, min(100, self._exam_gauge))
        if g < 35:
            color, face = "#44dd66", "😌"
        elif g < 65:
            color, face = "#ffaa44", "🤨"
        else:
            color, face = "#ff5555", "😠"
        return (
            f'<div style="margin:10px 0;padding:10px 14px;background:rgba(0,0,0,.35);'
            f'border:1px solid #334;border-radius:8px">'
            f'<div style="font-size:11px;color:#99a;letter-spacing:1px;margin-bottom:6px">'
            f'{face} 審査官の懸念ゲージ：<span style="color:{color};font-weight:700">{g}</span> / 100'
            f'<span style="color:#667;margin-left:10px">（低いほど良い ── 20以下で懸念解消 / 65以上で指摘追加）</span></div>'
            f'<div style="height:12px;background:#181828;border-radius:6px;overflow:hidden">'
            f'<div style="width:{g}%;height:100%;background:{color}"></div></div>'
            f'</div>'
        )

    def _start_exam_battle(self):
        c = self.company
        # 連動問題：プレイ履歴のフラグに応じて必ず出題する
        trig = {
            "no_cost_accounting": bool(getattr(c.flags, "no_cost_accounting", False)
                                       or getattr(c.flags, "no_inventory_count", False)),
            "unpaid_overtime": bool(getattr(c.flags, "unpaid_overtime", False)),
        }
        triggered = [q for q in EXAM_QUESTIONS if q["trigger"] != "common" and trig.get(q["trigger"], False)]
        common = [q for q in EXAM_QUESTIONS if q["trigger"] == "common"]
        _rand.shuffle(common)
        selected = (triggered + common)[: self.EXAM_BATTLE_QUESTIONS]
        _rand.shuffle(selected)

        self._exam_qs = selected
        self._exam_idx = 0
        self._exam_gauge = 50
        self._exam_correct = 0

        self._add(
            '<div class="tse-exam-header">'
            '<div class="tse-exam-label">⚔️ FINAL EXAMINATION</div>'
            '<div class="tse-exam-title">審査官との質疑応答</div>'
            f'<div class="tse-exam-market">全{len(selected)}問 ── 社長ご自身の言葉でお答えください</div>'
            '</div>'
        )
        self._add(story_panel(
            "「それでは社長、いくつか直接お伺いします」<br><br>"
            "審査官が書類から目を上げ、あなたをまっすぐ見つめました。<br>"
            "ここからは顧問の助言なし。<strong>4年間の上場準備で学んだ知識</strong>が試されます。",
            "👨‍⚖️ 審査官", "red"
        ))
        self._add(self._exam_gauge_html())
        self._show_exam_question()

    def _show_exam_question(self):
        from types import SimpleNamespace
        q = self._exam_qs[self._exam_idx]
        no = self._exam_idx + 1
        total = len(self._exam_qs)
        linked = "" if q["trigger"] == "common" else (
            '<span style="color:#ff8866;font-size:11px;margin-left:8px">'
            '⚠ 御社の経営判断に関わる質問</span>'
        )
        self._add(
            f'<div style="margin:14px 0 6px;padding:14px 16px;'
            f'background:linear-gradient(135deg,#16101e,#1e1428);'
            f'border:2px solid #8855cc;border-radius:10px">'
            f'<div style="font-size:11px;color:#aa88dd;letter-spacing:2px;margin-bottom:6px">'
            f'👨‍⚖️ 審査官の質問 {no} / {total}　【{esc(q["title"])}】{linked}</div>'
            f'<div style="font-size:15px;color:#eee;font-weight:600;line-height:1.7">'
            f'{esc(self._exam_q_text(q))}</div>'
            f'</div>'
        )
        choices = [SimpleNamespace(label=t, description="", profit_hint="", risk_hint="")
                   for t in q["choices"]]
        self._add(choices_html(choices, "ABCD"))
        self.phase = Phase.EXAM_BATTLE
        self._ph("► 回答をダブルクリックで選択...")

    def _answer_exam_question(self, idx: int):
        q = self._exam_qs[self._exam_idx]
        ans = self._exam_q_answer(q)
        correct = (idx == ans)
        self._add(f'<div class="ceo-decision">👤 社長の回答：{"ABCD"[idx]}. {esc(q["choices"][idx])}</div>')

        if correct:
            self._exam_correct += 1
            self._exam_gauge = max(0, self._exam_gauge - 15)
            head = (
                '<div style="font-size:16px;font-weight:800;color:#44dd66;margin-bottom:6px">'
                '⭕ 正解 ── 審査官は静かに頷いた</div>'
            )
            border = "#44dd66"
        else:
            self._exam_gauge = min(100, self._exam_gauge + 15)
            head = (
                '<div style="font-size:16px;font-weight:800;color:#ff5555;margin-bottom:6px">'
                '❌ 不正解 ── 審査官の眉がぴくりと動いた</div>'
                f'<div style="font-size:13px;color:#ffaa88;margin-bottom:6px">'
                f'正しくは：{"ABCD"[ans]}. {esc(q["choices"][ans])}</div>'
            )
            border = "#ff5555"
        self._add(
            f'<div style="margin:8px 0;padding:12px 14px;background:rgba(0,0,0,.3);'
            f'border:1px solid {border};border-radius:8px">'
            f'{head}'
            f'<div style="font-size:12px;color:#bbc;line-height:1.7">'
            f'<span style="color:#88aaff;font-weight:700">📖 解説：</span>{esc(q["explanation"])}</div>'
            f'</div>'
        )
        self._add(self._exam_gauge_html())

        self._exam_idx += 1
        if self._exam_idx < len(self._exam_qs):
            self._show_exam_question()
        else:
            self._finish_exam_battle()

    def _finish_exam_battle(self):
        issues = self._tse_pending_issues
        g = self._exam_gauge
        total = len(self._exam_qs)
        correct = self._exam_correct

        # ── 質疑応答の結果を審査に反映 ──
        if g >= 65:
            issues.append(f"⑩ 審査質疑応答 — 経営者の上場制度理解に重大な懸念（{correct}/{total}問正解）")
            self._add(story_panel(
                f"質疑応答の結果：<strong>{correct}/{total}問 正解</strong>（懸念ゲージ {g}）<br><br>"
                "「……社長ご自身の制度理解に、重大な懸念が残ると言わざるを得ません」<br><br>"
                "▶ <strong>指摘事項が1件追加</strong>されました。",
                "😠 審査官の懸念が増大", "red"
            ))
        elif g <= 20:
            relieved = ""
            for i, it in enumerate(issues):
                if "反社" not in it and "監査契約" not in it:
                    relieved = issues.pop(i)
                    break
            if relieved:
                self._add(story_panel(
                    f"質疑応答の結果：<strong>{correct}/{total}問 正解</strong>（懸念ゲージ {g}）<br><br>"
                    "「社長ご自身が制度を深く理解されていますね。これなら上場後の体制運用も期待できます」<br><br>"
                    f"▶ 的確な説明により、指摘事項<strong>「{esc(relieved)}」</strong>の懸念が条件付きで解消されました。",
                    "😌 審査官の懸念が解消", "green"
                ))
            else:
                self._add(story_panel(
                    f"質疑応答の結果：<strong>{correct}/{total}問 正解</strong>（懸念ゲージ {g}）<br><br>"
                    "「完璧です。制度をご自身の言葉で語れる経営者は、そう多くありません」",
                    "😌 審査官が深く頷いた", "green"
                ))
        else:
            self._add(story_panel(
                f"質疑応答の結果：<strong>{correct}/{total}問 正解</strong>（懸念ゲージ {g}）<br><br>"
                "「……承知しました。ご回答は審査記録に残させていただきます」<br>"
                "審査官は表情を変えずに書類へ目を戻しました。",
                "🤨 質疑応答 終了", "yellow"
            ))

        # ── 最終判定前のプレビュー ──
        pass_count, total_count = getattr(self, "_tse_pass_total", (0, 0))
        fail_count = len(issues)
        if fail_count == 0:
            verdict_color = "#00dd88"
            verdict_icon = "🟢"
            verdict_text = "懸念事項はすべて解消 — 審査官が最終承認の判断を下そうとしています"
        elif fail_count <= 2:
            verdict_color = "#ffaa44"
            verdict_icon = "🟡"
            verdict_text = f"{pass_count}/{total_count}項目クリア — {fail_count}件の問題点あり。審査官が協議しています"
        else:
            verdict_color = "#ff5555"
            verdict_icon = "🔴"
            verdict_text = f"{pass_count}/{total_count}項目クリア — {fail_count}件の重大問題。審査官の表情が険しい"

        self._add(
            f'<div style="margin:20px 0;padding:20px;'
            f'background:linear-gradient(135deg,#0a0a1a,#111128);'
            f'border:2px solid {verdict_color};border-radius:10px;text-align:center">'
            f'<div style="font-size:36px;margin-bottom:8px">{verdict_icon}</div>'
            f'<div style="font-size:14px;color:#aaa;letter-spacing:2px;margin-bottom:6px">CHECKING RESULTS...</div>'
            f'<div style="font-size:15px;color:{verdict_color};font-weight:700">{esc(verdict_text)}</div>'
            f'<div style="margin-top:16px;font-size:12px;color:#666;letter-spacing:1px">'
            f'審査官が審査書類を精査中です。判定に数分かかる場合があります...</div>'
            f'</div>'
        )
        self.phase = Phase.CONTINUE
        self._next_action = "tse_verdict"
        self._ph("► 審査結果を確認する...")

    # ──────────────────────────────────────────
    # TSE審査 Phase 2：最終判定の発表
    # ──────────────────────────────────────────
    def _run_tse_verdict(self):
        """TSE審査の最終判定を劇的に演出する"""
        c = self.company
        mkt_labels = {"growth": "グロース", "standard": "スタンダード", "prime": "プライム"}
        mkt_label = mkt_labels.get(self.target_market, "グロース")
        issues = self._tse_pending_issues
        self._tse_pending_issues = []

        # ── 審査発表ヘッダー ──
        self._add(
            f'<div style="text-align:center;padding:24px 16px;'
            f'background:linear-gradient(180deg,#050510 0%,#0a0a20 100%);'
            f'border-radius:10px;margin-bottom:4px">'
            f'<div style="font-size:11px;color:#556;letter-spacing:4px;margin-bottom:6px">'
            f'TOKYO STOCK EXCHANGE</div>'
            f'<div style="font-size:20px;color:#ffffff;font-weight:900;letter-spacing:3px;margin-bottom:4px">'
            f'東京証券取引所</div>'
            f'<div style="font-size:13px;color:#778;letter-spacing:2px">'
            f'{esc(mkt_label)}市場 上場審査 ── 最終判定</div>'
            f'</div>'
        )

        if not issues:
            # ── マクロショック確率判定 ──
            if self._macro_shock_active:
                shock = self._macro_shock_active
                pass_prob = shock["pass_prob"]
                shock_name = shock["name"]
                shock_roll = _rand.random()
                self._add(story_panel(
                    f"チェックリスト項目は全てクリアしましたが、<br>"
                    f"<strong>{esc(shock_name)}</strong>の影響が審査に重大な影響を与えています。<br><br>"
                    f"🎲 市場環境判定：承認確率 <strong>{int(pass_prob*100)}%</strong>",
                    f"⚠️ {esc(shock_name)}ショック — 市場環境判定", "red"
                ))
                if shock_roll >= pass_prob:
                    # マクロショックにより審査不通過
                    self._add(
                        f'<div style="text-align:center;padding:32px 20px;'
                        f'background:linear-gradient(135deg,#150a00,#2a1400,#150a00);'
                        f'border:3px solid #ff8844;border-radius:12px;margin:8px 0">'
                        f'<div style="font-size:48px;margin-bottom:8px">⚠️</div>'
                        f'<div style="font-size:24px;font-weight:900;color:#ff8844;'
                        f'letter-spacing:3px;text-shadow:0 0 20px rgba(255,136,68,.6)">'
                        f'上 場 審 査 不 通 過</div>'
                        f'<div style="font-size:13px;color:#aa6655;margin-top:8px;letter-spacing:2px">'
                        f'LISTING REVIEW FAILED</div>'
                        f'<div style="margin-top:16px;font-size:14px;color:#ffccaa">'
                        f'{esc(shock["fail_reason"])}</div>'
                        f'</div>'
                    )
                    self._add("", "ipo_failure_sound")
                    self._add(
                        f'<div style="padding:14px 16px;background:rgba(255,60,30,.08);'
                        f'border:1px solid rgba(255,60,30,.3);border-radius:8px;margin-top:8px">'
                        f'<div style="font-size:12px;color:#ff8866;font-weight:700;margin-bottom:8px;letter-spacing:1px">'
                        f'【{esc(shock_name)}ショックの影響】</div>'
                        f'<div style="padding:3px 0;color:#ffaa88">{esc(shock["fail_reason"])}</div>'
                        f'</div>'
                    )
                    self._show_ending("delay", [f"{shock_name}ショックによる市場環境悪化"])
                    return
                # 確率判定をパスした場合は通常の承認フローへ

            # ════════ 上場承認 ════════
            self._add(
                f'<div style="text-align:center;padding:32px 20px;'
                f'background:linear-gradient(135deg,#0a1500,#1a2f00,#0a1500);'
                f'border:3px solid #44dd44;border-radius:12px;margin:8px 0">'
                f'<div style="font-size:48px;margin-bottom:8px">🔔</div>'
                f'<div style="font-size:28px;font-weight:900;color:#44ff44;'
                f'letter-spacing:4px;text-shadow:0 0 30px rgba(68,255,68,.8)">'
                f'上 場 承 認</div>'
                f'<div style="font-size:14px;color:#88ff88;margin-top:10px;letter-spacing:2px">'
                f'LISTING APPROVED</div>'
                f'<div style="margin-top:16px;font-size:15px;color:#cceebb">'
                f'{esc(c.name)} の {esc(mkt_label)}市場への上場が正式に承認されました</div>'
                f'<div style="margin-top:12px;font-size:12px;color:#557744;letter-spacing:1px">'
                f'N-3期からの4年間にわたる全ての準備が、今この瞬間に実を結びました</div>'
                f'</div>'
            )
            # 花火は _show_ending 側で登頂演出の後に発火する
            self._show_ending("success", [])
        else:
            # ════════ 審査不通過 ════════
            fatal = any("反社" in i or "監査契約" in i for i in issues)
            fail_count = len(issues)

            if fatal:
                rejection_title = "上 場 申 請 却 下"
                rejection_sub = "APPLICATION REJECTED"
                rejection_color = "#ff3333"
                rejection_bg = "linear-gradient(135deg,#150000,#2a0000,#150000)"
                rejection_msg = "重大なコンプライアンス違反により、上場申請が却下されました。"
                rejection_icon = "🚫"
            else:
                rejection_title = "上 場 審 査 不 通 過"
                rejection_sub = "LISTING REVIEW FAILED"
                rejection_color = "#ff8844"
                rejection_bg = "linear-gradient(135deg,#150a00,#2a1400,#150a00)"
                rejection_msg = f"{fail_count}件の問題点が解消されていません。上場は最低1年延期されます。"
                rejection_icon = "⚠️"

            self._add(
                f'<div style="text-align:center;padding:32px 20px;'
                f'background:{rejection_bg};'
                f'border:3px solid {rejection_color};border-radius:12px;margin:8px 0">'
                f'<div style="font-size:48px;margin-bottom:8px">{rejection_icon}</div>'
                f'<div style="font-size:24px;font-weight:900;color:{rejection_color};'
                f'letter-spacing:3px;text-shadow:0 0 20px rgba(255,80,80,.6)">'
                f'{rejection_title}</div>'
                f'<div style="font-size:13px;color:#aa6655;margin-top:8px;letter-spacing:2px">'
                f'{rejection_sub}</div>'
                f'<div style="margin-top:16px;font-size:14px;color:#ffccaa">'
                f'{esc(rejection_msg)}</div>'
                f'</div>'
            )
            self._add("", "ipo_failure_sound")

            # 問題点リスト
            issue_lines = "".join(f'<div style="padding:3px 0;color:#ffaa88">✘ {esc(i)}</div>' for i in issues)
            self._add(
                f'<div style="padding:14px 16px;background:rgba(255,60,30,.08);'
                f'border:1px solid rgba(255,60,30,.3);border-radius:8px;margin-top:8px">'
                f'<div style="font-size:12px;color:#ff8866;font-weight:700;margin-bottom:8px;letter-spacing:1px">'
                f'【審査官指摘事項 {fail_count}件】</div>'
                f'{issue_lines}'
                f'</div>'
            )
            self._show_ending("dismissed" if fatal else "delay", issues)

    # ──────────────────────────────────────────
    # 上場延期 → 1年後同時期から再スタート
    # ──────────────────────────────────────────
    def _handle_ipo_delay(self, shock_name: str, after_story_html: str = ""):
        """マクロショックによる上場延期。1年後の同時期から再スタートする。"""
        c = self.company
        t = self.timeline

        # 現在の期・四半期を記録（+1Qずらして再スタート：同Qだと同一イベントが再表示される）
        restart_period = t.n_period
        restart_quarter = t.quarter + 1
        if restart_quarter > 4:
            restart_quarter = 1
            restart_period = min(0, restart_period + 1)  # N期を超えないよう制限
        period_labels = {-3: "N-3期", -2: "N-2期（直前々期）",
                         -1: "N-1期（直前期）", 0: "N期（申請期）"}
        restart_label = period_labels.get(restart_period, f"N{restart_period}期")

        # 延期演出
        self._add("", "ipo_failure_sound")
        # 🗺 マクロショックで大きく滑落
        self._map_fall(4, f"⚠ {shock_name} — 大滑落！")
        self._add(story_panel(
            f"<strong>{esc(shock_name)}</strong>の影響を受け、上場を1年延期する決断を下しました。<br><br>"
            f"主幹事証券担当者：「市場環境を考えれば賢明なご判断です。<br>"
            f"体制は整っていますので、環境回復後に速やかに再申請しましょう。」<br><br>"
            f"▶ <strong>1年後の{esc(restart_label)} Q{restart_quarter}から上場準備を再開します。</strong>",
            f"📅 上場1年延期 — {esc(shock_name)}による外部環境悪化", "yellow"
        ))
        if after_story_html:
            self._add(after_story_html)

        # ── 1年経過の演出 ──
        self._add(
            f'<div style="text-align:center;padding:24px 16px;margin:12px 0;'
            f'background:linear-gradient(135deg,#0a0a20,#1a1a30);'
            f'border:2px solid #5588aa;border-radius:10px">'
            f'<div style="font-size:20px;margin-bottom:8px">⏳</div>'
            f'<div style="font-size:16px;font-weight:700;color:#88bbdd;letter-spacing:2px">'
            f'── 1 年 後 ──</div>'
            f'<div style="font-size:13px;color:#7799bb;margin-top:8px">'
            f'{esc(shock_name)}の影響が収束し、市場環境が回復しつつあります</div>'
            f'<div style="font-size:12px;color:#99ccee;margin-top:6px">'
            f'{esc(restart_label)} Q{restart_quarter} から上場準備を再開</div>'
            f'</div>'
        )

        # ── 橋渡しナラティブ（ショック種別に応じた1年後の状況描写） ──
        _bridge_texts = {
            "大規模災害": (
                "1年の歳月が静かに流れた。首都圏に未曽有の被害をもたらした大地震は、"
                "まだ傷跡を残しながらも、社会は少しずつ復興の歩みを刻んでいる。"
                "あの日以来、社長は社員の生活再建と事業の立て直しに全力を注いできた。"
                "そして今、ようやく東証への道が再び開こうとしている。"
            ),
            "パンデミック": (
                "感染症の嵐から1年が経過した。"
                "人々の生活は少しずつ元の形を取り戻しつつあり、"
                "株式市場にも資金が戻ってきた。"
                "この1年間、社長は体制の磨き上げに徹した。再びIPOの扉が開く時が来た。"
            ),
            "金融危機": (
                "金融市場の嵐から1年が経った。"
                "各国の政策対応が奏功し、株式市場は底打ちから反転上昇を果たしている。"
                "社長はこの1年を雌伏の期間として、財務基盤と内部管理体制を徹底的に鍛え上げた。"
                "いよいよ、東証の審査官の前に再び立つ時だ。"
            ),
            "地政学リスク": (
                "地政学的な緊張が和らぎ、サプライチェーンも安定を取り戻した。"
                "この1年間で事業の足固めを進めた社長は、"
                "改めて東証上場への準備を加速させる決断を下した。"
            ),
        }
        _bridge_texts["市場急落"] = (
            "株式市場の急落から1年が経過した。"
            "各国の金融緩和と企業業績の回復を受け、市場は底打ちから力強い反転を果たしている。"
            "あのとき1年の延期を選んだことで、内部体制は一段と充実した。"
            "時価総額も回復軌道に乗り、IPOウィンドウが再び開いた。"
            "社長は確信を持って、再び東証への扉をノックする。"
        )
        _bridge = _bridge_texts.get(shock_name,
            "1年が経過し、市場環境は落ち着きを取り戻した。"
            "社長は再び上場準備を本格化させる。")
        self._add(story_panel(
            esc(_bridge).replace(chr(10), "<br>"),
            f"📖 1年後 — {esc(restart_label)} Q{restart_quarter} 再スタート", "cyan"
        ))

        # ── タイムラインを1年延期位置にリセット ──
        # 同じ n_period, quarter に戻す（1年後の同時期）
        t.n_period = restart_period
        t.quarter = restart_quarter

        # 1年経過による自然な変化
        # ・資金：1年分の運営費を消費（ただし売上も入る）
        annual_net = (c.revenue.recognized - c.quarterly_burn) * 4
        c.cash += annual_net  # 4四半期分のネットCF
        if c.cash < 50:
            c.cash = 50  # 最低限の生存保証

        # ・売上成長（1年分）
        from engine.finance import BUSINESS_PARAMS
        growth_rate = BUSINESS_PARAMS[c.business_type].get("growth_rate", 0.05)
        for _ in range(4):
            c.revenue.recognized *= (1 + growth_rate)

        # ・スコア微減（1年のブランク）
        c.internal_control_score = max(0, c.internal_control_score - 3)
        c.employee_morale = max(0, c.employee_morale - 5)
        c.investor_trust = max(0, c.investor_trust - 5)
        # ・リスクスコア軽減（時間経過で一部リスクが風化）
        c.flags.total_risk_score = max(0, c.flags.total_risk_score - 10)
        # ・市場環境回復による時価総額の微改善
        c.market_cap_million *= 1.05

        # ── YTD累計をリセット（新しい期の開始） ──
        self._ytd_rev  = 0.0
        self._ytd_burn = 0.0
        self._ytd_otc  = 0.0
        self._prev_turn_one_time_costs = 0.0
        self._this_turn_one_time_costs = 0.0

        # スコアスナップショットをリセット
        self._prev_scores = self._get_score_snapshot()
        self._prev_cash = c.cash
        self._prev_rev  = c.revenue.recognized
        # ターン開始スナップショットをリセット（延期前の値が前Q比に混入しないよう）
        self._turn_start_cash         = c.cash
        self._turn_start_burn         = c.quarterly_burn
        self._turn_start_rev          = c.revenue.recognized
        self._turn_start_mktcap       = c.market_cap_million
        self._turn_start_shareholders = c.shareholder_count
        self._score_change_reasons    = []

        # マクロショックフラグをクリア
        self._macro_shock_active = None

        # イベントリストを再生成（再スタート用）
        self._game_events = get_fresh_events()
        self._world_events = get_fresh_world_events()
        self._scheduled_crises = []  # クライシスを再スケジュール
        self._schedule_ai_crises()

        # 延期前ターンの保留結果をクリア（再スタートターンで前Q結果報告を非表示にする）
        self._deferred_outcomes.clear()
        self._pending_agm_result = None

        # セーブ（_save_game内で self._queue=[] クリアされるため演出を退避→復元）
        _pre_save_queue = list(self._queue)
        _save_game(self)
        self._queue.extend(_pre_save_queue)  # 橋渡しナラティブをキューに戻す

        # ターン開始へ
        self.phase = Phase.CONTINUE
        self._next_action = "begin_turn"
        self._ph("► 1年後… 上場準備を再開する")

    # ──────────────────────────────────────────
    # エンディング
    # ──────────────────────────────────────────
    def _show_ending(self, ending_type: str, issues: list):
        _delete_save()   # ゲーム終了時はセーブデータを削除
        c = self.company
        # 🗺 ワールドマップ：成功なら山頂の鐘へ登頂 → 花火、失敗なら大きく滑落
        if ending_type == "success":
            self._map_goal()
            self._add("", "ipo_fireworks")   # 登頂を見届けてから花火＋音楽
            # 🏁 ライバルより先に上場できたら「業界初」ボーナス表示
            _rv = getattr(self, "_rival", None)
            if _rv and not _rv.get("listed"):
                self._add(story_panel(
                    f"📰 <strong>【速報】{esc(c.name)}、業界初の上場！</strong><br><br>"
                    f"競合の{esc(_rv['name'])}（現在{_rv['pos']}/26マス）を抑えて、"
                    f"見事に先頭で東証の鐘を鳴らしました。<br>"
                    f"業界のリーディングカンパニーとして、投資家の注目を一身に集めます。",
                    "🏁 上場レース 勝利！", "gold-bright"
                ), "event_panel")
        else:
            self._map_fall(3, "⚠ 上場ならず — 滑落…")
        if ending_type == "success":
            # ─ 詳細な成功ストーリーパネル（花火・音楽は直前の登頂演出後に発火済み）─
            mkt_labels = {"growth": "グロース市場", "standard": "スタンダード市場", "prime": "プライム市場"}
            mkt = mkt_labels.get(self.target_market, "グロース市場")
            checklist_done = sum([
                c.flags.short_review_done, c.has_audit_contract, c.has_underwriter,
                not c.flags.cash_basis_accounting, not c.flags.no_inventory_count,
                c.has_mid_term_plan, c.has_capital_policy, c.has_cfo,
                not c.flags.no_related_party_review, c.has_authority_rules,
                c.has_budget_control, c.has_internal_audit, c.has_antisocial_system,
                c.has_ip_protection, not c.flags.no_outside_director,
                c.has_internal_control_system, c.has_accounting_auditor,
                c.has_share_admin, c.has_disclosure_system, c.has_insider_prevention,
                c.has_articles_amendment, c.has_hofuri, c.has_governance_report,
            ])
            annual_rev = c.revenue.recognized * 4
            self._add(story_panel(
                f'<div style="text-align:center;padding:8px 0">'
                f'<div style="font-size:30px;font-weight:900;color:#ffd700;'
                f'text-shadow:0 0 20px rgba(255,215,0,.6);letter-spacing:.08em">'
                f'🔔 上場の鐘が鳴り響く 🔔</div>'
                f'<div style="font-size:18px;color:#cceeff;margin:8px 0 16px">'
                f'{esc(c.name)} が {esc(mkt)} に上場を果たしました！</div>'
                f'</div>'
                f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0">'
                f'<div style="background:rgba(255,215,0,.08);border:1px solid rgba(255,215,0,.3);'
                f'border-radius:6px;padding:10px;text-align:center">'
                f'<div style="font-size:11px;color:#9bc8e8;margin-bottom:4px">📈 推定時価総額</div>'
                f'<div style="font-size:22px;font-weight:900;color:#ffd700">'
                f'¥{c.market_cap_million:,.0f}M</div></div>'
                f'<div style="background:rgba(0,220,136,.08);border:1px solid rgba(0,220,136,.3);'
                f'border-radius:6px;padding:10px;text-align:center">'
                f'<div style="font-size:11px;color:#9bc8e8;margin-bottom:4px">💹 年間売上（換算）</div>'
                f'<div style="font-size:22px;font-weight:900;color:#00dd88">'
                f'¥{annual_rev:,.0f}M</div></div>'
                f'<div style="background:rgba(0,180,255,.08);border:1px solid rgba(0,180,255,.3);'
                f'border-radius:6px;padding:10px;text-align:center">'
                f'<div style="font-size:11px;color:#9bc8e8;margin-bottom:4px">📋 チェックリスト</div>'
                f'<div style="font-size:22px;font-weight:900;color:#44aaff">'
                f'{checklist_done}/23 ✔</div></div>'
                f'<div style="background:rgba(200,100,255,.08);border:1px solid rgba(200,100,255,.3);'
                f'border-radius:6px;padding:10px;text-align:center">'
                f'<div style="font-size:11px;color:#9bc8e8;margin-bottom:4px">🏢 株主数</div>'
                f'<div style="font-size:22px;font-weight:900;color:#cc77ff">'
                f'{c.shareholder_count}名</div></div>'
                f'</div>'
                f'<div style="margin-top:14px;padding:12px;'
                f'background:rgba(255,215,0,.07);border-radius:6px;'
                f'border-left:3px solid #ffd700;font-size:13px;color:#ffe">'
                f'「{esc(c.name)} の社長として、あなたは4年間にわたる上場準備を\n'
                f'  完遂しました。N-3期から積み重ねてきた全ての決断が、今この瞬間に実を結びました。\n\n'
                f'  東証の鐘が鳴り響く中、あなたの会社は新たな章へと踏み出します。」'
                f'</div>'.replace("\n", "<br>"),
                "👑 CONGRATULATIONS！ 上場成功 👑", "gold-bright"
            ))
        elif ending_type == "delay":
            # ipo_failure_sound は _run_tse_verdict 側で発火済み
            self._add(story_panel(
                "上場延期が決定しました<br><br>"
                "改善後に再申請が必要です。上場は最低1年延期されます。",
                "⚠ 上場延期 ⚠", "red"
            ))
            if issues:
                self._add_postmortem(issues)
        elif ending_type == "bankruptcy":
            self._add("", "ipo_failure_sound")
            self._add(story_panel(
                "資金がショートしました<br><br>"
                "上場前に資金が底をつき、事業継続が困難になりました。",
                "💔 GAME OVER — 資金ショート", "red"
            ))
        elif ending_type == "dismissed":
            # ipo_failure_sound は _run_tse_verdict 側で発火済み
            self._add(story_panel(
                "代表取締役から解任通告を受けました<br><br>"
                "コンプライアンス違反・不正の発覚により投資家・取締役会からの信頼を失いました。",
                "🚫 GAME OVER — 代表取締役解任", "red"
            ))
            dismissed_issues = [
                "累積リスクスコア — 上場審査でリスクが高すぎると判定されました",
                "コンプライアンス体制 — 法令遵守体制が不十分でした",
            ]
            self._add_postmortem(dismissed_issues)
        elif ending_type == "macro_delay":
            shock_name = issues[0] if issues else "マクロショック"
            self._add("", "ipo_failure_sound")
            self._add(story_panel(
                f"<strong>{esc(shock_name)}</strong>の影響を受け、上場を自主延期する決断を下しました。<br><br>"
                "外部環境が回復し次第、改めて上場準備を再開します。<br>"
                "社長としての冷静な判断が、会社の将来を守りました。<br><br>"
                "💬 主幹事証券担当者：「市場環境を考えれば賢明なご判断です。<br>"
                "　体制は整っていますので、環境回復後に速やかに再申請しましょう。」",
                f"📅 上場自主延期 — {esc(shock_name)}による外部環境悪化", "red"
            ))
        elif ending_type == "ipo_abandoned":
            self._add("", "ipo_failure_sound")
            self._add(story_panel(
                "上場計画が撤回されました<br><br>"
                "ダメージが蓄積した結果、東証への上場申請が不可能な状態となりました。<br>"
                "会社は存続しますが、今回の上場計画は白紙に戻ります。<br>"
                "再挑戦するには、全ての問題を解決し体制を立て直す必要があります。",
                "💔 GAME OVER — 上場計画断念", "red"
            ))

        self._add_feedback(ending_type)
        self.phase = Phase.ENDING
        self._ph("► Enter でもう一度プレイ...")

    def _add_feedback(self, ending_type: str = "success"):
        c = self.company
        self._add(story_rule("📚 実務学習フィードバック", "cyan"))

        feedbacks: List[tuple] = []
        if c.flags.unpaid_overtime:
            feedbacks.append(("⏰ 労務管理",
                "未払残業代を放置したため上場直前に労基署申告が発生しました。\n"
                "N-3期から勤怠管理システムの整備が必要でした。"))
        if c.flags.antisocial_vendor:
            feedbacks.append(("🔍 反社チェック",
                "取引先の審査を怠ったため主幹事証券会社から上場延期を通告されました。\n"
                "主幹事証券会社は全取引先の反社チェックを必ず実施します。"))
        if c.flags.no_job_separation:
            feedbacks.append(("🔒 職務分掌",
                "出納と記帳の分離が未実施のため横領リスクが高い状態が続きました。\n"
                "職務分掌は内部統制の基本中の基本です。"))
        if c.flags.cash_basis_accounting:
            feedbacks.append(("📒 収益認識",
                "現金主義から発生主義への移行が未完了でした。\n"
                "N-3期から移行に着手しないとN-2期の監査開始時に大混乱が生じます。"))
        if not c.flags.short_review_done:
            feedbacks.append(("🔍 ショートレビュー",
                "実施しなかったため潜在リスクが可視化されませんでした。\n"
                "N-3期に実施することで課題を事前に整理できます。"))
        if c.flags.audit_contract_rejected and not c.has_audit_contract:
            feedbacks.append(("📋 監査契約",
                "監査法人に受嘱を拒絶されました。\n"
                "N-2期期首までに受入体制を整えることが絶対条件です。"))
        if not feedbacks:
            if ending_type == "success":
                feedbacks.append(("🎊 総評",
                    "素晴らしい判断の連続でした！\n"
                    "IPO準備の鉄則：「短期コスト削減 ＜ 長期リスク管理」"))
            else:
                feedbacks.append(("📋 総評",
                    "今回は上場に至りませんでしたが、この経験は大きな財産です。\n"
                    "チェックリストの全項目クリアが審査通過の大前提です。\n"
                    "IPO準備の鉄則：「チェックリスト完全充足 ＋ スコア確保」"))

        for i, (title, body) in enumerate(feedbacks, 1):
            self._add(story_panel(
                esc(body).replace("\n", "<br>"),
                f"📖 教訓{i}：{esc(title)}", "cyan"
            ))

        scores = [
            ("内部管理体制", c.internal_control_score),
            ("コンプライアンス", c.compliance_score),
            ("会計品質", c.accounting_quality),
            ("ガバナンス", c.governance_score),
            ("監査法人信頼", c.auditor_trust),
            ("投資家信頼", c.investor_trust),
        ]

        def grade(s):
            if s >= 90: return "S", "#ffd700"
            if s >= 75: return "A", "#00ff88"
            if s >= 60: return "B", "#00ffff"
            if s >= 40: return "C", "#ffcc00"
            return "D", "#ff4444"

        rows = "".join(
            f'<tr><td>{esc(lbl)}</td><td>{sc}</td>'
            f'<td style="color:{gc};font-weight:700">{g}</td></tr>'
            for lbl, sc in scores
            for g, gc in [grade(sc)]
        )
        self._add(f'''
        <div class="score-summary">
            <div class="score-sum-title">◆ 最終スコアサマリー ◆</div>
            <table class="score-table">
                <thead><tr><th>カテゴリ</th><th>スコア</th><th>評価</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>''')

    def _add_postmortem(self, issues: list):
        """審査不通過・ゲームオーバー時の原因解説"""
        self._add(story_rule("🔎 社長、失敗の原因を振り返りましょう", "yellow"))

        advice_map = {
            "株主数": (
                "📌 原因：上場時公募・売出しの設計が不十分でした。\n"
                "【実務知識】株主数要件（グロース150名等）は上場日における見込み数で判定されます。\n"
                "上場申請日時点の株主数が少ないのは通例で、申請後から上場日前日までの\n"
                "公募・売出しにより充足します。証券会社が1人1単元ずつ個人投資家に配分する\n"
                "仕組みにより、実務では最低要件を大きく上回る株主数が確保されます。\n"
                "主幹事証券会社との連携による公募・売出し設計が最も重要な対策です。"
            ),
            "時価総額": (
                "📌 原因：売上成長・PER評価が目標市場の時価総額要件に届きませんでした。\n"
                "【対策】売上成長イベントを積極的に選択し、ガバナンス・コンプライアンス・投資家信頼の\n"
                "スコアを高く維持することが重要です（これらがPER倍率に影響します）。\n"
                "時価総額 = 推定売上 × PER倍率。スコアが高いほどPERが上がります。"
            ),
            "監査契約": (
                "📌 原因：N-2期期首の監査ルーレットに失敗し、契約が締結できませんでした。\n"
                "【対策】N-3期中に会計品質・内部統制スコアを50以上に引き上げることで\n"
                "監査契約の成功率が大幅に上がります。ショートレビューの実施が特に有効です。"
            ),
            "主幹事証券会社": (
                "📌 原因：主幹事証券会社が見つかりませんでした。\n"
                "【対策】N-2期〜N-1期の「主幹事証券会社選定」イベントで意思決定を行い、\n"
                "投資家信頼スコアを50以上・コンプライアンス35以上に維持することが\n"
                "選定成功の条件です。早期の投資家信頼構築が重要です。"
            ),
            "内部管理体制": (
                "📌 原因：内部統制スコアが50を下回っていました。\n"
                "【対策】N-3期の「ショートレビュー」「CFO採用」「IT整備」、\n"
                "N-2期の「職務分掌」「J-SOX準備」イベントで\n"
                "体制を整備すべきでした。監査役からの指摘も早期対応が必要です。"
            ),
            "コンプライアンス体制": (
                "📌 原因：コンプライアンス・スコアが50を下回っていました。\n"
                "【対策】「反社チェック」「関連当事者取引整理」「社外役員選任」イベントで\n"
                "スコアを積み上げる必要があります。違反リスクは早期発見・解決が原則です。"
            ),
            "会計処理": (
                "📌 原因：現金主義会計から発生主義への移行が完了していませんでした。\n"
                "【対策】N-3期の「発生主義移行」イベントで早期に対応することが必須です。\n"
                "N-2期の監査開始前に移行が完了していないと、監査自体が実施できません。"
            ),
            "関連当事者取引": (
                "📌 原因：関連当事者取引が未整理のまま申請期を迎えました。\n"
                "【対策】N-2期の「関連当事者取引整理」イベントで取引を可視化・適正化し、\n"
                "上場審査で問われる独立性を確保する必要がありました。"
            ),
            "ガバナンス体制": (
                "📌 原因：ガバナンス・スコアが50を下回っていました。\n"
                "【対策】「社外役員選任」「役員報酬制度設計」「取締役会戦略議論」などで\n"
                "ガバナンスを強化すべきでした。社外取締役・独立監査役の早期選任が鍵です。"
            ),
            "累積リスクスコア": (
                "📌 原因：リスクスコアが60以上に達し、上場審査をクリアできませんでした。\n"
                "【対策】各イベントで「先送り」や「無視」を選ぶとリスクが蓄積します。\n"
                "特にN-3期の初期イベント（ショートレビュー・証憑管理・棚卸）で\n"
                "リスクを潰していくことが最重要です。"
            ),
            "純資産": (
                "📌 原因：スタンダード/プライム市場の純資産要件を満たしていませんでした。\n"
                "【対策】IPO準備における一時費用（ショートレビュー・システム整備・監査費用等）は\n"
                "不可避ですが、それ以外の経常的なコストを抑制し営業黒字を継続することが重要です。\n"
                "各Qのコスト削減イベントで費用を最適化しながら、売上成長を維持することで\n"
                "純資産の積み上げが実現できます。グロース市場（純資産要件なし）への変更も選択肢です。"
            ),
            "年間純利益": (
                "📌 原因：スタンダード市場の利益要件（年間1億円）を達成できませんでした。\n"
                "【対策】売上成長イベントを積極活用しつつ、費用の適正化が必要です。\n"
                "利益が出ない場合はグロース市場への変更を検討してください（利益要件なし）。"
            ),

            "反社": (
                "📌 原因：反社会的勢力との関係が発覚し、上場審査で致命的な指摘を受けました。\n"
                "【①ガバナンス・コンプライアンス】N-2期の「反社チェック」イベントで全取引先のスクリーニングを\n"
                "実施することが絶対条件です。「コスト削減」で省略するのは厳禁です。"
            ),
            "発生主義": (
                "📌 原因：現金主義会計から発生主義への移行が完了していませんでした。\n"
                "【②会計・内部統制】N-3期の「発生主義・収益認識移行」イベントで早期対応が必須です。\n"
                "N-2期の監査開始前に移行が完了していないと、監査意見が限定付になります。"
            ),
            "利益操作": (
                "📌 原因：不適切な会計処理（利益操作）が監査で発覚しました。\n"
                "【②会計・内部統制】売上の前倒し計上・棚卸評価の操作は上場審査で致命的です。\n"
                "N-1期以降に業績が下ブレした場合は、誠実な下方修正が正解です。"
            ),
            "中期経営計画": (
                "📌 原因：中期経営計画が未策定のまま上場審査を迎えました。\n"
                "【③事業継続性・④経営管理】数値の裏付けとKPIとの連動が必要です。\n"
                "N-3期の「中期経営計画策定」イベントで早期に策定してください。"
            ),
            "赤字": (
                "📌 原因：売上が費用を大幅に下回り、事業継続性に懸念が生じました。\n"
                "【③事業継続性】グロース市場以外では利益要件もあります。\n"
                "売上成長イベントを積極選択し、費用の適正管理が必要でした。"
            ),
            "予算管理": (
                "📌 原因：予算管理制度が未整備のまま申請期を迎えました。\n"
                "【④経営管理体制】月次予実管理サイクルの構築がN-2期の重要課題です。\n"
                "「予算管理制度の確立」イベントで早期に整備してください。"
            ),
            "職務分掌": (
                "📌 原因：出納と記帳の分離（職務分掌）が未実施でした。\n"
                "【②内部統制・⑨業務プロセス】内部統制の基本中の基本です。\n"
                "N-3期の「職務分掌」イベントで早期に整備し、横領リスクをゼロにしてください。"
            ),
            "労務": (
                "📌 原因：未払残業代が解消されないまま上場審査を迎えました。\n"
                "【①ガバナンス・コンプライアンス】元従業員の労基署申告で発覚するリスクがあります。\n"
                "「労務コンプライアンス体制整備」イベントでN-3期から対処してください。"
            ),
        }

        # 利益要件テキストを市場別に動的生成
        _mkt = getattr(self, 'target_market', 'standard')
        if _mkt == 'prime':
            advice_map["年間純利益"] = (
                "📌 原因：プライム市場の利益要件（直近2年累計25億円以上）を達成できませんでした。\n"
                "【対策】一時費用を抑制しつつ営業黒字を継続することが重要です。\n"
                "プライム市場は財務要件が最も厳しく、スタンダード/グロース市場への変更も検討してください。"
            )
        elif _mkt == 'growth':
            advice_map["年間純利益"] = (
                "📌 グロース市場は利益要件がありません（成長可能性で評価）。\n"
                "【対策】利益よりも売上成長率・投資家信頼・ガバナンス体制の整備が評価の軸です。"
            )
        # standard は既存テキストをそのまま使用

        shown = set()
        for issue in issues:
            for keyword, advice_text in advice_map.items():
                if keyword in issue and keyword not in shown:
                    shown.add(keyword)
                    self._add(story_panel(
                        esc(advice_text).replace("\n", "<br>"),
                        f"💡 {esc(keyword)}の問題：なぜ失敗したか", "yellow"
                    ))

    # ──────────────────────────────────────────
    # 状況分析ナラティブ（Gemini AI or ルールベース）
    # ──────────────────────────────────────────
    def _add_situation_narrative(self):
        """各ターン冒頭にAIナラティブパネルを追加"""
        global _GEMINI_AVAILABLE
        t = self.timeline
        c = self.company
        is_founding = (t.n_period == -3 and t.quarter == 1)
        header_label = "🤖 創業の回想 — IPOへの第一歩" if is_founding else "🤖 今期の状況"

        ai_text = self._call_gemini_narrative()
        if ai_text:
            self._add(
                f'<div class="ai-narrative">'
                f'<div class="ain-header">{header_label}</div>'
                f'<div class="ain-body">{esc(ai_text).replace(chr(10), "<br>")}</div>'
                f'</div>'
            )
        else:
            # Gemini不使用時：N-3期Q1は創業フォールバック文
            if is_founding:
                fallback = (
                    f"あれから何年が経つだろうか。{c.name}を立ち上げた日のことは、今でも鮮明に覚えている。"
                    "資金も人脈も十分ではなかったが、社長はこの事業に確かな可能性を感じていた。"
                    "N-4期を乗り越え、小さくても着実な成果が積み重なってきた。"
                    "そして今日、東証上場を目指すIPO準備が本格的に幕を開ける。"
                    "この先に待ち受けるのは試練か、それとも栄光か——答えはまだ誰も知らない。"
                )
                self._add(
                    f'<div class="ai-narrative">'
                    f'<div class="ain-header">{header_label}</div>'
                    f'<div class="ain-body">{esc(fallback).replace(chr(10), "<br>")}</div>'
                    f'</div>'
                )
                return
            # AIが使えない理由を明示
            if not _GEMINI_AVAILABLE:
                reason = f"APIキー未設定 or 初期化失敗 — {esc(_GEMINI_INIT_REASON)}"
                detail = ""
            elif self._last_gemini_error:
                # 実際のAPIエラーを表示（診断用）
                import time as _t
                err = self._last_gemini_error
                hint = ""
                # 全キーの状態を集計
                now = _t.time()
                n_keys = len(_gemini_keys)
                n_alive = sum(1 for b in _gemini_key_backoffs if b <= now)
                key_status = f"利用中キー {n_alive}/{n_keys}"
                # 最も早く解禁するキーの時刻
                min_resume = min((b for b in _gemini_key_backoffs if b > now), default=0)
                resume_str = _t.strftime("%H:%M", _t.localtime(min_resume)) if min_resume > 0 else "?"

                if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower() or "全APIキー" in err:
                    is_daily = ("PerDay" in err or "per_day" in err.lower()
                                or "GenerateRequestsPerDay" in err
                                or "free_tier_requests" in err.lower())
                    if n_alive == 0:
                        if is_daily:
                            reason = f"全{n_keys}キー1日上限到達 — 翌朝09:00頃(UTC+9)に自動解禁"
                            hint = f"💡 Googleクォータは翌UTC0時(日本時間09:00頃)リセット。{resume_str}以降に自動回復 / またはキーを追加"
                        else:
                            reason = f"全{n_keys}キー瞬間枠超過 — {resume_str}に自動回復"
                            hint = "💡 同時呼出が多すぎ。少し待てば自動再開します。"
                    else:
                        reason = f"次キーへ切替中 ({key_status})"
                        hint = "💡 次のターンで別キーに切替します。"
                elif "timeout" in err.lower():
                    reason = "タイムアウト（ネットワーク遅延）"
                elif "model" in err.lower() and ("not found" in err.lower() or "invalid" in err.lower()):
                    reason = f"モデル名エラー — {_GEMINI_MODEL}"
                else:
                    reason = "API応答失敗"
                detail = (f'<div class="ain-body" style="color:#ff9944;font-size:0.75em">'
                          f'詳細: {esc(err[:300])}</div>')
                if hint:
                    detail += (f'<div class="ain-body" style="color:#ffcc66;font-size:0.78em;margin-top:4px">'
                               f'{esc(hint)}</div>')
            else:
                reason = "スロットル（連続呼び出しをスキップ）"
                detail = ""
            self._add(
                f'<div class="ai-narrative" style="border-left-color:#ff8866;opacity:.7">'
                f'<div class="ain-header" style="color:#ff8866">⚠ AIナラティブ OFF — {reason}</div>'
                f'{detail}'
                f'<div class="ain-body">（ルールベースのモノローグを表示します）</div>'
                f'</div>'
            )
            self._add_ceo_monologue()   # フォールバック

    def _gemini_throttle(self, context: str = "") -> bool:
        """Gemini呼び出しの前にインターバルを確認する（コンテキスト別）。
        True=呼び出し可能、False=スキップ（エラー表示なし）
        コンテキストが異なれば同時呼び出し可能（narrative と outcome は独立）"""
        global _gemini_last_call_by_ctx, _GEMINI_MIN_INTERVAL
        import time as _time
        # コンテキストを大分類に正規化（"outcome-good"/"outcome-bad" → "outcome"）
        ctx_key = context.split("-")[0] if context else "default"
        now = _time.time()
        last = _gemini_last_call_by_ctx.get(ctx_key, 0.0)
        elapsed = now - last
        if elapsed < _GEMINI_MIN_INTERVAL:
            print(f"  [AI] Throttle({ctx_key}): skipping (only {elapsed:.1f}s since last call)")
            return False
        _gemini_last_call_by_ctx[ctx_key] = now
        return True

    def _gemini_generate(self, prompt: str, *, max_tokens: int, temperature: float,
                          timeout: float, context: str) -> Optional[str]:
        """Geminiにテキスト生成を依頼。429時は自動的に次キーでリトライ（最大len(keys)回）。
        成功したら本文を返す。全キー枯渇 or 非429エラーなら None を返す。"""
        global _GEMINI_AVAILABLE
        if not _GEMINI_AVAILABLE:
            return None
        if not self._gemini_throttle(context):
            return None

        max_attempts = max(1, len(_gemini_clients))
        last_err: Optional[Exception] = None
        for attempt in range(max_attempts):
            client, key_idx = _get_active_client()
            if client is None:
                self._last_gemini_error = "全APIキーが枠超過状態"
                return None
            try:
                import concurrent.futures as _cf
                def _call():
                    from google.genai import types as _gtypes
                    return client.models.generate_content(
                        model=_GEMINI_MODEL, contents=prompt,
                        config=_gtypes.GenerateContentConfig(
                            max_output_tokens=max_tokens, temperature=temperature
                        ),
                    )
                with _cf.ThreadPoolExecutor(max_workers=1) as ex:
                    resp = ex.submit(_call).result(timeout=timeout)
                text = (resp.text or "").strip()
                if text:
                    self._last_gemini_error = ""
                    if attempt > 0:
                        print(f"  [AI] {context} succeeded after retry on key#{key_idx+1}")
                    else:
                        print(f"  [AI] {context} generated ({len(text)} chars, key#{key_idx+1})")
                    return text
                return None   # 空応答
            except Exception as e:
                last_err = e
                err_str = str(e)
                is_429 = ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                          or "quota" in err_str.lower())
                self._handle_gemini_error(e, context, key_idx)
                if not is_429:
                    return None   # 429以外のエラーはリトライしない
                # 429: 次キーが利用可能なら少し待ってからリトライ
                nxt_client, _ = _get_active_client()
                if nxt_client is None:
                    return None   # 全キー枯渇
                import time as _retry_t
                _retry_t.sleep(2.0)   # RPM超過防止のため2秒待機してから次キーへ
                # ループ継続 → 次キーで再試行
        return None

    def _handle_gemini_error(self, e: Exception, context: str, key_idx: int = -1):
        """Gemini APIエラーを共通処理する。429なら該当キーをバックオフ→次キーへ切替。"""
        global _GEMINI_BACKOFF_SECS, _GEMINI_BACKOFF_DAILY
        import time as _time
        err_str = str(e)
        self._last_gemini_error = err_str[:600]
        is_quota = "429" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str
        is_503   = "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str.lower()
        if is_503 and key_idx >= 0:
            # 503: サービス一時不可（高負荷）→ 120秒のバックオフ
            import time as _t5
            _mark_key_backoff(key_idx, 120)
            resume_t = _t5.strftime("%H:%M", _t5.localtime(_t5.time() + 120))
            print(f"  [WARN] Key #{key_idx+1}: 503 high-demand → {resume_t}まで120秒待機")
            client, new_idx = _get_active_client()
            if client is None:
                print(f"  [WARN] 全キーが503 — ルールベースに切替")
        elif is_quota and key_idx >= 0:
            # RPD（1日制限）か RPM（瞬間制限）かを判別
            is_daily = ("PerDay" in err_str or "per_day" in err_str.lower()
                        or "GenerateRequestsPerDay" in err_str
                        or "free_tier_requests" in err_str.lower())
            backoff_until = _next_utc_midnight() if is_daily else None
            if backoff_until is None:
                import time as _t2
                backoff_until = _t2.time() + _GEMINI_BACKOFF_SECS
            kid = _key_id(_gemini_keys[key_idx]) if key_idx < len(_gemini_keys) else "?"
            limit_kind = "1日上限(RPD)" if is_daily else "瞬間上限(RPM)"
            import time as _t2
            resume_t = _t2.strftime("%m/%d %H:%M", _t2.localtime(backoff_until))
            print(f"  [WARN] Key #{key_idx+1} ({kid}): 429 {limit_kind} → {resume_t}まで待機")
            print(f"  [WARN] Full error: {err_str[:300]}")
            # backoff_untilはUNIX時刻。_mark_key_backoffは「秒数」を受け取る設計なので差分で渡す
            import time as _t3
            _mark_key_backoff(key_idx, backoff_until - _t3.time())
            # 次のキーが利用可能なら、次回呼び出しで自動的にそちらに切り替わる
            client, new_idx = _get_active_client()
            if client is None:
                print(f"  [WARN] 全キーが枠超過 — ルールベースに切替")
        else:
            print(f"  [WARN] Gemini {context} error: {err_str}")

    def _call_gemini_agm_narrative(self, period_label: str, choice_label: str,
                                    is_good: bool, is_founding: bool) -> Optional[str]:
        """定時株主総会 議決結果の直後に表示するナラティブを生成（3〜4文）"""
        global _GEMINI_AVAILABLE
        if not _GEMINI_AVAILABLE:
            return None

        c = self.company
        t = self.timeline

        if is_founding:
            prompt = f"""あなたはIPO準備シミュレーションゲームのナレーターです。
場面：{c.name}（{c.business_type.value}）のN-4期 定時株主総会が無事終了しました。
これは会社設立後はじめての定時総会であり、すべての議案が可決されました。
社長はIPO（東証上場）を目指し、今まさにN-3期（上場準備の本格スタート）を迎えています。

以下の内容で3〜4文の日本語ナラティブを生成してください：
- 創業から今日までの道のりへの感慨・創業の思いを1文
- N-4期の成果（小さくてもチームが成長した、事業が軌道に乗り始めたなど）を1文
- 今日から始まるIPO準備への決意・緊張感を1文
- 箇条書き・記号・英語・専門用語禁止。純粋な日本語文章のみ。「社長」という言葉を必ず使う。"""
        else:
            tone = "安堵と達成感、しかし課題への緊張が混じる" if is_good else "懸念と緊張感、立て直しへの決意"
            prompt = f"""あなたはIPO準備シミュレーションゲームのナレーターです。
場面：{c.name}（{c.business_type.value}）の{period_label} 定時株主総会が終了しました。
議案：「{choice_label}」 結果：{"可決・良好" if is_good else "波乱あり・懸念残る"}
上場まで残り{t.quarters_until_ipo()}Q。手元資金¥{c.cash:.0f}M。

以下の内容で3〜4文の日本語ナラティブを生成してください：
- 総会が終わった後の{"安堵の空気・達成感" if is_good else "重苦しい空気・緊張感"}を1文
- {"承認を得て次のステップへ向かう前向きな気持ち" if is_good else "生じた懸念・今後対処すべき課題"}を1文
- IPO準備の観点から今期やるべきことへの決意を1文
- トーン：{tone}
- 箇条書き・記号・英語・専門用語禁止。純粋な日本語文章のみ。「社長」という言葉を必ず使う。"""

        return self._gemini_generate(
            prompt, max_tokens=350, temperature=0.88, timeout=8.0,
            context="agm_narrative",
        )

    def _render_agm_narrative(self, text: Optional[str], is_good: bool,
                              agm_result: str = "", n_period: int = -4):
        """AGM後ナラティブをパネルとして出力（Gemini不可時はルールベースフォールバック）

        n_period は「総会の対象期」（= 開催四半期の属する期 − 1）。
        例: N-2期Q1に開催される総会は N-3期総会なので n_period=-3 を渡す。"""
        if not text:
            # フォールバック（ルールベース）— 総会結果・対象期に応じて文章を変える
            # 期ラベルの取り違えを防ぐため、文面は極力一般的な表現とする
            period_labels = {-4: "N-4期", -3: "N-3期", -2: "N-2期（直前々期）", -1: "N-1期（直前期）"}
            plabel = period_labels.get(n_period, "")
            if is_good:
                if n_period == -4:
                    text = (f"総会は和やかな雰囲気のまま閉幕した。"
                            f"株主たちの顔に安堵の色が見える。社長はふと、会社を起こした日のことを思い出した。"
                            f"IPO準備は今日からが本番だ。まずは内部管理体制の整備から着手しなければならない。")
                elif n_period == -3:
                    text = (f"{plabel}定時株主総会が無事終了した。"
                            f"監査法人との関係も軌道に乗り、ガバナンス体制が少しずつ形になってきている。"
                            f"社長は会場を出るとき、IPO準備顧問と短く言葉を交わした。"
                            f"「来期（直前期）が本当の勝負です」—その言葉が頭を離れなかった。")
                elif n_period == -2:
                    text = (f"{plabel}定時株主総会が終わった。"
                            f"上場申請まで残りわずか。社長室に戻った社長は、ここまで積み上げてきた準備を静かに振り返った。"
                            f"東証の審査官に胸を張って説明できる状態にあるか。自問しながら、"
                            f"最後の仕上げに向けてスタッフへの指示を出し始めた。")
                else:
                    text = ("ようやく定時株主総会が終わった。株主たちの信任を得た今、社長の肩には安堵と同時に"
                            "重大な責任がずっしりとのしかかる。上場に向けた仕上げはここからが本番だ。")
            else:
                if n_period == -3:
                    text = (f"{plabel}総会は波乱含みだった。"
                            f"内部管理体制の不備への懸念が株主から寄せられた。"
                            f"社長はその夜、執務室で長い時間を過ごした。"
                            f"上場に向けて、取り組むべき課題が山積している。")
                elif n_period == -2:
                    text = (f"ようやく定時株主総会が終わった。だが空気は重い。"
                            f"株主からの厳しい指摘は上場審査への不安を高める。"
                            f"社長は即座に幹部を集め、課題解決の緊急タスクフォースを立ち上げることを宣言した。"
                            f"上場申請まで、後退は許されない。")
                else:
                    text = ("総会は重苦しい空気のまま幕を閉じた。株主からの懸念は払拭されておらず、"
                            "社長はその夜、執務室で長い時間を過ごした。問題を先送りする余裕はもうない。")
        border_col = "#00cc66" if is_good else "#ff6644"
        self._add(
            f'<div class="ai-narrative" style="border-left-color:{border_col};margin-bottom:8px">'
            f'<div class="ain-header">🤖 総会後の社長室</div>'
            f'<div class="ain-body">{esc(text).replace(chr(10), "<br>")}</div>'
            f'</div>'
        )

    def _call_gemini_narrative(self) -> Optional[str]:
        """Gemini Flash でターン開始時のナラティブを生成（8秒タイムアウト）"""
        global _GEMINI_AVAILABLE, _gemini_narrative_cache
        if not _GEMINI_AVAILABLE:
            return None

        c = self.company
        t = self.timeline
        sid_key = id(self)
        turn_key = f"{t.n_period}:{t.quarter}"

        # 同じターンでのキャッシュ
        if _gemini_narrative_cache.get(sid_key, (None,))[0] == turn_key:
            return _gemini_narrative_cache[sid_key][1]

        rw = c.runway_quarters()
        _otc_for_ai = getattr(self, '_prev_turn_one_time_costs', 0.0)
        net = c.revenue.recognized - c.quarterly_burn - _otc_for_ai
        # YTD純利益（サイドバーと一致させる）
        _ytd_r = getattr(self, '_ytd_rev', 0.0)
        _ytd_b = getattr(self, '_ytd_burn', 0.0)
        _ytd_o = getattr(self, '_ytd_otc', 0.0)
        _ytd_net = _ytd_r - _ytd_b - _ytd_o
        risk = c.flags.total_risk_score

        # ── N-3期Q1（ゲーム開始ターン）専用プロンプト ──
        if t.n_period == -3 and t.quarter == 1:
            prompt = f"""あなたはIPO準備シミュレーションゲームの敏腕ナレーターです。
場面：{c.name}（{c.business_type.value}）の社長がIPO準備の本格スタート（N-3期Q1）を迎えました。
手元資金¥{c.cash:.0f}M。上場まで{t.quarters_until_ipo()}Qの長い旅が始まります。

以下の内容で5〜6文の日本語ナラティブを生成してください：
- 会社を立ち上げた日の記憶・創業の思いを1〜2文で情景描写
- N-4期（創業期）の成果と苦労——小さくても確かな手応えを感じた出来事を1文
- 今日からIPO準備が本格的に始まるという節目の緊張感・決意を1文
- 東証への上場という遠くて大きな目標への問いかけで締める1文
- ビジネスドラマ風の小説調。「社長」という言葉を必ず一度使う。
- 箇条書き・記号・英語・専門用語禁止。純粋な日本語文章のみ。"""
            text = self._gemini_generate(
                prompt, max_tokens=450, temperature=0.92, timeout=8.0,
                context="narrative",
            )
            if text:
                _gemini_narrative_cache[sid_key] = (turn_key, text)
            return text

        # ランウェイ評価ラベル（決算レポートの「資金残存」と同じ基準）
        _rw_eval = (
            "資金十分（黒字継続・財務上の問題なし）" if rw >= 99 else
            f"余裕あり（約{rw // 4}年分 — 財務上の問題なし）" if rw >= 8 else
            f"注意（残り{rw}Q — 慎重な資金管理が必要）" if rw >= 4 else
            f"⚠ 資金枯渇間近（残り{rw}Q — 即座の対応が必要）"
        )
        critical = []
        if rw <= 4:           critical.append(f"資金残存{_rw_label(rw)}（ショート危機）")
        if c.investor_trust < 30: critical.append(f"投資家信頼{c.investor_trust}（危険水域）")
        if c.auditor_trust < 30:  critical.append(f"監査法人信頼{c.auditor_trust}（危険水域）")
        if risk > 50:         critical.append(f"累積リスク{risk}/100（上場審査NG域に接近）")
        if c.compliance_score < 25: critical.append("コンプライアンス体制が崩壊寸前")
        if c.flags.ipo_force_delay: critical.append("上場延期フラグが発動中！")

        biz_context = {
            "SaaS":  "生成AI・LLMが主要プロダクト機能を代替しつつある業界大変革期",
            "FinTech": "金融庁規制強化・暗号資産バブル崩壊が業界全体を直撃中",
            "製造業": "原材料費・物流費高騰とカーボンニュートラル規制対応が急務",
            "小売業": "EC大手の価格攻勢と消費者行動変化が実店舗モデルを脅かす",
        }.get(c.business_type.value, "")

        # N-3期Q2専用：N-4期通年純利益は未追跡のためQ1実績×2で近似
        _q2_prev_year = (
            net * 2
            if t.n_period == -3 and t.quarter == 2
               and getattr(self, '_prev_year_net', 0.0) == 0.0
            else getattr(self, '_prev_year_net', 0.0)
        )

        prompt = f"""あなたはIPO準備シミュレーションゲームの敏腕ナレーターです。
以下の経営状況を元に、社長への没入感ある日本語ナラティブを5〜6文で生成してください。

【会社】{c.name}（{c.business_type.value}）/ {t.period_name()} Q{t.quarter} / 上場まで{t.quarters_until_ipo()}Q
【財務】手元資金¥{c.cash:.0f}M / {"前期通年純利益¥" + f"{getattr(self, '_prev_year_net', net):+.0f}M" if t.quarter == 1 else (f"前期通年純利益¥{_q2_prev_year:+.0f}M / 第1四半期純利益¥{net:+.0f}M" if t.quarter == 2 else f"前Q（Q{t.quarter - 1}）純利益¥{net:+.0f}M / 当期累計純利益¥{_ytd_net:+.0f}M")} / 資金残存:{_rw_eval}
【スコア】内部統制{c.internal_control_score} コンプライアンス{c.compliance_score} ガバナンス{c.governance_score} 監査法人信頼{c.auditor_trust} 投資家信頼{c.investor_trust}
【リスク】{risk}/100（スケール：0＝リスクゼロ理想、60未満＝安全圏、70超＝危険域、80超＝審査NG水域。数値が低いほど良好。低い場合は安全として描写すること）
{"【危機要因】⚠ " + " / ".join(critical) if critical else "【状況】大きな問題は表面化していないが油断は禁物"}
【業界背景】{biz_context}

要求：
- 5〜6文の小説調ナラティブ（ビジネスドラマ風）
- 現在の経営状況を社長が体感しているように描写する
- 財務の言及ルール（四半期別・厳守）：
  Q1：「前期の通年純利益」のみ言及。「当期累計純利益」は一切使わない。必ず前期の総括から入り「さて今期Q1の課題は…」という流れで展開
  Q2：「前期通年純利益」と「第1四半期の純利益」を言及。「当期累計純利益」は絶対使わない（Q1利益＝累計のため冗長）。第1四半期の利益は単独の四半期実績として表現する（例：「第1四半期はさらにXX万円のマイナス」）。★【絶対禁止】前期通年損失と当期Q1損失を足し合わせて「合計XX万円の損失」のように合算表記することは禁止。会計期と四半期は別期間であり合算は意味を持たない★。Q2の「前期通年純利益」は現在の期の直前期（1期前）の通年純利益を指す。「前々期」（2期前）という表現は絶対使わない
  Q3・Q4：「前Q（直前四半期）の純利益」と「当期累計純利益（Q1から直前四半期までの合計）」の両方を使う。★【絶対禁止】自期内の四半期を「前期Q3」「前期Q2」等と呼ぶことは禁止。「前期」は必ず1年前の会計期を指す。自期内の直前四半期は必ず「当Q3」「当Q2」「直前四半期」「前四半期」と表現する★
  Q4固有：「最終四半期のスタート」であり「幕が閉じた」「昨期通年」「前期通年」等の完了・前期混同表現は絶対使わない
- Q1における「前期」は必ず「現在の期より1つ前の期」を指す。N-1期Q1なら「N-2期の通年純利益」、N期Q1なら「N-1期の通年純利益」と表現し、現在の期名を「前期」と呼ぶことは絶対しない
- スコアを数値で表す場合は必ずアラビア数字と「点」を使うこと（❌二十点 ✅20点 / ❌五十点 ✅50点）。漢数字・分・割・パーセントは絶対に使わない
- 財務数値も必ずアラビア数字で表記（❌五千六百万円 ✅5,600万円 / ❌マイナス二千万円 ✅-2,000万円）
- 「N-3期」「N-2期」等のNはアルファベットの「N」をそのまま使うこと（「氮」等の漢字に変換しない）
- 資金残存が「資金十分」または「余裕あり」の場合は、「しか」「わずか」等の否定表現を絶対に使わず、潤沢さを前向きに描写する
- 危機がある場合は最大限の緊張感・絶望感を演出
- 好調でも「しかし」という暗雲・伏線を入れること
- 「社長」という言葉を必ず一度使う
- 最後の文で「上場」という目標への問いかけで締める
- 箇条書きや数字・記号を使わず、純粋な文章のみ
- アルファベット・英単語（例：pyridine・gavel・rubicon・KPI等）は一切使わない。カタカナ外来語（リスク・ガバナンス等）は可
- スコア名の正式名称：「内部統制」「コンプライアンス」「ガバナンス」「監査法人信頼」「投資家信頼」「従業員士気」。略称（コンプラ等）は使わない
- 【重要】提供されたデータ内の数値のみ使用する。計算・推測・平均などにより提供データに存在しない数値を生成することは絶対に禁止"""

        text = self._gemini_generate(
            prompt, max_tokens=450, temperature=0.92, timeout=8.0,
            context="narrative",
        )
        if text:
            # 英語単語（3文字以上のアルファベット連続）が含まれる文を除去
            import re as _re2
            _en_re = _re2.compile(r'[A-Za-z]{3,}')
            if _en_re.search(text):
                # 英語単語を含む文を除去して残りを使用
                sentences = _re2.split(r'(?<=[。！？])', text)
                clean = ''.join(s for s in sentences if not _en_re.search(s))
                text = clean.strip() if len(clean.strip()) > 20 else text
            text = text.replace("氮", "N")  # GeminiがNをChinese字に誤変換するケースを修正
            _gemini_narrative_cache[sid_key] = (turn_key, text)
        return text

    def _call_gemini_outcome(self, event_title: str, choice_label: str,
                             result_msg: str, is_good: bool) -> Optional[str]:
        """選択結果をAIがドラマチックな物語として描写（3〜4文）"""
        global _GEMINI_AVAILABLE
        if not _GEMINI_AVAILABLE:
            return None

        c = self.company
        t = self.timeline
        tone = "成功・前進の高揚感と、それでも残る微かな不安" if is_good else "失敗・ダメージの重さと、立て直しへの焦り・覚悟"

        # スコア変動行（例: "内部統制+20 / ガバナンス+10"）を除去してGeminiに渡す
        # → 数値はすでに「前Q意思決定の結果報告」パネルに表示されているため重複させない
        clean_result = "\n".join(
            ln for ln in result_msg.split("\n")
            if not _re.search(r'[\w・/　]+[+\-]\d', ln) and ln.strip()
        ).strip()[:150]

        prompt = f"""あなたはIPO準備シミュレーションゲームのナレーターです。
社長が下した決断とその結末を、3〜4文の没入感あるドラマとして描写してください。

【会社】{c.name}（{c.business_type.value}）/ {t.period_name()} Q{t.quarter}
【出来事】{event_title}
【社長の決断】{choice_label[:60]}
【出来事の内容】{clean_result}
【現在の体力】手元資金¥{c.cash:.0f}M / 投資家信頼{c.investor_trust} / リスク{c.flags.total_risk_score}/100
【感情のトーン】{tone}

要求：
- 3〜4文の小説調（経営ドラマ・ビジネス小説風）
- 社長視点か、社内の空気感・人物描写を入れること
- {'この決断が光明をもたらした瞬間を描く' if is_good else 'この決断が招いた危機の深刻さ・周囲の反応を描く'}
- 最後の一文は「上場」という目標との距離感を示唆
- ★★「+20」「-10」のような数値・スコアの変化は一切書かないこと（別パネルに表示済み）★★
- 箇条書きや数字・スコア表記を使わず、純粋な文章・情感のみ
- 専門用語・英語（gavel・pyridineのようなアルファベット単語）・造語・聞き慣れない比喩は一切使わず、日本のビジネスマンが日常的に使う自然な日本語のみで書くこと
- アルファベット・英単語は絶対に使わない（KPIなど一般的なビジネス略語のカタカナ表記は可）"""

        return self._gemini_generate(
            prompt, max_tokens=300, temperature=0.95, timeout=8.0,
            context=f"outcome-{'good' if is_good else 'bad'}",
        )

    def _call_gemini_outcome_batch(self, outcomes: list) -> Optional[str]:
        """複数の意思決定結果をまとめて1回のGemini呼び出しで「その後の展開」を生成"""
        global _GEMINI_AVAILABLE
        if not _GEMINI_AVAILABLE:
            return None
        if not outcomes:
            return None
        # 1件のみの場合は従来の単独呼び出し
        if len(outcomes) == 1:
            ev_title, ch_label, res_msg, good = outcomes[0]
            return self._call_gemini_outcome(ev_title, ch_label, _strip_score_lines(res_msg), good)

        c = self.company
        t = self.timeline
        # 複数件をまとめたプロンプト構築
        events_desc = []
        overall_good = all(g for _, _, _, g in outcomes)
        overall_bad = all(not g for _, _, _, g in outcomes)
        for i, (ev_title, ch_label, res_msg, good) in enumerate(outcomes, 1):
            clean = "\n".join(
                ln for ln in _strip_score_lines(res_msg).split("\n")
                if not _re.search(r'[\w・/　]+[+\-]\d', ln) and ln.strip()
            ).strip()[:120]
            result_type = "成功" if good else "失敗"
            events_desc.append(f"  出来事{i}：{ev_title}（{result_type}）\n  決断：{ch_label[:50]}\n  内容：{clean}")

        if overall_good:
            tone = "複数の成功が重なった高揚感と、慢心への戒め"
        elif overall_bad:
            tone = "連続する困難への焦りと、それでも前を向く覚悟"
        else:
            tone = "明暗が分かれた複雑な心境と、次の一手への思索"

        events_block = "\n\n".join(events_desc)
        prompt = f"""あなたはIPO準備シミュレーションゲームのナレーターです。
社長が下した複数の決断とその結末を、4〜5文の没入感あるドラマとして一つの物語にまとめてください。

【会社】{c.name}（{c.business_type.value}）/ {t.period_name()} Q{t.quarter}
【今期の出来事（{len(outcomes)}件）】
{events_block}
【現在の体力】手元資金¥{c.cash:.0f}M / 投資家信頼{c.investor_trust} / リスク{c.flags.total_risk_score}/100
【感情のトーン】{tone}

要求：
- 4〜5文の小説調（経営ドラマ・ビジネス小説風）
- {len(outcomes)}つの出来事を自然に1つの物語として紡ぐこと（個別に分けず、連続した流れで）
- 社長視点か、社内の空気感・人物描写を入れること
- 最後の一文は「上場」という目標との距離感を示唆
- ★★「+20」「-10」のような数値・スコアの変化は一切書かないこと★★
- 箇条書きや数字・スコア表記を使わず、純粋な文章・情感のみ
- 専門用語・英語・造語は一切使わず、自然な日本語のみ
- アルファベット・英単語は絶対に使わない（KPIなど一般的なビジネス略語のカタカナ表記は可）"""

        return self._gemini_generate(
            prompt, max_tokens=400, temperature=0.95, timeout=10.0,
            context=f"outcome-batch-{len(outcomes)}",
        )

    # ──────────────────────────────────────────
    # 上場審査10論点に基づく突発的警告（ターン開始時）
    # ──────────────────────────────────────────
    def _check_spontaneous_audit_warnings(self):
        """上場審査10論点に照らして現状を診断し、見過ごせないリスクを警告パネルで通知する。
        同じ警告が繰り返し表示されないようフラグ管理する。"""
        c = self.company
        t = self.timeline
        if not hasattr(self, '_warned_flags'):
            self._warned_flags: set = set()

        # ④ 予実管理：予算管理制度ありでも予実乖離が大きい場合
        if (t.n_period >= -2
                and getattr(c, 'has_budget_control', False)
                and c.revenue.recognized < c.quarterly_burn * 0.8
                and 'budget_variance_warned' not in self._warned_flags):
            self._warned_flags.add('budget_variance_warned')
            gap_pct = int((1 - c.revenue.recognized / c.quarterly_burn) * 100)
            c.investor_trust -= 5
            c.flags.total_risk_score += 5
            self._add(story_panel(
                f"📊 <strong>予実乖離アラート：売上が費用を大幅に下回っています</strong><br><br>"
                f"現在の売上は費用の約{100-gap_pct}%水準（乖離率{gap_pct}%）。<br>"
                f"月次予実差異分析の結果、主幹事証券会社から以下の確認がありました。<br><br>"
                f"「事業計画との乖離が大きい場合、③事業継続性・④経営管理体制の両面で<br>"
                f"上場審査での重点審査事項となります。<br>"
                f"未達の原因分析と改善策を取締役会で承認・説明できる状態にしてください。<br>"
                f"乖離率±10%以内が審査での目安です。」<br><br>"
                f"▶ 投資家信頼-5 / リスクスコア+5",
                "⚠️ 予実乖離警告 — ④経営管理体制", "yellow"
            ))

        # ⑧ 訴訟リスク：IP保護未実施 + 知財フラグなし + N-1期以降
        if (t.n_period >= -1
                and not getattr(c, 'has_ip_protection', False)
                and 'ip_risk_warned' not in self._warned_flags):
            import random as _rand
            if _rand.random() < 0.35:   # 35%の確率で警告発火
                self._warned_flags.add('ip_risk_warned')
                c.flags.total_risk_score += 8
                c.investor_trust -= 5
                self._add(story_panel(
                    "⚖️ <strong>知的財産リスク：競合他社から警告書が届きました</strong><br><br>"
                    "「御社の主力サービスが自社の登録商標に類似している」との<br>"
                    "警告書が法律事務所から送付されました。<br><br>"
                    "▶ 主幹事証券会社に報告義務があります。<br>"
                    "▶ 有価証券届出書の「事業上のリスク」への記載が必要です。<br>"
                    "▶ ⑧リスク・訴訟の観点から上場審査への影響が生じる可能性があります。<br><br>"
                    "弁理士への早急な相談と、権利の有無・侵害可能性の調査が必要です。<br><br>"
                    "▶ リスクスコア+8 / 投資家信頼-5",
                    "⚠️ 知財リスク発生 — ⑧リスク・訴訟・外部要因", "red"
                ))

        # ① ガバナンス：取締役会が機能していない（社外役員なし + N-1期以降）
        # 候補内定済み(agm_deferred)または選任否決後の臨時総会対応中(rejected_needs_eogm)は警告しない
        if (t.n_period >= -1
                and c.flags.no_outside_director
                and not c.agm_deferred_outside_director
                and not c.outside_director_rejected_needs_eogm
                and 'board_warned' not in self._warned_flags):
            self._warned_flags.add('board_warned')
            self._force_outside_director_n1 = True
            c.governance_score -= 8
            c.flags.total_risk_score += 10
            self._add(story_panel(
                "🏛️ <strong>ガバナンス不備：主幹事証券会社から緊急指摘</strong><br><br>"
                "「独立社外取締役・社外監査役が未選任の状態で N-1期に突入しています。<br>"
                "上場審査では①ガバナンス・コンプライアンスの観点から<br>"
                "取締役会の実効性が最重要確認事項のひとつです。<br><br>"
                "形式的な選任ではなく、実際に経営を監督・牽制する機能が<br>"
                "N-1期を通じた運用実績として求められます。<br>"
                "このまま上場申請を進めると審査不通過のリスクが高まります。」<br><br>"
                "▶ ガバナンス-8 / リスクスコア+10",
                "🚨 社外役員未選任 — ①ガバナンス・コンプライアンス", "red"
            ))

        # ③ 顧客集中：主幹事証券会社（未選定の場合はIPOアドバイザー）から顧客集中指摘（N-2期Q2以降、初回のみ）
        if (t.n_period == -2 and t.quarter >= 2
                and not getattr(c, 'has_customer_diversification', False)
                and 'customer_conc_hint' not in self._warned_flags):
            self._warned_flags.add('customer_conc_hint')
            _fb_src = "主幹事証券会社" if c.has_underwriter else "IPOアドバイザー"
            self._add(story_panel(
                f"📋 <strong>{esc(_fb_src)}からのフィードバック</strong><br><br>"
                "「御社の売上構成を分析したところ、上位数社への依存度が高い状況です。<br>"
                "③事業継続性・収益性の観点から、顧客集中リスクへの対応方針を<br>"
                "次回の打ち合わせまでに整理しておいてください。」",
                "💡 顧客集中リスク事前通知 — ③事業継続性", "cyan"
            ))

    # ──────────────────────────────────────────
    # クライシスカスケードチェック（ターン開始前）
    # ──────────────────────────────────────────
    def _check_crisis_cascade(self) -> bool:
        """
        ゲーム中途の危機閾値チェック。
        Trueならゲーム終了処理を実施済み（呼び出し元はreturnすること）
        """
        c = self.company
        t = self.timeline

        # 強制上場延期フラグ → IPO不能エンディング
        if c.flags.ipo_force_delay and t.n_period >= 0:
            self._add(story_panel(
                "各方面からの信頼が完全に失墜し、上場審査の申請が不可能な状態となりました。<br><br>"
                "主幹事証券会社は引受停止。監査法人は意見表明を留保。<br>"
                "取締役会の決議により、IPO計画の全面撤回を決定しました。",
                "💔 IPO計画 全面撤回", "red"
            ))
            self._show_ending("ipo_abandoned", ["上場延期フラグ発動", "投資家・監査法人の信頼崩壊"])
            return True

        # 投資家信頼ゼロ圏（5以下）→ 解任エンディング
        if c.investor_trust <= 5 and t.n_period >= -1:
            self._add(story_panel(
                "投資家・株主の信頼が完全に崩壊しました。<br><br>"
                "緊急取締役会において、あなたの代表取締役職の解任が可決されました。<br>"
                "上場計画も白紙に戻り、会社は再建の道を探ることになります。",
                "🚫 代表取締役 解任通告", "red"
            ))
            self._show_ending("dismissed", [])
            return True

        # 監査法人信頼ゼロ圏（5以下）→ 監査契約解除
        if c.auditor_trust <= 5 and c.has_audit_contract:
            c.has_audit_contract = False
            c.flags.total_risk_score += 30
            self._add(story_panel(
                "監査法人からの信頼が完全に失墜しました。<br>"
                "本日付で監査契約を解除する旨の内容証明郵便が届きました。<br><br>"
                "監査契約なしでの上場申請は不可能です。リスクスコアも急増しています。<br>"
                "次の監査法人を見つけるまで、上場計画は凍結となります。",
                "⚠ 監査契約 強制解除！", "red"
            ))
            # ゲームオーバーではないが大きなペナルティ

        # リスクスコア80超 + N期 → 上場審査不能警告
        if c.flags.total_risk_score >= 80 and t.n_period >= 0 and not c.flags.ipo_force_delay:
            c.flags.ipo_force_delay = True
            self._add(story_panel(
                "累積リスクスコアが上場審査の許容限界を超えました。<br><br>"
                "東証の内規により、リスクスコアが80を超えた企業は上場審査に進めません。<br>"
                "主幹事証券会社から「審査前に全リスクを解消しない限り申請不可」と通告されました。<br><br>"
                "上場計画は事実上、断念せざるを得ない状況です。",
                "💣 累積リスク超過 — 上場審査不能", "red"
            ))
            self._show_ending("ipo_abandoned", ["累積リスクスコア80超過", "東証審査基準超過"])
            return True

        return False

    # ──────────────────────────────────────────
    # サイドバー HTML 構築
    # ──────────────────────────────────────────

    def _sidebar_finance_rows(self, c, t, net, netcol, netsign) -> list:
        """財務セクション行リスト
        決算直後（_closing_period セット時）: cp_q に基づき当Q+累計を表示
        ターン開始中（_closing_period なし）: t.quarter に基づきYTD前Q累計を表示
        """
        parts = []
        ytd_rev  = getattr(self, '_ytd_rev',  0.0)
        ytd_burn = getattr(self, '_ytd_burn', 0.0)
        ytd_otc  = getattr(self, '_ytd_otc',  0.0)
        _otc     = getattr(self, '_prev_turn_one_time_costs', 0.0)
        _cp      = getattr(self, '_closing_period', None)

        if _cp:
            # ── 四半期末直後: 決算レポートと同じ期・四半期で表示 ──
            cp_q = _cp[1]  # 閉じたばかりの四半期番号（1〜4）
            if cp_q == 1:
                # Q1閉じ後 → 単行表示（累計行不要）
                parts += [
                    f'<div class="sbr"><span>📈 売上</span><span style="color:#00cc66">¥{c.revenue.recognized:,.0f}M</span></div>',
                    f'<div class="sbr"><span>💸 費用</span><span style="color:#ffcc00">¥{c.quarterly_burn:,.0f}M</span></div>',
                    f'<div class="sbr"><span>📊 純利益</span><span style="color:{netcol}">{netsign}{net:,.0f}M</span></div>',
                ]
            else:
                # Q2〜Q4閉じ後 → 当Q + 累計(Q1〜Qn)
                # YTD累計: advance_turn内で当Q分加算前なので c.revenue.recognized を加える
                ytd_rev_full  = ytd_rev  + c.revenue.recognized
                ytd_burn_full = ytd_burn + c.quarterly_burn
                ytd_otc_full  = ytd_otc  + _otc
                ytd_net_full  = ytd_rev_full - ytd_burn_full - ytd_otc_full
                ytd_nc = "#00cc66" if ytd_net_full >= 0 else "#ff4444"
                ytd_ns = "+" if ytd_net_full >= 0 else ""
                parts += [
                    f'<div class="sbr"><span>📈 売上（当Q）</span><span style="color:#00cc66">¥{c.revenue.recognized:,.0f}M</span></div>',
                    f'<div class="sbr"><span style="color:var(--dim)">　　累計（Q1〜Q{cp_q}）</span><span style="color:#00cc66">¥{ytd_rev_full:,.0f}M</span></div>',
                    f'<div class="sbr"><span>💸 経常費用（当Q）</span><span style="color:#ffcc00">¥{c.quarterly_burn:,.0f}M</span></div>',
                    f'<div class="sbr"><span style="color:var(--dim)">　　累計（Q1〜Q{cp_q}）</span><span style="color:#ffcc00">¥{ytd_burn_full:,.0f}M</span></div>',
                ]
                if ytd_otc_full >= 0.5:
                    parts.append(
                        f'<div class="sbr"><span>🔴 一時費用（累計）</span><span style="color:#ff6644">¥{ytd_otc_full:,.0f}M</span></div>'
                    )
                parts += [
                    f'<div class="sbr"><span>📊 純利益（当Q）</span><span style="color:{netcol}">{netsign}{net:,.0f}M</span></div>',
                    f'<div class="sbr"><span style="color:var(--dim)">　　累計（Q1〜Q{cp_q}）</span><span style="color:{ytd_nc}">{ytd_ns}¥{ytd_net_full:,.0f}M</span></div>',
                ]
        else:
            # ── ターン開始中（begin_turn 後、次の決算前） ──
            if t.quarter > 1:
                # Q2以降: 当Q + 前Q末までの累計（YTD = Q1〜Q{t.quarter-1}）
                ytd_net = ytd_rev - ytd_burn - ytd_otc
                ytd_nc  = "#00cc66" if ytd_net >= 0 else "#ff4444"
                ytd_ns  = "+" if ytd_net >= 0 else ""
                parts += [
                    f'<div class="sbr"><span>📈 売上（当Q）</span><span style="color:#00cc66">¥{c.revenue.recognized:,.0f}M</span></div>',
                    f'<div class="sbr"><span style="color:var(--dim)">　　累計（Q1〜Q{t.quarter-1}）</span><span style="color:#00cc66">¥{ytd_rev:,.0f}M</span></div>',
                    f'<div class="sbr"><span>💸 経常費用（当Q）</span><span style="color:#ffcc00">¥{c.quarterly_burn:,.0f}M</span></div>',
                    f'<div class="sbr"><span style="color:var(--dim)">　　累計（Q1〜Q{t.quarter-1}）</span><span style="color:#ffcc00">¥{ytd_burn:,.0f}M</span></div>',
                ]
                if ytd_otc >= 0.5:
                    parts.append(
                        f'<div class="sbr"><span>🔴 一時費用（累計）</span><span style="color:#ff6644">¥{ytd_otc:,.0f}M</span></div>'
                    )
                parts += [
                    f'<div class="sbr"><span>📊 純利益（当Q）</span><span style="color:{netcol}">{netsign}{net:,.0f}M</span></div>',
                    f'<div class="sbr"><span style="color:var(--dim)">　　累計（Q1〜Q{t.quarter-1}）</span><span style="color:{ytd_nc}">{ytd_ns}¥{ytd_net:,.0f}M</span></div>',
                ]
            else:
                # Q1: 単行表示
                parts += [
                    f'<div class="sbr"><span>📈 売上</span><span style="color:#00cc66">¥{c.revenue.recognized:,.0f}M</span></div>',
                    f'<div class="sbr"><span>💸 費用</span><span style="color:#ffcc00">¥{c.quarterly_burn:,.0f}M</span></div>',
                    f'<div class="sbr"><span>📊 純利益</span><span style="color:{netcol}">{netsign}{net:,.0f}M</span></div>',
                ]
        return parts

    def build_sidebar(self) -> str:
        if self.company is None or self.timeline is None:
            return (
                '<div class="sb-title">◆ THE IPO PATH ◆</div>'
                '<div class="sb-title-ja">栄光への決断</div>'
                '<div class="sb-waiting">ゲーム開始前</div>'
            )

        c = self.company
        t = self.timeline
        _cp = getattr(self, '_closing_period', None)
        _display_n = _cp[0] if _cp else t.n_period
        pcol = {-3: "#4499ff", -2: "#00e5ff", -1: "#ffdd00", 0: "#ff4444"}.get(
            _display_n, "#ffffff"
        )

        def ccol(cash, burn):
            if cash <= 0 or cash < burn * 2: return "#ff4444"
            if cash < burn * 4: return "#ffcc00"
            return "#00cc66"

        def sc(v):
            if v >= 70: return "#00cc66"
            if v >= 40: return "#ffcc00"
            return "#ff4444"

        def ck(ok):
            if ok:
                return '<span class="ck-pass">✔</span>'
            return '<span class="ck-fail">✘</span>'

        def srow(label, val):
            p = min(max(val, 0), 100)
            col = sc(val)
            return (
                f'<div class="srow">'
                f'<span class="srow-lbl">{esc(label)}</span>'
                f'<span class="srow-val" style="color:{col}">{val}</span>'
                f'<div class="mini-bar"><div class="mini-fill" style="width:{p}%;background:{col}"></div></div>'
                f'</div>'
            )

        cc = ccol(c.cash, c.quarterly_burn)
        # 一時費用込みの純利益（四半期レポートと統一）
        _otc = getattr(self, '_prev_turn_one_time_costs', 0.0)
        net = c.revenue.recognized - c.quarterly_burn - _otc
        netcol = "#00cc66" if net >= 0 else "#ff4444"
        netsign = "+" if net >= 0 else ""
        rw = c.runway_quarters()
        rwcol = "#00cc66" if rw > 8 else ("#ffcc00" if rw > 4 else "#ff4444")
        risk = c.flags.total_risk_score
        riskcol = "#00cc66" if risk < 30 else ("#ffcc00" if risk < 60 else "#ff4444")

        # ① N期フェーズ進捗（N-3/N-2/N-1/N）をドットで表示
        # 到達済みフェーズ=◆、未到達=◇ （例: N-1期なら ◆◆◆◇）
        ipo_q_left = t.quarters_until_ipo()
        _phase_map = [-3, -2, -1, 0]
        q_dots = ["◆" if t.n_period >= p else "◇" for p in _phase_map]
        q_str = " ".join(q_dots)

        mkt_labels = {"growth": "グロース", "standard": "スタンダード", "prime": "プライム"}
        mkt_label = mkt_labels.get(self.target_market, "グロース")
        mkt_col = {"growth": "#00cc66", "standard": "#ffcc00", "prime": "#ff4444"}.get(self.target_market, "#00cc66")

        # 株主数と市場別要件
        sh_req = {"growth": 150, "standard": 400, "prime": 800}.get(self.target_market, 150)
        sh_col = "#00cc66" if c.shareholder_count >= sh_req else "#ff4444"

        html_parts = [
            # ① 会社名（株式会社付き）・業種を明示
            f'<div class="sb-co">{esc(c.name)}株式会社</div>',
            f'<div class="sb-biz">業種：{esc(c.business_type.value)}</div>',
            '<div class="sb-role-badge">👤 代表取締役社長</div>',
            f'<div class="sb-period" style="color:{pcol}">{esc(_cp[2] if _cp else t.period_name())} Q{_cp[1] if _cp else t.quarter}</div>',
            # Q進捗ドット + 上場審査まで残りQ数
            (f'<div class="sb-q-row">'
             f'<span class="sb-q-dots" style="color:{pcol}">{q_str}</span>'
             f'<span class="sb-q-ipo">🏁 上場審査まで残{ipo_q_left}Q</span>'
             f'</div>'),
            f'<div class="sbr"><span>🎯 目標市場</span><span style="color:{mkt_col}">{esc(mkt_label)}</span></div>',
            # ③：実株主数 + 市場別最低要件 + 潜在株主数（SO保有者）
            (f'<div class="sbr"><span>👥 実株主数</span>'
             f'<span style="color:{sh_col}">{c.shareholder_count}人'
             f'<span style="color:var(--dim);font-size:10px">（要{sh_req}+）</span></span></div>'),
            *([(f'<div class="sbr"><span style="color:var(--dim)">　↑持株会</span>'
                f'<span style="color:var(--dim);font-size:11px">毎Q+3人増加中</span></div>')]
               if c.has_esop else []),
            *([(f'<div class="sbr"><span style="color:var(--dim)">　潜在株主</span>'
                f'<span style="color:var(--dim);font-size:11px">{c.potential_shareholders}人（SO保有・未行使）</span></div>')]
               if c.potential_shareholders > 0 else []),
            '<div class="sb-sec">── 財 務 ──────────</div>',
            f'<div class="sbr"><span>💰 手元資金</span><span style="color:{cc}">¥{c.cash:,.0f}M</span></div>',
            *self._sidebar_finance_rows(c, t, net, netcol, netsign),
            f'<div class="sbr"><span>⏳ 資金持続</span><span style="color:{rwcol}">{"問題なし（黒字）" if rw >= 99 else (f"残り約{rw * 3}ヶ月" if rw >= 4 else f"⚠ 残り約{rw * 3}ヶ月！")}</span></div>',
            f'<div class="sbr"><span>🏢 時価総額</span><span style="color:#ffd700">¥{c.market_cap_million:,.0f}M</span></div>',
            # 📈 実効成長率（攻守トレードオフ反映後）
            (lambda _g=effective_growth_rate(c), _b=c.revenue.growth_rate:
                f'<div class="sbr"><span>📈 成長率/Q</span>'
                f'<span style="color:{"#00cc66" if _g >= _b else "#ff8844"}">{_g*100:.1f}%'
                f'<span style="color:var(--dim);font-size:10px">（基礎{_b*100:.0f}%）</span></span></div>')(),
            '<div class="sb-sec">── 📊 市況（IPOウィンドウ）──</div>',
            # 市況メーター：時価総額の評価倍率に直結
            (lambda _mi=getattr(c, "market_index", 55.0):
                f'<div class="sbr"><span>市況</span>'
                f'<span style="color:{"#00cc66" if _mi >= 65 else ("#ffcc00" if _mi >= 35 else "#ff4444")}">'
                f'{"🐂 強気" if _mi >= 65 else ("〜 中立" if _mi >= 35 else "🐻 弱気")} {_mi:.0f}'
                f'<span style="color:var(--dim);font-size:10px">（評価×{market_multiplier(c):.2f}）</span></span></div>')(),
            '<div class="sb-sec">── 💼 成長と管理のバランス ──</div>',
            # 🚀事業投資（戦略的な成長投資）/ 🏗現場負荷（管理対応に割いた現場リソース）
            (lambda _o=getattr(c, "offense_score", 0), _d=getattr(c, "defense_score", 0):
                f'<div class="sbr"><span>🚀 事業投資</span><span style="color:#66bbff">{_o}</span></div>'
                f'<div class="sbr"><span>🏗 現場負荷</span><span style="color:#ffcc66">{_d}</span></div>'
                + (f'<div style="font-size:10px;color:#ff8844;text-align:center">⚠ 成長と管理のバランスに注意</div>'
                   if (_o + _d) >= 4 and abs(_o - _d) >= 3 else ''))(),
            '<div class="sb-sec">── 🏁 上場レース ──────</div>',
            # ライバルとの登山レース（ワールドマップのマス位置）
            (lambda _rv=getattr(self, "_rival", None), _mp=getattr(self, "_map_pos", 0):
                ('' if not _rv else (
                    f'<div class="sbr"><span>🧗 自社</span><span>{_mp}/26マス</span></div>'
                    f'<div class="sbr"><span>🏃 {esc(_rv["name"])}</span>'
                    f'<span style="color:{"#ff4444" if _rv["listed"] else ("#ff8844" if _rv["pos"] > _mp else "#00cc66")}">'
                    + ("🔔 上場済み！" if _rv["listed"] else f'{_rv["pos"]}/26マス')
                    + '</span></div>'
                    + (f'<div style="font-size:10px;color:#ff8866;text-align:center">'
                       f'⚠ 評価-{round((1 - getattr(c, "rival_discount", 0.85)) * 100)}%（先行上場の影響）</div>'
                       if getattr(c, "rival_listed_first", False) else ''))))(),
            '<div class="sb-sec">── スコア ───────────</div>',
            srow("内統",     min(100, max(0, c.internal_control_score))),
            srow("コンプラ",  min(100, max(0, c.compliance_score))),
            srow("会計",     min(100, max(0, c.accounting_quality))),
            srow("統治",     min(100, max(0, c.governance_score))),
            srow("監査信頼",  min(100, max(0, c.auditor_trust))),
            srow("投資家信頼", min(100, max(0, c.investor_trust))),
            srow("士気",     min(100, max(0, c.employee_morale))),
            (f'<div class="srow"><span class="srow-lbl">💣上場失敗リスク</span>'
             f'<span class="srow-val" style="color:{riskcol}">{risk}</span>'
             f'<div class="mini-bar"><div class="mini-fill" style="width:{min(risk,100)}%;background:{riskcol}"></div></div></div>'),
            # ④ mood indicator 削除済み
        ]
        return "".join(html_parts)

    def build_right_sidebar(self) -> str:
        """右サイドバー：上場準備チェックリスト（④）"""
        if self.company is None:
            return ""
        c = self.company

        def ck(ok):
            if ok:
                return '<span class="ck-pass">✔</span>'
            return '<span class="ck-fail">✘</span>'

        parts = [
            '<div class="rsb-title">上場準備チェック</div>',
            # N-3期
            '<div class="sb-phase sb-phase-n3">▼ N-3期 体制構築</div>',
            f'<div class="ckrow">{ck(c.flags.short_review_done)} ショートレビュー</div>',
            f'<div class="ckrow">{ck(c.has_audit_contract)} 監査契約</div>',
            f'<div class="ckrow">{ck(c.has_underwriter)} 主幹事証券</div>',
            f'<div class="ckrow">{ck(not c.flags.cash_basis_accounting)} 発生主義会計</div>',
            f'<div class="ckrow">{ck(not c.flags.no_inventory_count)} 棚卸管理</div>',
            f'<div class="ckrow">{ck(not c.flags.no_cost_accounting)} 原価計算制度</div>',
            f'<div class="ckrow">{ck(c.has_mid_term_plan)} 中期経営計画</div>',
            f'<div class="ckrow">{ck(c.has_capital_policy)} 資本政策</div>',
            # N-2期
            '<div class="sb-phase sb-phase-n2">▼ N-2期 体制整備</div>',
            f'<div class="ckrow">{ck(c.has_monthly_closing)} 月次決算早期化</div>',
            f'<div class="ckrow">{ck(c.has_cfo)} CFO在籍</div>',
            f'<div class="ckrow">{ck(not c.flags.no_related_party_review)} 関連当事者整理</div>',
            f'<div class="ckrow">{ck(c.has_authority_rules)} 職務権限・分掌規程</div>',
            f'<div class="ckrow">{ck(c.has_budget_control)} 予算管理制度</div>',
            f'<div class="ckrow">{ck(c.has_internal_audit)} 内部監査部門</div>',
            f'<div class="ckrow">{ck(not c.flags.unpaid_overtime)} 労務コンプライアンス</div>',
            f'<div class="ckrow">{ck(c.has_antisocial_system)} 反社排除体制</div>',
            f'<div class="ckrow">{ck(c.has_ip_protection)} 知財保護</div>',
            # N-1期
            '<div class="sb-phase sb-phase-n1">▼ N-1期 運用徹底</div>',
            f'<div class="ckrow">{ck(not c.flags.no_outside_director)} 社外役員</div>',
            f'<div class="ckrow">{ck(c.has_internal_control_system)} 内部統制システム</div>',
            f'<div class="ckrow">{ck(c.has_accounting_auditor)} 会計監査人選任</div>',
            f'<div class="ckrow">{ck(c.has_share_admin)} 株主名簿管理人</div>',
            f'<div class="ckrow">{ck(c.has_disclosure_system)} 適時開示体制</div>',
            f'<div class="ckrow">{ck(c.has_insider_prevention)} インサイダー防止</div>',
            # N期
            '<div class="sb-phase sb-phase-n0">▼ N期 申請対応</div>',
            f'<div class="ckrow">{ck(c.underwriter_pre_exam_passed)} 主幹事事前審査</div>',
            f'<div class="ckrow">{ck(c.has_articles_amendment)} 定款変更</div>',
            f'<div class="ckrow">{ck(c.has_hofuri)} 保振参加</div>',  # ① 保振参加
            f'<div class="ckrow">{ck(c.has_governance_report)} ガバナンス報告書</div>',
        ]
        return "".join(parts)

    # ──────────────────────────────────────────
    # ボタンバー構築（スマホ・タッチ対応）
    # ──────────────────────────────────────────
    def build_buttons(self) -> list:
        """各フェーズに応じたボタンリストを返す [{label, value, style}]"""

        if self.phase == Phase.TITLE:
            return [{"label": "▶ ゲームを開始", "value": "", "style": "primary"}]

        if self.phase == Phase.BIZ_SELECT:
            letters = ["A", "B", "C", "D"]
            styles  = ["a",  "b",  "c",  "d"]
            btns = []
            for i, (btype, _) in enumerate(BUSINESS_PARAMS.items()):
                if i >= 4:
                    break
                btns.append({
                    "label": f"{letters[i]}  {btype.value}",
                    "value": letters[i],
                    "style": styles[i],
                })
            return btns

        if self.phase == Phase.MARKET_SELECT:
            return [
                {"label": "A グロース（★☆☆）", "value": "A", "style": "green"},
                {"label": "B スタンダード（★★☆）", "value": "B", "style": "yellow"},
                {"label": "C プライム（★★★）", "value": "C", "style": "red"},
            ]

        if self.phase == Phase.NAME_INPUT:
            return [{"label": "決定 →", "value": "__INPUT__", "style": "primary"}]

        if self.phase == Phase.CONTINUE:
            lbl_map = {
                "begin_turn":   "次のターンへ →",
                "next_event":   "次のイベントへ →",
                "advance_turn": "ターンを進める →",
                "tse_verdict":  "🔍 審査結果を確認する →",
                "exam_battle":  "👨‍⚖️ 質疑応答に進む →",
            }
            lbl = lbl_map.get(self._next_action, "次へ →")
            return [{"label": lbl, "value": "", "style": "continue"}]

        if self.phase == Phase.EVENT_CHOICE:
            # 選択肢カード自体がクリック可能なので A/B/C/D ボタンは不要
            # IPO先生ボタンのみ残す
            return [{"label": "💡 IPO先生に相談", "value": "__ADVISOR__", "style": "advisor"}]

        if self.phase == Phase.ALT_CHOICE:
            # 選択肢カード自体がクリック可能
            return []

        if self.phase == Phase.FORTUNE_CHOICE:
            # 選択肢カード自体がクリック可能
            return [{"label": "💡 IPO先生に相談", "value": "__ADVISOR__", "style": "advisor"}]

        if self.phase == Phase.EXAM_BATTLE:
            # 審査本番のため IPO先生への相談は不可。回答カード自体がクリック可能
            return []

        if self.phase == Phase.ENDING:
            return [{"label": "🔄 もう一度プレイ", "value": "", "style": "primary"}]

        return []


# ══════════════════════════════════════════════
# Flask ルーティング
# ══════════════════════════════════════════════
_LOGO_PATH      = os.path.join(os.path.dirname(__file__), "rogo.png")
# タイトル画像：同ディレクトリ内の title_bg.png を優先、なければ環境変数パス、なければ旧パス
_TITLE_IMG_PATH = (
    os.environ.get("TITLE_IMG_PATH")
    or os.path.join(os.path.dirname(__file__), "title_bg.png")
)



@app.route("/logo.png")
def serve_logo():
    """スタート画面バナー用ロゴ画像を配信する"""
    logo = os.path.abspath(_LOGO_PATH)
    if os.path.isfile(logo):
        return send_file(logo, mimetype="image/png")
    return "", 404


@app.route("/title-img.png")
def serve_title_img():
    """タイトル画面バナー画像を配信する"""
    img = _TITLE_IMG_PATH
    if os.path.isfile(img):
        return send_file(img, mimetype="image/png")
    return "", 404


@app.route("/")
def index():
    return render_template("game.html")


@app.route("/autosave", methods=["POST"])
def autosave():
    """ブラウザ閉じる時の navigator.sendBeacon() から呼ばれる自動セーブ"""
    try:
        data = request.json or {}
        sid  = data.get("sid", "")
        if sid and sid in SESSIONS:
            session = SESSIONS[sid]
            if session.company is not None and session.phase not in (Phase.TITLE, Phase.ENDING):
                ok, _, _b64 = _save_game(session)
                print(f"  [AUTOSAVE] Session {sid[:8]}... saved on browser close (ok={ok})")
    except Exception as e:
        print(f"  [WARN] Autosave error: {e}")
    return "", 204   # No Content


@app.route("/action", methods=["POST"])
def action():
    import traceback
    try:
        return _action_inner()
    except Exception as exc:
        traceback.print_exc()
        return jsonify({
            "sid": "",
            "story_items": [{"html": f'<div class="bomb-panel"><div class="bomb-title">💥 サーバーエラー</div>'
                                     f'<pre class="bomb-text">{html_module.escape(type(exc).__name__)}: '
                                     f'{html_module.escape(str(exc))}</pre></div>', "type": "normal"}],
            "placeholder": "► エラーが発生しました。ページをリロードしてください",
            "sidebar": "",
            "buttons": [],
            "clear": False,
        })


def _action_inner():
    data = request.json or {}
    sid = data.get("sid", "")
    value = data.get("value", "").strip()

    # 新規セッション
    if not sid or sid not in SESSIONS:
        sid = str(uuid.uuid4())
        session = GameSession()
        SESSIONS[sid] = session
        story_items = session.get_title_story()
        return jsonify({
            "sid": sid,
            "story_items": story_items,
            "placeholder": session._placeholder,
            "sidebar": session.build_sidebar(),
            "right_sidebar": session.build_right_sidebar(),
            "buttons": session.build_buttons(),
            "clear": True,
        })

    session = SESSIONS[sid]

    # エンディング後はリセット（セーブ削除済み）
    if session.phase == Phase.ENDING:
        del SESSIONS[sid]
        sid = str(uuid.uuid4())
        session = GameSession()
        SESSIONS[sid] = session
        story_items = session.get_title_story()
        return jsonify({
            "sid": sid,
            "story_items": story_items,
            "placeholder": session._placeholder,
            "sidebar": session.build_sidebar(),
            "right_sidebar": session.build_right_sidebar(),
            "buttons": session.build_buttons(),
            "clear": True,
        })

    # 💾 手動セーブ（どのフェーズでも機能する）
    if value == "__SAVE__" and session.company is not None:
        ok, err_msg, save_b64 = _save_game(session)
        session._queue = []
        if ok:
            session._add(
                '<div class="save-toast">💾 セーブしました！ブラウザを閉じても続きから再開できます。</div>'
            )
        else:
            import html as _html_mod
            session._add(
                f'<div class="save-toast save-toast-fail">⚠ セーブに失敗しました。<br>'
                f'<span style="font-size:11px;opacity:.8">{_html_mod.escape(err_msg)}</span></div>'
            )
        return jsonify({
            "sid": sid,
            "story_items": session._queue,
            "placeholder": session._placeholder,
            "sidebar": session.build_sidebar(),
            "right_sidebar": session.build_right_sidebar(),
            "buttons": session.build_buttons(),
            "clear": False,
            "saved_ok": ok,       # JSの _savedClean フラグ更新用
            "save_b64": save_b64, # ← localStorage に渡すBase64セーブデータ
        })

    # タイトル画面で「続きから再開」が押された場合
    if session.phase == Phase.TITLE and value == "__RESUME__":
        # localStorage経由のBase64データがあればそちらを優先
        _resume_b64 = data.get("save_b64", "")
        loaded = _load_game(save_b64=_resume_b64)
        if loaded is not None:
            _delete_save()   # セーブは「一回使い切り」—再開後は明示的に💾しないと次回ボタンが出ない
            SESSIONS[sid] = loaded
            session = loaded
            session._queue = []
            c = session.company
            t = session.timeline
            session._add(story_panel(
                f"「<strong>{esc(c.name)}</strong>」（{esc(c.business_type.value)}）の続きから再開します。<br><br>"
                f"現在の状況：<strong>{esc(t.period_name())} Q{t.quarter}</strong>"
                f" / 上場まで残り <strong>{t.quarters_until_ipo()}Q</strong>",
                "📂 ゲームを再開しました", "cyan"
            ))
            session._begin_turn()
            return jsonify({
                "sid": sid,
                "story_items": session._queue,
                "placeholder": session._placeholder,
                "sidebar": session.build_sidebar(),
            "right_sidebar": session.build_right_sidebar(),
                "buttons": session.build_buttons(),
                "clear": True,
            })
        else:
            # セーブデータが見つからない場合は新規ゲームへ
            session._queue = []
            session._add('<div class="err-msg">⚠ セーブデータが見つかりませんでした。新規ゲームを開始します。</div>')
            session._start_biz_select()
            return jsonify({
                "sid": sid,
                "story_items": session._queue,
                "placeholder": session._placeholder,
                "sidebar": session.build_sidebar(),
            "right_sidebar": session.build_right_sidebar(),
                "buttons": session.build_buttons(),
                "clear": True,
            })

    story_items, placeholder, sidebar = session.handle(value)
    return jsonify({
        "sid": sid,
        "story_items": story_items,
        "placeholder": placeholder,
        "sidebar": sidebar,
        "right_sidebar": session.build_right_sidebar(),
        "buttons": session.build_buttons(),
        "clear": False,
    })


# ══════════════════════════════════════════════
# エントリーポイント
# ══════════════════════════════════════════════
if __name__ == "__main__":
    def open_browser():
        time.sleep(1.2)
        webbrowser.open("http://127.0.0.1:5000")

    threading.Thread(target=open_browser, daemon=True).start()
    print("=" * 50)
    print("  THE IPO PATH: 栄光への決断 - Web版")
    print("  http://127.0.0.1:5000 でゲームが起動します")
    print("  Ctrl+C で終了")
    print("=" * 50)
    app.run(debug=False, port=5000, use_reloader=False)
