from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestMetrics:
    final_equity: float
    total_return: float
    cagr: float
    sharpe: float
    max_drawdown: float
    trade_count: int


@dataclass(frozen=True)
class BacktestArtifacts:
    equity_curve_path: str
    drawdown_path: str
    trade_blotter_path: str | None = None
    signal_context_path: str | None = None


@dataclass(frozen=True)
class BacktestRun:
    run_id: str
    strategy_name: str
    strategy_version_id: str
    world_manifest_id: str
    metrics: BacktestMetrics
    artifacts: BacktestArtifacts
