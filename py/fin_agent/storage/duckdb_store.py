from __future__ import annotations

import duckdb

from fin_agent.storage.paths import RuntimePaths


def _connect(paths: RuntimePaths) -> duckdb.DuckDBPyConnection:
    paths.ensure()
    return duckdb.connect(str(paths.duckdb_path))


def init_db(paths: RuntimePaths) -> None:
    with _connect(paths) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_ohlcv (
                timestamp TIMESTAMP NOT NULL,
                published_at TIMESTAMP,
                symbol VARCHAR NOT NULL,
                open DOUBLE NOT NULL,
                high DOUBLE NOT NULL,
                low DOUBLE NOT NULL,
                close DOUBLE NOT NULL,
                volume DOUBLE NOT NULL,
                source_file VARCHAR NOT NULL,
                dataset_hash VARCHAR NOT NULL,
                ingested_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.execute("ALTER TABLE market_ohlcv ADD COLUMN IF NOT EXISTS published_at TIMESTAMP")
        conn.execute("UPDATE market_ohlcv SET published_at = timestamp WHERE published_at IS NULL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_technicals (
                timestamp TIMESTAMP NOT NULL,
                symbol VARCHAR NOT NULL,
                sma_short DOUBLE,
                sma_long DOUBLE,
                source VARCHAR NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_instruments (
                instrument_token VARCHAR NOT NULL,
                exchange VARCHAR,
                segment VARCHAR,
                tradingsymbol VARCHAR NOT NULL,
                name VARCHAR,
                lot_size DOUBLE,
                tick_size DOUBLE,
                expiry VARCHAR,
                strike DOUBLE,
                instrument_type VARCHAR,
                source VARCHAR NOT NULL,
                dataset_hash VARCHAR NOT NULL,
                fetched_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_quotes (
                quote_key VARCHAR NOT NULL,
                instrument_token VARCHAR,
                last_price DOUBLE,
                payload_json VARCHAR NOT NULL,
                source VARCHAR NOT NULL,
                fetched_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS company_fundamentals (
                symbol VARCHAR NOT NULL,
                published_at TIMESTAMP NOT NULL,
                pe_ratio DOUBLE,
                eps DOUBLE,
                payload_json VARCHAR NOT NULL,
                source_file VARCHAR NOT NULL,
                dataset_hash VARCHAR NOT NULL,
                ingested_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS corporate_actions (
                symbol VARCHAR NOT NULL,
                effective_at TIMESTAMP NOT NULL,
                action_type VARCHAR NOT NULL,
                action_value DOUBLE,
                payload_json VARCHAR NOT NULL,
                source_file VARCHAR NOT NULL,
                dataset_hash VARCHAR NOT NULL,
                ingested_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyst_ratings (
                symbol VARCHAR NOT NULL,
                revised_at TIMESTAMP NOT NULL,
                agency VARCHAR NOT NULL,
                rating VARCHAR NOT NULL,
                payload_json VARCHAR NOT NULL,
                source_file VARCHAR NOT NULL,
                dataset_hash VARCHAR NOT NULL,
                ingested_at TIMESTAMP NOT NULL
            )
            """
        )


def query_ohlcv_count(paths: RuntimePaths, symbol: str) -> int:
    with _connect(paths) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM market_ohlcv WHERE symbol = ?", (symbol,)
        ).fetchone()
    return int(row[0])
