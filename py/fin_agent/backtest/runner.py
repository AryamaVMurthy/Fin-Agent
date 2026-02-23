from __future__ import annotations

import math
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from fin_agent.backtest.models import BacktestArtifacts, BacktestMetrics, BacktestRun
from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths
from fin_agent.strategy.models import StrategySpec
from fin_agent.viz.svg import write_line_chart_svg
from fin_agent.world_state.service import WorldStateManifest


def _moving_average(values: list[float], window: int) -> list[float]:
    result: list[float] = []
    for idx in range(len(values)):
        if idx + 1 < window:
            result.append(float("nan"))
            continue
        segment = values[idx + 1 - window : idx + 1]
        result.append(sum(segment) / float(window))
    return result


def _compute_metrics(equity_by_day: list[float], trade_count: int) -> BacktestMetrics:
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


def _to_date_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def run_backtest(paths: RuntimePaths, strategy: StrategySpec, manifest: WorldStateManifest) -> BacktestRun:
    sqlite_store.init_db(paths)
    if strategy.signal_type != "sma_crossover":
        raise ValueError(f"unsupported signal_type: {strategy.signal_type}")
    if strategy.short_window >= strategy.long_window:
        raise ValueError("short_window must be less than long_window")

    if len(strategy.universe) > strategy.max_positions:
        raise ValueError("universe size exceeds max_positions")

    placeholders = ",".join(["?"] * len(strategy.universe))
    sql = f"""
        SELECT symbol, timestamp, close
        FROM market_ohlcv
        WHERE symbol IN ({placeholders})
          AND CAST(timestamp AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
        ORDER BY symbol, timestamp
    """
    with duckdb.connect(str(paths.duckdb_path)) as conn:
        rows = conn.execute(sql, [*strategy.universe, strategy.start_date, strategy.end_date]).fetchall()

    if not rows:
        raise ValueError("no OHLCV rows found for strategy range")

    by_symbol: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for symbol, timestamp, close in rows:
        by_symbol[str(symbol)].append((timestamp, float(close)))

    missing = [symbol for symbol in strategy.universe if symbol not in by_symbol]
    if missing:
        raise ValueError(f"missing OHLCV rows for symbols: {missing}")

    cash_per_symbol = strategy.initial_capital / float(len(strategy.universe))
    trade_count = 0
    equity_by_date: dict[str, float] = defaultdict(float)
    trade_rows: list[dict[str, str | float]] = []
    signal_rows: list[dict[str, str | float]] = []

    for symbol in strategy.universe:
        points = by_symbol[symbol]
        closes = [close for _, close in points]
        short_ma = _moving_average(closes, strategy.short_window)
        long_ma = _moving_average(closes, strategy.long_window)

        cash = cash_per_symbol
        shares = 0.0
        prev_signal = False
        open_trade: dict[str, str | float] | None = None

        for idx, (ts, close) in enumerate(points):
            can_signal = not math.isnan(short_ma[idx]) and not math.isnan(long_ma[idx])
            buy_signal = can_signal and short_ma[idx] > long_ma[idx]
            reason_code = "insufficient_history"
            if can_signal:
                if buy_signal and not prev_signal:
                    reason_code = "sma_cross_up"
                elif (not buy_signal) and prev_signal:
                    reason_code = "sma_cross_down"
                elif buy_signal:
                    reason_code = "trend_above"
                else:
                    reason_code = "trend_below"

            signal_rows.append(
                {
                    "symbol": symbol,
                    "timestamp": _to_date_key(ts),
                    "close": close,
                    "sma_short": short_ma[idx],
                    "sma_long": long_ma[idx],
                    "buy_signal": 1.0 if buy_signal else 0.0,
                    "reason_code": reason_code,
                }
            )

            if buy_signal and not prev_signal and shares == 0.0:
                gross = cash
                fee = gross * (strategy.cost_bps / 10000.0)
                net = gross - fee
                if net <= 0:
                    raise ValueError("net capital after fees is non-positive")
                shares = net / close
                cash = 0.0
                trade_count += 1
                open_trade = {
                    "symbol": symbol,
                    "entry_ts": _to_date_key(ts),
                    "entry_price": close,
                    "entry_reason": "sma_cross_up",
                }

            if (not buy_signal) and prev_signal and shares > 0.0:
                gross = shares * close
                fee = gross * (strategy.cost_bps / 10000.0)
                cash = gross - fee
                shares = 0.0
                trade_count += 1
                if open_trade is not None:
                    entry_price = float(open_trade["entry_price"])
                    pnl = cash - cash_per_symbol
                    trade_rows.append(
                        {
                            "symbol": symbol,
                            "entry_ts": str(open_trade["entry_ts"]),
                            "exit_ts": _to_date_key(ts),
                            "entry_price": entry_price,
                            "exit_price": close,
                            "pnl": pnl,
                            "entry_reason": str(open_trade["entry_reason"]),
                            "exit_reason": "sma_cross_down",
                        }
                    )
                    open_trade = None

            prev_signal = buy_signal
            equity = cash + (shares * close)
            equity_by_date[_to_date_key(ts)] += equity

        if shares > 0.0:
            close = points[-1][1]
            gross = shares * close
            fee = gross * (strategy.cost_bps / 10000.0)
            cash = gross - fee
            shares = 0.0
            trade_count += 1
            equity_by_date[_to_date_key(points[-1][0])] += cash
            if open_trade is not None:
                entry_price = float(open_trade["entry_price"])
                pnl = cash - cash_per_symbol
                trade_rows.append(
                    {
                        "symbol": symbol,
                        "entry_ts": str(open_trade["entry_ts"]),
                        "exit_ts": _to_date_key(points[-1][0]),
                        "entry_price": entry_price,
                        "exit_price": close,
                        "pnl": pnl,
                        "entry_reason": str(open_trade["entry_reason"]),
                        "exit_reason": "end_of_window",
                    }
                )
                open_trade = None

    ordered_dates = sorted(equity_by_date.keys())
    equity_series = [equity_by_date[day] for day in ordered_dates]
    metrics = _compute_metrics(equity_series, trade_count=trade_count)

    drawdowns = []
    peak = equity_series[0]
    for value in equity_series:
        peak = max(peak, value)
        drawdowns.append((value / peak) - 1.0)

    run_dir = paths.artifacts_dir / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    temp_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    equity_path = run_dir / f"equity-{temp_id}.svg"
    drawdown_path = run_dir / f"drawdown-{temp_id}.svg"
    trade_path = run_dir / f"trades-{temp_id}.csv"
    signal_path = run_dir / f"signals-{temp_id}.csv"

    write_line_chart_svg(equity_path, f"Equity Curve - {strategy.strategy_name}", ordered_dates, equity_series)
    write_line_chart_svg(drawdown_path, f"Drawdown - {strategy.strategy_name}", ordered_dates, drawdowns)
    with trade_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["symbol", "entry_ts", "exit_ts", "entry_price", "exit_price", "pnl", "entry_reason", "exit_reason"],
        )
        writer.writeheader()
        for row in trade_rows:
            writer.writerow(row)
    with signal_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["symbol", "timestamp", "close", "sma_short", "sma_long", "buy_signal", "reason_code"],
        )
        writer.writeheader()
        for row in signal_rows:
            writer.writerow(row)

    strategy_version_ref = sqlite_store.save_strategy_version(paths, strategy.strategy_name, strategy.model_dump())
    run_id = sqlite_store.save_backtest_run(
        paths,
        strategy_version_id=strategy_version_ref.version_id,
        world_manifest_id=manifest.manifest_id,
        metrics=metrics.__dict__,
        artifacts={
            "equity_curve_path": str(equity_path),
            "drawdown_path": str(drawdown_path),
            "trade_blotter_path": str(trade_path),
            "signal_context_path": str(signal_path),
        },
        payload={
            "strategy": strategy.model_dump(),
            "manifest": manifest.__dict__,
        },
    )

    sqlite_store.append_audit_event(
        paths,
        "backtest.run",
        {
            "run_id": run_id,
            "strategy_version_id": strategy_version_ref.version_id,
            "world_manifest_id": manifest.manifest_id,
            "metrics": metrics.__dict__,
        },
    )

    return BacktestRun(
        run_id=run_id,
        strategy_name=strategy.strategy_name,
        strategy_version_id=strategy_version_ref.version_id,
        world_manifest_id=manifest.manifest_id,
        metrics=metrics,
        artifacts=BacktestArtifacts(
            equity_curve_path=str(equity_path),
            drawdown_path=str(drawdown_path),
            trade_blotter_path=str(trade_path),
            signal_context_path=str(signal_path),
        ),
    )
