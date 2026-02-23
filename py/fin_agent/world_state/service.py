from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

import duckdb

from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


@dataclass(frozen=True)
class WorldStateManifest:
    manifest_id: str
    universe: list[str]
    start_date: str
    end_date: str
    data_hash: str
    row_count: int
    fundamentals_row_count: int = 0
    corporate_actions_row_count: int = 0
    ratings_row_count: int = 0
    adjustment_policy: str = "none"


@dataclass(frozen=True)
class DataCompletenessReport:
    universe: list[str]
    start_date: str
    end_date: str
    strict_mode: bool
    total_symbols: int
    covered_symbols: int
    skipped_instruments: list[dict[str, str]]
    skipped_features: list[dict[str, str]]
    fallback_reason: str | None


@dataclass(frozen=True)
class PITValidationReport:
    universe: list[str]
    start_date: str
    end_date: str
    strict_mode: bool
    valid: bool
    errors: list[str]
    remediation: list[str]
    leak_rows: int


def build_world_state_manifest(
    runtime_paths: RuntimePaths,
    universe: list[str],
    start_date: str,
    end_date: str,
    adjustment_policy: str = "none",
) -> WorldStateManifest:
    if not universe:
        raise ValueError("universe must not be empty")
    policy = adjustment_policy.strip().lower()
    if policy not in {"none", "split_adjusted", "total_return"}:
        raise ValueError(
            f"unsupported adjustment_policy={adjustment_policy}; expected one of: none, split_adjusted, total_return"
        )

    placeholders = ",".join(["?"] * len(universe))
    sql = f"""
        SELECT symbol, timestamp, published_at, open, high, low, close, volume, dataset_hash
        FROM market_ohlcv
        WHERE symbol IN ({placeholders})
          AND CAST(timestamp AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
        ORDER BY symbol, timestamp
    """

    fundamentals_sql = f"""
        SELECT COUNT(*) AS c
        FROM company_fundamentals
        WHERE symbol IN ({placeholders})
          AND published_at <= CAST(? AS TIMESTAMP)
    """
    actions_sql = f"""
        SELECT COUNT(*) AS c
        FROM corporate_actions
        WHERE symbol IN ({placeholders})
          AND CAST(effective_at AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
    """
    ratings_sql = f"""
        SELECT COUNT(*) AS c
        FROM analyst_ratings
        WHERE symbol IN ({placeholders})
          AND revised_at <= CAST(? AS TIMESTAMP)
    """

    with duckdb.connect(str(runtime_paths.duckdb_path)) as conn:
        rows = conn.execute(sql, [*universe, start_date, end_date]).fetchall()
        fundamentals_count = int(conn.execute(fundamentals_sql, [*universe, f"{end_date}T23:59:59"]).fetchone()[0])
        actions_count = int(conn.execute(actions_sql, [*universe, start_date, end_date]).fetchone()[0])
        ratings_count = int(conn.execute(ratings_sql, [*universe, f"{end_date}T23:59:59"]).fetchone()[0])

    if not rows:
        raise ValueError("no market rows available for requested universe/date range")

    by_symbol = {symbol: 0 for symbol in universe}
    hasher = hashlib.sha256()
    for row in rows:
        by_symbol[str(row[0])] += 1
        serialized = "|".join(str(item) for item in row)
        hasher.update(serialized.encode("utf-8"))

    hasher.update(f"adjustment_policy={policy}".encode("utf-8"))
    hasher.update(f"fundamentals_count={fundamentals_count}".encode("utf-8"))
    hasher.update(f"actions_count={actions_count}".encode("utf-8"))
    hasher.update(f"ratings_count={ratings_count}".encode("utf-8"))

    missing_symbols = [symbol for symbol, count in by_symbol.items() if count == 0]
    if missing_symbols:
        raise ValueError(f"critical PIT data missing for symbols: {missing_symbols}")

    manifest = WorldStateManifest(
        manifest_id=str(uuid.uuid4()),
        universe=universe,
        start_date=start_date,
        end_date=end_date,
        data_hash=hasher.hexdigest(),
        row_count=len(rows),
        fundamentals_row_count=fundamentals_count,
        corporate_actions_row_count=actions_count,
        ratings_row_count=ratings_count,
        adjustment_policy=policy,
    )
    sqlite_store.save_world_manifest(runtime_paths, manifest.__dict__)
    return manifest


