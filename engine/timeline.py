from dataclasses import dataclass
from models.company import Quarter


# N期: -3=N-3, -2=N-2, -1=N-1, 0=N（申請期）
N_MINUS_3 = -3
N_MINUS_2 = -2
N_MINUS_1 = -1
N_PERIOD = 0


@dataclass
class Timeline:
    n_period: int = N_MINUS_3   # 現在のN期数
    quarter: int = 1            # 現在のQ（1〜4）
    total_turns: int = 0        # 経過ターン数

    def period_name(self) -> str:
        if self.n_period == N_MINUS_3:
            return "N-3期"
        elif self.n_period == N_MINUS_2:
            return "N-2期（直前々期）"
        elif self.n_period == N_MINUS_1:
            return "N-1期（直前期）"
        elif self.n_period == N_PERIOD:
            return "N期（申請期）"
        return f"N{self.n_period}期"

    def full_label(self) -> str:
        return f"{self.period_name()} Q{self.quarter}"

    def is_audit_period(self) -> bool:
        """監査対象期間（N-2以降）"""
        return self.n_period >= N_MINUS_2

    def advance(self) -> dict:
        """1ターン進める。戻り値: イベント情報"""
        self.total_turns += 1
        events = {}

        self.quarter += 1
        if self.quarter > 4:
            self.quarter = 1
            events["year_end"] = True  # Q4終了 → 定時株主総会

            old_period = self.n_period
            self.n_period += 1
            if self.n_period > N_PERIOD:
                self.n_period = N_PERIOD  # 申請期以降は固定

            if old_period == N_MINUS_3 and self.n_period == N_MINUS_2:
                events["enter_n2"] = True  # N-2期に入る → 監査契約ルーレット
            elif old_period == N_MINUS_2 and self.n_period == N_MINUS_1:
                events["enter_n1"] = True
            elif old_period == N_MINUS_1 and self.n_period == N_PERIOD:
                events["enter_n"] = True

        return events

    def is_game_over_period(self) -> bool:
        """N期Q4終了 = ゲーム終了タイミング"""
        return self.n_period == N_PERIOD and self.quarter == 4

    def quarters_until_ipo(self) -> int:
        """上場まで残り何Q"""
        remaining_in_period = 4 - self.quarter
        remaining_periods = N_PERIOD - self.n_period
        return remaining_in_period + remaining_periods * 4
