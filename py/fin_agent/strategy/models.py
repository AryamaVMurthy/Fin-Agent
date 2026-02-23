from __future__ import annotations

from pydantic import BaseModel, Field


class IntentSnapshot(BaseModel):
    universe: list[str] = Field(min_length=1)
    start_date: str
    end_date: str
    initial_capital: float = Field(gt=0)
    short_window: int = Field(ge=1)
    long_window: int = Field(ge=2)
    max_positions: int = Field(ge=1)


class StrategySpec(BaseModel):
    strategy_id: str
    strategy_name: str
    universe: list[str]
    start_date: str
    end_date: str
    initial_capital: float
    signal_type: str
    short_window: int
    long_window: int
    max_positions: int
    cost_bps: float