def build_data_completeness_report(
    runtime_paths: RuntimePaths,
    universe: list[str],
    start_date: str,
    end_date: str,
    strict_mode: bool = False,
) -> DataCompletenessReport:
    if not universe:
        raise ValueError("universe must not be empty")
    placeholders = ",".join(["?"] * len(universe))
    ohlcv_sql = f"""
        SELECT symbol, COUNT(*) AS c
        FROM market_ohlcv
        WHERE symbol IN ({placeholders})
          AND CAST(timestamp AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
        GROUP BY symbol
    """
    technical_sql = f"""
        SELECT symbol, COUNT(*) AS c
        FROM market_technicals
        WHERE symbol IN ({placeholders})
          AND CAST(timestamp AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
        GROUP BY symbol
    """

    with duckdb.connect(str(runtime_paths.duckdb_path)) as conn:
        ohlcv_rows = conn.execute(ohlcv_sql, [*universe, start_date, end_date]).fetchall()
        technical_rows = conn.execute(technical_sql, [*universe, start_date, end_date]).fetchall()

    ohlcv_counts = {str(symbol): int(count) for symbol, count in ohlcv_rows}
    technical_counts = {str(symbol): int(count) for symbol, count in technical_rows}

    skipped_instruments: list[dict[str, str]] = []
    skipped_features: list[dict[str, str]] = []
    for symbol in universe:
        if ohlcv_counts.get(symbol, 0) <= 0:
            skipped_instruments.append(
                {
                    "symbol": symbol,
                    "fallback_reason": "missing_ohlcv_rows",
                }
            )
            continue
        if technical_counts.get(symbol, 0) <= 0:
            skipped_features.append(
                {
                    "symbol": symbol,
                    "feature": "sma_short,sma_long",
                    "fallback_reason": "missing_technical_rows",
                }
            )

    fallback_reason: str | None = None
    if skipped_instruments:
        fallback_reason = "critical_missing_ohlcv_rows"
    elif skipped_features:
        fallback_reason = "technical_features_missing"

    if strict_mode and skipped_instruments:
        raise ValueError(
            "strict completeness check failed: missing critical PIT dependencies (OHLCV rows). "
            "Remediation: import required OHLCV data for all requested symbols/date range."
        )

    covered_symbols = len(universe) - len(skipped_instruments)
    return DataCompletenessReport(
        universe=universe,
        start_date=start_date,
        end_date=end_date,
        strict_mode=strict_mode,
        total_symbols=len(universe),
        covered_symbols=covered_symbols,
        skipped_instruments=skipped_instruments,
        skipped_features=skipped_features,
        fallback_reason=fallback_reason,
    )


def validate_world_state_pit(
    runtime_paths: RuntimePaths,
    universe: list[str],
    start_date: str,
    end_date: str,
    strict_mode: bool = True,
) -> PITValidationReport:
    if not universe:
        raise ValueError("universe must not be empty")

    placeholders = ",".join(["?"] * len(universe))
    sql = f"""
        SELECT symbol, timestamp, published_at
        FROM market_ohlcv
        WHERE symbol IN ({placeholders})
          AND CAST(timestamp AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
    """
    with duckdb.connect(str(runtime_paths.duckdb_path)) as conn:
        rows = conn.execute(sql, [*universe, start_date, end_date]).fetchall()

    errors: list[str] = []
    remediation: list[str] = []
    if not rows:
        errors.append("no market_ohlcv rows available for universe/date range")
        remediation.append("import OHLCV data for requested universe/date range")

    by_symbol = {symbol: 0 for symbol in universe}
    leak_rows = 0
    missing_published_at_rows = 0
    for symbol, timestamp, published_at in rows:
        symbol_key = str(symbol)
        if symbol_key in by_symbol:
            by_symbol[symbol_key] += 1
        if timestamp is None or published_at is None:
            missing_published_at_rows += 1
            continue
        if published_at > timestamp:
            leak_rows += 1

    missing_symbols = [symbol for symbol, count in by_symbol.items() if count == 0]
    if missing_symbols:
        errors.append(f"missing rows for symbols: {missing_symbols}")
        remediation.append("import OHLCV rows for all requested symbols")

    if missing_published_at_rows > 0:
        errors.append(f"rows missing critical published_at/timestamp fields: {missing_published_at_rows}")
        remediation.append("backfill market_ohlcv.published_at for all rows (published_at = timestamp)")

    if leak_rows > 0:
        errors.append(f"future publication leaks detected: {leak_rows} rows where published_at > timestamp")
        remediation.append(
            "fix source publication timestamps and re-import; published_at must be <= timestamp for PIT safety"
        )

    valid = len(errors) == 0
    if strict_mode and not valid:
        raise ValueError(
            "PIT validation failed in strict mode: "
            + "; ".join(errors)
            + ". Remediation: "
            + " | ".join(remediation)
        )

    return PITValidationReport(
        universe=universe,
        start_date=start_date,
        end_date=end_date,
        strict_mode=strict_mode,
        valid=valid,
        errors=errors,
        remediation=remediation,
        leak_rows=leak_rows,
    )
