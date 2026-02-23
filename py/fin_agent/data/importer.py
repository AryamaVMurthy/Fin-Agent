from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from fin_agent.storage import duckdb_store, sqlite_store
from fin_agent.storage.paths import RuntimePaths

REQUIRED_COLUMNS = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]
FUNDAMENTALS_COLUMNS = ["symbol", "published_at"]
CORPORATE_ACTION_COLUMNS = ["symbol", "effective_at", "action_type"]
RATINGS_COLUMNS = ["symbol", "revised_at", "agency", "rating"]


@dataclass(frozen=True)
class ImportResult:
    source_path: str
    rows_inserted: int
    dataset_hash: str


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_csv_columns(path: Path) -> None:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        present = reader.fieldnames or []
    missing = [column for column in REQUIRED_COLUMNS if column not in present]
    if missing:
        raise ValueError(f"missing required columns: {missing}")


def _validate_relational_columns(path: Path, relation_sql: str) -> None:
    with duckdb.connect() as conn:
        columns = [row[0] for row in conn.execute(f"SELECT * FROM {relation_sql} LIMIT 0").description]
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")


def _relation_for_file(path: Path) -> str:
    if path.suffix.lower() == ".csv":
        return f"read_csv_auto('{path.as_posix()}', header=true)"
    return f"read_parquet('{path.as_posix()}')"


