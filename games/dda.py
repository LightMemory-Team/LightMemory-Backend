"""
共用 DDA（動態難度調整 / Dynamic Difficulty Adjustment）引擎。

提供統一的難度升階骨架、狀態轉換與策略介面，
供各遊戲（如 market_route, market_shopping, fridge_check 等）共用。
"""

from dataclasses import dataclass
from typing import Callable, Optional, Protocol


@dataclass(frozen=True)
class DDAConfig:
    """一款遊戲的難度設定：有哪些階段、連對幾題升階。"""

    stage_order: list[str]
    promote_streak: int = 3


class DDAStrategy(Protocol):
    """處理「升階以外」的欄位調整。沒有額外欄位就使用 NoOpStrategy。"""

    def on_correct(
        self, state: dict, config: DDAConfig, *, is_fast: bool = False
    ) -> dict: ...

    def on_wrong(self, state: dict, config: DDAConfig) -> dict: ...

    def on_promote(
        self, state: dict, config: DDAConfig, new_stage: str
    ) -> dict: ...


class NoOpStrategy:
    """適用於只升階、無額外欄位調整的遊戲（如 fridge_check, market_shopping）。"""

    def on_correct(
        self, state: dict, config: DDAConfig, *, is_fast: bool = False
    ) -> dict:
        return {}

    def on_wrong(self, state: dict, config: DDAConfig) -> dict:
        return {}

    def on_promote(
        self, state: dict, config: DDAConfig, new_stage: str
    ) -> dict:
        return {}


def apply_answer(
    state: dict,
    config: DDAConfig,
    strategy: DDAStrategy,
    *,
    is_correct: bool,
    is_fast: bool = False,
    extra_promote_check: Optional[Callable[[dict, bool], bool]] = None,
) -> tuple[dict, str]:
    """
    DDA 引擎核心函式：處理連對計數 + 升階判斷，其餘客製欄位由 strategy 處理。

    參數：
        state: 當前 session state 字典
        config: DDAConfig 設定（階段清單與升階門檻）
        strategy: DDAStrategy 策略物件
        is_correct: 該次作答是否正確
        is_fast: 是否屬於快速作答（預設 False）
        extra_promote_check: 額外的升階判定函式 (state, is_fast) -> bool

    回傳：
        (updated_fields_dict, action)
        action 為 "promoted" 或 "no_promotion"。
    """
    # 支援 current_stage 與 difficulty 相容讀取
    stage = state.get("current_stage", state.get("difficulty"))
    if stage is None and config.stage_order:
        stage = config.stage_order[0]

    # 支援 correct_streak 與 consecutive_correct 相容讀取
    correct_streak = state.get(
        "correct_streak", state.get("consecutive_correct", 0)
    )

    if not is_correct:
        updated = {
            "current_stage": stage,
            "correct_streak": 0,
            # 同步支援舊欄位名稱以保證相容
            "difficulty": stage,
            "consecutive_correct": 0,
        }
        updated.update(strategy.on_wrong(state, config))
        return updated, "no_promotion"

    correct_streak += 1
    should_promote = correct_streak >= config.promote_streak
    if not should_promote and extra_promote_check is not None:
        should_promote = extra_promote_check(state, is_fast)

    stage_index = (
        config.stage_order.index(stage) if stage in config.stage_order else 0
    )
    if should_promote and stage_index < len(config.stage_order) - 1:
        new_stage = config.stage_order[stage_index + 1]
        updated = {
            "current_stage": new_stage,
            "correct_streak": 0,
            "difficulty": new_stage,
            "consecutive_correct": 0,
        }
        updated.update(strategy.on_promote(state, config, new_stage))
        return updated, "promoted"

    updated = {
        "current_stage": stage,
        "correct_streak": correct_streak,
        "difficulty": stage,
        "consecutive_correct": correct_streak,
    }
    updated.update(strategy.on_correct(state, config, is_fast=is_fast))
    return updated, "no_promotion"


# 三階段計分權重（統一常數）
DEFAULT_STAGE_MULTIPLIER = {
    "basic": 1.0,
    "intermediate": 1.3,
    "advanced": 1.6,
    "easy": 1.0,
    "medium": 1.3,
    "hard": 1.6,
}
