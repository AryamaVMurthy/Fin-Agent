from __future__ import annotations

import duckdb

from fin_agent.storage.paths import RuntimePaths


def resolve_universe(runtime_paths: RuntimePaths, requested_symbols: list[str]) -> list[str]:
    if not requested_symbols:
        raise ValueError("requested_symbols must not be empty")

    placeholders = ",".join(["?"] * len(requested_symbols))
    sql = f"SELECT DISTINCT symbol FROM market_ohlcv WHERE symbol IN ({placeholders}) ORDER BY symbol"

    with duckdb.connect(str(runtime_paths.duckdb_path)) as conn:
        rows = conn.execute(sql, requested_symbols).fetchall()

    found = [str(row[0]) for row in rows]
    missing = sorted(set(requested_symbols) - set(found))
    if missing:
        raise ValueError(f"symbols not found in local data: {missing}")
    return found
