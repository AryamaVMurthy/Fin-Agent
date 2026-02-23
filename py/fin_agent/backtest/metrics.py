from __future__ import annotations

import math

from fin_agent.backtest.models import BacktestMetrics


def compute_backtest_metrics(equity_by_day: list[float], trade_count: int) -> BacktestMetrics:
    if len(equity_by_day) < 2:
        raise ValueError("need at least 2 points to compute metrics")

    returns = []
    for idx in range(1, len(equity_by_day)):
        prev = equity_by_day[idx - 1]
        curr = equity_by_day[idx]
        if prev <= 0:
            raise ValueError("equity became non-positive; metrics invalid")
        returns.append((curr - prev) / prev)

    initial = equity_by_day[0]
    final = equity_by_day[-1]
    total_return = (final / initial) - 1.0
    years = max((len(equity_by_day) - 1) / 252.0, 1.0 / 252.0)
    cagr = (final / initial) ** (1.0 / years) - 1.0

    mean_ret = sum(returns) / len(returns)
    variance = sum((value - mean_ret) ** 2 for value in returns) / len(returns)
    std_dev = math.sqrt(variance)
    sharpe = 0.0 if std_dev == 0 else (mean_ret / std_dev) * math.sqrt(252.0)

    peak = equity_by_day[0]
    max_drawdown = 0.0
    for value in equity_by_day:
        peak = max(peak, value)
        drawdown = (value / peak) - 1.0
        max_drawdown = min(max_drawdown, drawdown)

    return BacktestMetrics(
        final_equity=final,
        total_return=total_return,
        cagr=cagr,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        trade_count=trade_count,
    )