def _validate_columns_for_relation(relation_sql: str, required_columns: list[str]) -> None:
    with duckdb.connect() as conn:
        columns = [row[0] for row in conn.execute(f"SELECT * FROM {relation_sql} LIMIT 0").description]
    missing = [column for column in required_columns if column not in columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")


def _ensure_supported_input(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"input file not found: {path}")
    if path.suffix.lower() not in {".csv", ".parquet"}:
        raise ValueError("only .csv and .parquet are supported in Stage 1")


def _ensure_required_timestamp_values(relation_sql: str, timestamp_column: str) -> None:
    with duckdb.connect() as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM {relation_sql}
            WHERE {timestamp_column} IS NULL OR TRIM(CAST({timestamp_column} AS VARCHAR)) = ''
            """
        ).fetchone()
    missing_count = int(row[0]) if row is not None else 0
    if missing_count > 0:
        raise ValueError(
            f"{timestamp_column} is required for all rows; found {missing_count} rows missing {timestamp_column}"
        )


def import_ohlcv_file(path: Path, runtime_paths: RuntimePaths) -> ImportResult:
    path = path.resolve()
    _ensure_supported_input(path)

    dataset_hash = _hash_file(path)
    duckdb_store.init_db(runtime_paths)
    sqlite_store.init_db(runtime_paths)

    if path.suffix.lower() == ".csv":
        _validate_csv_columns(path)
        relation = f"read_csv_auto('{path.as_posix()}', header=true)"
    else:
        relation = f"read_parquet('{path.as_posix()}')"
        _validate_relational_columns(path, relation)

    now = datetime.now(timezone.utc).isoformat()
    with duckdb.connect(str(runtime_paths.duckdb_path)) as conn:
        before = conn.execute("SELECT COUNT(*) FROM market_ohlcv").fetchone()[0]
        conn.execute(
            f"""
            INSERT INTO market_ohlcv (timestamp, published_at, symbol, open, high, low, close, volume, source_file, dataset_hash, ingested_at)
            SELECT
                CAST(timestamp AS TIMESTAMP),
                CAST(timestamp AS TIMESTAMP),
                CAST(symbol AS VARCHAR),
                CAST(open AS DOUBLE),
                CAST(high AS DOUBLE),
                CAST(low AS DOUBLE),
                CAST(close AS DOUBLE),
                CAST(volume AS DOUBLE),
                ?,
                ?,
                CAST(? AS TIMESTAMP)
            FROM {relation}
            """,
            [str(path), dataset_hash, now],
        )
        after = conn.execute("SELECT COUNT(*) FROM market_ohlcv").fetchone()[0]

    rows_inserted = int(after - before)
    if rows_inserted <= 0:
        raise ValueError(f"no rows inserted from {path}")

    sqlite_store.append_audit_event(
        runtime_paths,
        "data.import",
        {
            "source_path": str(path),
            "rows_inserted": rows_inserted,
            "dataset_hash": dataset_hash,
        },
    )
    return ImportResult(source_path=str(path), rows_inserted=rows_inserted, dataset_hash=dataset_hash)


def import_fundamentals_file(path: Path, runtime_paths: RuntimePaths) -> ImportResult:
    path = path.resolve()
    _ensure_supported_input(path)
    dataset_hash = _hash_file(path)
    relation = _relation_for_file(path)
    _validate_columns_for_relation(relation, FUNDAMENTALS_COLUMNS)
    _ensure_required_timestamp_values(relation, "published_at")
    now = datetime.now(timezone.utc).isoformat()

    duckdb_store.init_db(runtime_paths)
    sqlite_store.init_db(runtime_paths)
    with duckdb.connect(str(runtime_paths.duckdb_path)) as conn:
        before = conn.execute("SELECT COUNT(*) FROM company_fundamentals").fetchone()[0]
        conn.execute(
            f"""
            INSERT INTO company_fundamentals
              (symbol, published_at, pe_ratio, eps, payload_json, source_file, dataset_hash, ingested_at)
            SELECT
              CAST(symbol AS VARCHAR),
              CAST(published_at AS TIMESTAMP),
              TRY_CAST(pe_ratio AS DOUBLE),
              TRY_CAST(eps AS DOUBLE),
              CAST('{{}}' AS VARCHAR),
              ?,
              ?,
              CAST(? AS TIMESTAMP)
            FROM {relation}
            """,
            [str(path), dataset_hash, now],
        )
        after = conn.execute("SELECT COUNT(*) FROM company_fundamentals").fetchone()[0]

    rows_inserted = int(after - before)
    if rows_inserted <= 0:
        raise ValueError(f"no rows inserted from {path}")
    sqlite_store.append_audit_event(
        runtime_paths,
        "data.import.fundamentals",
        {
            "source_path": str(path),
            "rows_inserted": rows_inserted,
            "dataset_hash": dataset_hash,
        },
    )
    return ImportResult(source_path=str(path), rows_inserted=rows_inserted, dataset_hash=dataset_hash)


def import_corporate_actions_file(path: Path, runtime_paths: RuntimePaths) -> ImportResult:
    path = path.resolve()
    _ensure_supported_input(path)
    dataset_hash = _hash_file(path)
    relation = _relation_for_file(path)
    _validate_columns_for_relation(relation, CORPORATE_ACTION_COLUMNS)
    _ensure_required_timestamp_values(relation, "effective_at")
    now = datetime.now(timezone.utc).isoformat()

    duckdb_store.init_db(runtime_paths)
    sqlite_store.init_db(runtime_paths)
    with duckdb.connect(str(runtime_paths.duckdb_path)) as conn:
        before = conn.execute("SELECT COUNT(*) FROM corporate_actions").fetchone()[0]
        conn.execute(
            f"""
            INSERT INTO corporate_actions
              (symbol, effective_at, action_type, action_value, payload_json, source_file, dataset_hash, ingested_at)
            SELECT
              CAST(symbol AS VARCHAR),
              CAST(effective_at AS TIMESTAMP),
              CAST(action_type AS VARCHAR),
              TRY_CAST(action_value AS DOUBLE),
              CAST('{{}}' AS VARCHAR),
              ?,
              ?,
              CAST(? AS TIMESTAMP)
            FROM {relation}
            """,
            [str(path), dataset_hash, now],
        )
        after = conn.execute("SELECT COUNT(*) FROM corporate_actions").fetchone()[0]

    rows_inserted = int(after - before)
    if rows_inserted <= 0:
        raise ValueError(f"no rows inserted from {path}")
    sqlite_store.append_audit_event(
        runtime_paths,
        "data.import.corporate_actions",
        {
            "source_path": str(path),
            "rows_inserted": rows_inserted,
            "dataset_hash": dataset_hash,
        },
    )
    return ImportResult(source_path=str(path), rows_inserted=rows_inserted, dataset_hash=dataset_hash)


def import_ratings_file(path: Path, runtime_paths: RuntimePaths) -> ImportResult:
    path = path.resolve()
    _ensure_supported_input(path)
    dataset_hash = _hash_file(path)
    relation = _relation_for_file(path)
    _validate_columns_for_relation(relation, RATINGS_COLUMNS)
    _ensure_required_timestamp_values(relation, "revised_at")
    now = datetime.now(timezone.utc).isoformat()

    duckdb_store.init_db(runtime_paths)
    sqlite_store.init_db(runtime_paths)
    with duckdb.connect(str(runtime_paths.duckdb_path)) as conn:
        before = conn.execute("SELECT COUNT(*) FROM analyst_ratings").fetchone()[0]
        conn.execute(
            f"""
            INSERT INTO analyst_ratings
              (symbol, revised_at, agency, rating, payload_json, source_file, dataset_hash, ingested_at)
            SELECT
              CAST(symbol AS VARCHAR),
              CAST(revised_at AS TIMESTAMP),
              CAST(agency AS VARCHAR),
              CAST(rating AS VARCHAR),
              CAST('{{}}' AS VARCHAR),
              ?,
              ?,
              CAST(? AS TIMESTAMP)
            FROM {relation}
            """,
            [str(path), dataset_hash, now],
        )
        after = conn.execute("SELECT COUNT(*) FROM analyst_ratings").fetchone()[0]

    rows_inserted = int(after - before)
    if rows_inserted <= 0:
        raise ValueError(f"no rows inserted from {path}")
    sqlite_store.append_audit_event(
        runtime_paths,
        "data.import.ratings",
        {
            "source_path": str(path),
            "rows_inserted": rows_inserted,
            "dataset_hash": dataset_hash,
        },
    )
    return ImportResult(source_path=str(path), rows_inserted=rows_inserted, dataset_hash=dataset_hash)


def query_fundamentals_as_of(runtime_paths: RuntimePaths, symbol: str, as_of: str) -> dict[str, str | float]:
    if not symbol.strip():
        raise ValueError("symbol is required")
    if not as_of.strip():
        raise ValueError("as_of is required")
    duckdb_store.init_db(runtime_paths)
    with duckdb.connect(str(runtime_paths.duckdb_path)) as conn:
        row = conn.execute(
            """
            SELECT symbol, published_at, pe_ratio, eps, payload_json
            FROM company_fundamentals
            WHERE symbol = ?
              AND published_at <= CAST(? AS TIMESTAMP)
            ORDER BY published_at DESC
            LIMIT 1
            """,
            [symbol, as_of],
        ).fetchone()
    if row is None:
        raise ValueError(f"no fundamentals row found for symbol={symbol} as_of={as_of}")
    return {
        "symbol": str(row[0]),
        "published_at": str(row[1]),
        "pe_ratio": float(row[2]) if row[2] is not None else float("nan"),
        "eps": float(row[3]) if row[3] is not None else float("nan"),
        "payload": json.loads(str(row[4])) if row[4] is not None else {},
    }
