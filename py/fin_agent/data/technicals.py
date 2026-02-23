from __future__ import annotations

import duckdb

from fin_agent.storage.paths import RuntimePaths


def compute_sma_features(
    runtime_paths: RuntimePaths,
    universe: list[str],
    start_date: str,
    end_date: str,
    short_window: int,
    long_window: int,
) -> int:
    if short_window < 1 or long_window < 2 or short_window >= long_window:
        raise ValueError("invalid windows: require 1 <= short_window < long_window")
    if not universe:
        raise ValueError("universe must not be empty")

    placeholders = ",".join(["?"] * len(universe))
    with duckdb.connect(str(runtime_paths.duckdb_path)) as conn:
        conn.execute("DELETE FROM market_technicals WHERE source = 'stage1_sma'")
        before = conn.execute("SELECT COUNT(*) FROM market_technicals").fetchone()[0]
        conn.execute(
            f"""
            INSERT INTO market_technicals (timestamp, symbol, sma_short, sma_long, source)
            SELECT
              timestamp,
              symbol,
              AVG(close) OVER (
                  PARTITION BY symbol
                  ORDER BY timestamp
                  ROWS BETWEEN {short_window - 1} PRECEDING AND CURRENT ROW
              ) AS sma_short,
              AVG(close) OVER (
                  PARTITION BY symbol
                  ORDER BY timestamp
                  ROWS BETWEEN {long_window - 1} PRECEDING AND CURRENT ROW
              ) AS sma_long,
              'stage1_sma'
            FROM market_ohlcv
            WHERE symbol IN ({placeholders})
              AND CAST(timestamp AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
            ORDER BY symbol, timestamp
            """,
            [*universe, start_date, end_date],
        )
        after = conn.execute("SELECT COUNT(*) FROM market_technicals").fetchone()[0]

    inserted = int(after - before)
    if inserted <= 0:
        raise ValueError("no technical rows generated")
    return inserted
