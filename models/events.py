from dataclasses import dataclass, field  # noqa: F401 (field used in GameEvent)
from typing import Callable, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models.company import Company


@dataclass
class Choice:
    label: str
    description: str
    immediate_effect: Callable[["Company"], str]
    future_flag_setter: Optional[Callable[["Company"], None]] = None
    # 即時利益/コストのヒント（プレイヤー向け）
    profit_hint: str = ""
    risk_hint: str = ""


@dataclass
class GameEvent:
    id: str
    title: str
    description: str
    choices: List[Choice]
    # このイベントが発生する条件
    trigger_condition: Optional[Callable[["Company"], bool]] = None
    # N期の最小値（例：N_MINUS_2 以降のみ）
    min_n_period: int = -3
    max_n_period: int = 0
    # 1回限りか繰り返し発生するか
    one_shot: bool = True
    fired: bool = False
    # one_shot=False のとき：同じ N-period には1回だけ発火（-99=未発火）
    last_fired_n_period: int = field(default=-99)

    def can_fire(self, company: "Company", n_period: int) -> bool:
        if self.one_shot and self.fired:
            return False
        # 繰り返しイベント：同じ期（N-3 / N-2 / N-1 / N）には1回まで
        if not self.one_shot and n_period == self.last_fired_n_period:
            return False
        if self.trigger_condition and not self.trigger_condition(company):
            return False
        if n_period < self.min_n_period or n_period > self.max_n_period:
            return False
        return True
