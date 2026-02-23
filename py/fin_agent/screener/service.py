from __future__ import annotations

import duckdb

from fin_agent.screener.formula import FormulaValidation, validate_and_compile_formula
from fin_agent.storage.paths import RuntimePaths

ALLOWED_COLUMNS = [
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "sma_short",
    "sma_long",
    "sma_gap_pct",
    "day_range_pct",
    "return_1d_pct",
]


def validate_formula(formula: str) -> FormulaValidation:
    return validate_and_compile_formula(formula=formula, allowed_identifiers=ALLOWED_COLUMNS)


def run_formula_screen(
    runtime_paths: RuntimePaths,
    formula: str,
    as_of: str,
    universe: list[str],
    top_k: int,
    rank_by: str | None = None,
    sort_order: str = "desc",
) -> dict[str, object]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if not universe:
        raise ValueError("universe must not be empty")
    normalized_order = sort_order.strip().lower()
    if normalized_order not in {"asc", "desc"}:
        raise ValueError("sort_order must be one of: asc, desc")

    compiled = validate_formula(formula)
    rank_sql = "close"
    if rank_by is not None and rank_by.strip():
        rank_sql = validate_formula(rank_by).sql_expression
    placeholders = ",".join(["?"] * len(universe))
    sql = f"""
    WITH latest_price AS (
      SELECT
        symbol,
        timestamp,
        open,
        high,
        low,
        close,
        volume,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) AS rn
      FROM market_ohlcv
      WHERE symbol IN ({placeholders})
        AND CAST(timestamp AS DATE) <= CAST(? AS DATE)
    ),
    latest_tech AS (
      SELECT
        symbol,
        sma_short,
        sma_long,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) AS rn
      FROM market_technicals
      WHERE symbol IN ({placeholders})
        AND CAST(timestamp AS DATE) <= CAST(? AS DATE)
    ),
    previous_price AS (
      SELECT
        symbol,
        close AS prev_close,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) AS rn
      FROM market_ohlcv
      WHERE symbol IN ({placeholders})
        AND CAST(timestamp AS DATE) <= CAST(? AS DATE)
    ),
    base AS (
      SELECT
        p.symbol,
        p.timestamp,
        p.open,
        p.high,
        p.low,
        p.close,
        p.volume,
        t.sma_short,
        t.sma_long,
        prev.prev_close,
        CASE
          WHEN t.sma_long IS NULL OR t.sma_long = 0 THEN NULL
          ELSE ((t.sma_short - t.sma_long) / t.sma_long) * 100.0
        END AS sma_gap_pct,
        CASE
          WHEN p.close = 0 THEN NULL
          ELSE ((p.high - p.low) / p.close) * 100.0
        END AS day_range_pct,
        CASE
          WHEN prev.prev_close IS NULL OR prev.prev_close = 0 THEN NULL
          ELSE ((p.close - prev.prev_close) / prev.prev_close) * 100.0
        END AS return_1d_pct
      FROM latest_price p
      LEFT JOIN latest_tech t ON t.symbol = p.symbol AND t.rn = 1
      LEFT JOIN previous_price prev ON prev.symbol = p.symbol AND prev.rn = 2
      WHERE p.rn = 1
    )
    SELECT *
    FROM base
    WHERE {compiled.sql_expression}
    ORDER BY {rank_sql} {normalized_order.upper()}, close DESC, symbol ASC
    LIMIT ?
    """

    params: list[object] = [*universe, as_of, *universe, as_of, *universe, as_of, top_k]
    with duckdb.connect(str(runtime_paths.duckdb_path)) as conn:
        rows = conn.execute(sql, params).fetchall()
        columns = [row[0] for row in conn.description]

    payload_rows: list[dict[str, object]] = []
    for row in rows:
        payload_rows.append({columns[idx]: row[idx] for idx in range(len(columns))})

    return {
        "formula": formula,
        "sql_expression": compiled.sql_expression,
        "identifiers": compiled.identifiers,
        "as_of": as_of,
        "universe": universe,
        "rank_by": rank_by or "close",
        "sort_order": normalized_order,
        "rows": payload_rows,
        "count": len(payload_rows),
    }
