from __future__ import annotations

import uuid

from fin_agent.strategy.models import IntentSnapshot, StrategySpec


def build_strategy_from_intent(intent: IntentSnapshot, strategy_name: str) -> StrategySpec:
    if intent.short_window >= intent.long_window:
        raise ValueError("short_window must be less than long_window")
    if len(intent.universe) > intent.max_positions:
        raise ValueError("universe size exceeds max_positions; reduce universe or increase max_positions")

    return StrategySpec(
        strategy_id=str(uuid.uuid4()),
        strategy_name=strategy_name,
        universe=intent.universe,
        start_date=intent.start_date,
        end_date=intent.end_date,
        initial_capital=float(intent.initial_capital),
        signal_type="sma_crossover",
        short_window=int(intent.short_window),
        long_window=int(intent.long_window),
        max_positions=int(intent.max_positions),
        cost_bps=5.0,
    )
