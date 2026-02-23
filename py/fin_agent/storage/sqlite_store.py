from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generator, Optional

from fin_agent.observability.context import get_trace_id
from fin_agent.security import decrypt_json, encrypt_json, encryption_enabled, redact_payload
from fin_agent.storage.paths import RuntimePaths


@dataclass(frozen=True)
class StrategyVersionRef:
    strategy_id: str
    version_id: str
    version_number: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(paths: RuntimePaths) -> Generator[sqlite3.Connection, None, None]:
    paths.ensure()
    conn = sqlite3.connect(paths.sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(paths: RuntimePaths) -> None:
    with connect(paths) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS intent_snapshots (
                id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategy_versions (
                id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(strategy_id, version_number)
            );

            CREATE TABLE IF NOT EXISTS world_manifests (
                id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS backtest_runs (
                id TEXT PRIMARY KEY,
                strategy_version_id TEXT NOT NULL,
                world_manifest_id TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                artifacts_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT,
                error_text TEXT,
                fallback_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                connector TEXT NOT NULL,
                created_at TEXT NOT NULL,
                consumed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS connector_sessions (
                connector TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS code_strategies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS code_strategy_versions (
                id TEXT PRIMARY KEY,
                strategy_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                source_code TEXT NOT NULL,
                validation_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(strategy_id, version_number)
            );

            CREATE TABLE IF NOT EXISTS tuning_runs (
                id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tuning_trials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tuning_run_id TEXT NOT NULL,
                backtest_run_id TEXT NOT NULL,
                params_json TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                score REAL NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tuning_layer_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tuning_run_id TEXT NOT NULL,
                layer_name TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                reason TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS live_states (
                strategy_version_id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS live_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_version_id TEXT NOT NULL,
                action TEXT NOT NULL,
                symbol TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                score REAL NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tax_reports (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tool_context_deltas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                input_json TEXT NOT NULL,
                output_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS session_state_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kite_candle_cache (
                cache_key TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                instrument_token TEXT NOT NULL,
                interval TEXT NOT NULL,
                from_ts TEXT NOT NULL,
                to_ts TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                dataset_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()


def save_intent_snapshot(paths: RuntimePaths, payload: dict[str, Any]) -> str:
    snapshot_id = str(uuid.uuid4())
    with connect(paths) as conn:
        conn.execute(
            "INSERT INTO intent_snapshots (id, payload_json, created_at) VALUES (?, ?, ?)",
            (snapshot_id, json.dumps(payload), _utc_now()),
        )
        conn.commit()
    return snapshot_id


def get_intent_snapshot(paths: RuntimePaths, snapshot_id: str) -> dict[str, Any]:
    with connect(paths) as conn:
        row = conn.execute(
            "SELECT payload_json FROM intent_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
    if row is None:
        raise ValueError(f"intent_snapshot not found: {snapshot_id}")
    return json.loads(row["payload_json"])


def save_strategy_version(paths: RuntimePaths, strategy_name: str, spec: dict[str, Any]) -> StrategyVersionRef:
    strategy_id = spec.get("strategy_id")
    if not strategy_id:
        raise ValueError("strategy_id missing from StrategySpec")

    with connect(paths) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO strategies (id, name, created_at) VALUES (?, ?, ?)",
            (strategy_id, strategy_name, _utc_now()),
        )
        row = conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) AS max_version FROM strategy_versions WHERE strategy_id = ?",
            (strategy_id,),
        ).fetchone()
        next_version = int(row["max_version"]) + 1
        version_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO strategy_versions (id, strategy_id, version_number, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (version_id, strategy_id, next_version, json.dumps(spec), _utc_now()),
        )
        conn.commit()
    return StrategyVersionRef(strategy_id=strategy_id, version_id=version_id, version_number=next_version)


def get_latest_strategy_spec(paths: RuntimePaths, strategy_id: str) -> dict[str, Any]:
    with connect(paths) as conn:
        row = conn.execute(
            """
            SELECT payload_json FROM strategy_versions
            WHERE strategy_id = ?
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (strategy_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"strategy_id not found: {strategy_id}")
    return json.loads(row["payload_json"])


def get_strategy_version(paths: RuntimePaths, strategy_version_id: str) -> dict[str, Any]:
    with connect(paths) as conn:
        row = conn.execute(
            """
            SELECT id, strategy_id, version_number, payload_json, created_at
            FROM strategy_versions
            WHERE id = ?
            """,
            (strategy_version_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"strategy_version_id not found: {strategy_version_id}")
    return {
        "strategy_version_id": row["id"],
        "strategy_id": row["strategy_id"],
        "version_number": int(row["version_number"]),
        "spec": json.loads(row["payload_json"]),
        "created_at": row["created_at"],
    }


def save_world_manifest(paths: RuntimePaths, manifest: dict[str, Any]) -> str:
    manifest_id = manifest.get("manifest_id") or str(uuid.uuid4())
    with connect(paths) as conn:
        conn.execute(
            "INSERT INTO world_manifests (id, payload_json, created_at) VALUES (?, ?, ?)",
            (manifest_id, json.dumps(manifest), _utc_now()),
        )
        conn.commit()
    return manifest_id


def save_backtest_run(
    paths: RuntimePaths,
    strategy_version_id: str,
    world_manifest_id: str,
    metrics: dict[str, Any],
    artifacts: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    run_id = str(uuid.uuid4())
    with connect(paths) as conn:
        conn.execute(
            """
            INSERT INTO backtest_runs (
                id, strategy_version_id, world_manifest_id, metrics_json, artifacts_json, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                strategy_version_id,
                world_manifest_id,
                json.dumps(metrics),
                json.dumps(artifacts),
                json.dumps(payload),
                _utc_now(),
            ),
        )
        conn.commit()
    return run_id


def get_backtest_run(paths: RuntimePaths, run_id: str) -> dict[str, Any]:
    with connect(paths) as conn:
        row = conn.execute(
            """
            SELECT id, strategy_version_id, world_manifest_id, metrics_json, artifacts_json, payload_json, created_at
            FROM backtest_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"backtest_run not found: {run_id}")
    return {
        "run_id": row["id"],
        "strategy_version_id": row["strategy_version_id"],
        "world_manifest_id": row["world_manifest_id"],
        "metrics": json.loads(row["metrics_json"]),
        "artifacts": json.loads(row["artifacts_json"]),
        "payload": json.loads(row["payload_json"]),
        "created_at": row["created_at"],
    }


def save_code_strategy_version(
    paths: RuntimePaths,
    strategy_name: str,
    source_code: str,
    validation: dict[str, Any],
) -> dict[str, Any]:
    if not strategy_name.strip():
        raise ValueError("strategy_name is required")
    if not source_code.strip():
        raise ValueError("source_code is required")

    with connect(paths) as conn:
        row = conn.execute(
            "SELECT id FROM code_strategies WHERE name = ?",
            (strategy_name,),
        ).fetchone()
        if row is None:
            strategy_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO code_strategies (id, name, created_at) VALUES (?, ?, ?)",
                (strategy_id, strategy_name, _utc_now()),
            )
        else:
            strategy_id = str(row["id"])

        max_row = conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) FROM code_strategy_versions WHERE strategy_id = ?",
            (strategy_id,),
        ).fetchone()
        version_number = int(max_row[0]) + 1
        version_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO code_strategy_versions
              (id, strategy_id, version_number, source_code, validation_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (version_id, strategy_id, version_number, source_code, json.dumps(validation), _utc_now()),
        )
        conn.commit()

    return {
        "strategy_id": strategy_id,
        "strategy_version_id": version_id,
        "version_number": version_number,
    }


def save_tuning_run(paths: RuntimePaths, strategy_name: str, payload: dict[str, Any]) -> str:
    if not strategy_name.strip():
        raise ValueError("strategy_name is required")
    run_id = str(payload.get("tuning_run_id", "")).strip() or str(uuid.uuid4())
    with connect(paths) as conn:
        conn.execute(
            """
            INSERT INTO tuning_runs (id, strategy_name, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, strategy_name, json.dumps(payload), _utc_now()),
        )
        evaluated = payload.get("evaluated_candidates")
        if evaluated is not None:
            if not isinstance(evaluated, list):
                raise ValueError("tuning payload evaluated_candidates must be a list when provided")
            for row in evaluated:
                if not isinstance(row, dict):
                    raise ValueError("tuning payload evaluated_candidates rows must be objects")
                backtest_run_id = str(row.get("run_id", "")).strip()
                params = row.get("params")
                metrics = row.get("metrics")
                if not backtest_run_id:
                    raise ValueError("tuning payload evaluated candidate missing run_id")
                if not isinstance(params, dict):
                    raise ValueError("tuning payload evaluated candidate params must be object")
                if not isinstance(metrics, dict):
                    raise ValueError("tuning payload evaluated candidate metrics must be object")
                score = row.get("score")
                try:
                    score_value = float(score)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"tuning payload evaluated candidate score must be numeric: {score}") from exc
                conn.execute(
                    """
                    INSERT INTO tuning_trials
                      (tuning_run_id, backtest_run_id, params_json, metrics_json, score, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        backtest_run_id,
                        json.dumps(params),
                        json.dumps(metrics),
                        score_value,
                        _utc_now(),
                    ),
                )

        tuning_plan = payload.get("tuning_plan")
        if tuning_plan is not None:
            if not isinstance(tuning_plan, dict):
                raise ValueError("tuning payload tuning_plan must be object when provided")
            layers = tuning_plan.get("layers")
            if layers is not None:
                if not isinstance(layers, list):
                    raise ValueError("tuning payload tuning_plan.layers must be list when provided")
                for layer in layers:
                    if not isinstance(layer, dict):
                        raise ValueError("tuning payload tuning_plan.layers rows must be objects")
                    layer_name = str(layer.get("layer", "")).strip()
                    reason = str(layer.get("reason", "")).strip()
                    enabled = bool(layer.get("enabled", False))
                    if not layer_name:
                        raise ValueError("tuning payload layer decision missing layer")
                    if not reason:
                        raise ValueError(f"tuning payload layer decision missing reason for layer={layer_name}")
                    conn.execute(
                        """
                        INSERT INTO tuning_layer_decisions
                          (tuning_run_id, layer_name, enabled, reason, payload_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            layer_name,
                            1 if enabled else 0,
                            reason,
                            json.dumps(layer),
                            _utc_now(),
                        ),
                    )
        conn.commit()
    return run_id


def list_tuning_trials(paths: RuntimePaths, tuning_run_id: str) -> list[dict[str, Any]]:
    if not tuning_run_id.strip():
        raise ValueError("tuning_run_id is required")
    with connect(paths) as conn:
        rows = conn.execute(
            """
            SELECT id, tuning_run_id, backtest_run_id, params_json, metrics_json, score, created_at
            FROM tuning_trials
            WHERE tuning_run_id = ?
            ORDER BY id ASC
            """,
            (tuning_run_id,),
        ).fetchall()
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                "id": int(row["id"]),
                "tuning_run_id": row["tuning_run_id"],
                "backtest_run_id": row["backtest_run_id"],
                "params": json.loads(row["params_json"]),
                "metrics": json.loads(row["metrics_json"]),
                "score": float(row["score"]),
                "created_at": row["created_at"],
            }
        )
    return payload


def list_tuning_layer_decisions(paths: RuntimePaths, tuning_run_id: str) -> list[dict[str, Any]]:
    if not tuning_run_id.strip():
        raise ValueError("tuning_run_id is required")
    with connect(paths) as conn:
        rows = conn.execute(
            """
            SELECT id, tuning_run_id, layer_name, enabled, reason, payload_json, created_at
            FROM tuning_layer_decisions
            WHERE tuning_run_id = ?
            ORDER BY id ASC
            """,
            (tuning_run_id,),
        ).fetchall()
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                "id": int(row["id"]),
                "tuning_run_id": row["tuning_run_id"],
                "layer_name": row["layer_name"],
                "enabled": bool(int(row["enabled"])),
                "reason": row["reason"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
        )
    return payload


def upsert_live_state(
    paths: RuntimePaths,
    strategy_version_id: str,
    strategy_name: str,
    status: str,
    payload: dict[str, Any],
) -> None:
    if status not in {"active", "paused", "stopped"}:
        raise ValueError("status must be one of: active, paused, stopped")
    now = _utc_now()
    with connect(paths) as conn:
        conn.execute(
            """
            INSERT INTO live_states (strategy_version_id, strategy_name, status, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(strategy_version_id)
            DO UPDATE SET
              strategy_name = excluded.strategy_name,
              status = excluded.status,
              payload_json = excluded.payload_json,
              updated_at = excluded.updated_at
            """,
            (strategy_version_id, strategy_name, status, json.dumps(payload), now, now),
        )
        conn.commit()


def get_live_state(paths: RuntimePaths, strategy_version_id: str) -> dict[str, Any]:
    with connect(paths) as conn:
        row = conn.execute(
            """
            SELECT strategy_version_id, strategy_name, status, payload_json, created_at, updated_at
            FROM live_states
            WHERE strategy_version_id = ?
            """,
            (strategy_version_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"live_state not found for strategy_version_id={strategy_version_id}")
    return {
        "strategy_version_id": row["strategy_version_id"],
        "strategy_name": row["strategy_name"],
        "status": row["status"],
        "payload": json.loads(row["payload_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def append_live_insight(
    paths: RuntimePaths,
    strategy_version_id: str,
    action: str,
    symbol: str,
    reason_code: str,
    score: float,
    payload: dict[str, Any],
) -> None:
    with connect(paths) as conn:
        conn.execute(
            """
            INSERT INTO live_insights
              (strategy_version_id, action, symbol, reason_code, score, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (strategy_version_id, action, symbol, reason_code, float(score), json.dumps(payload), _utc_now()),
        )
        conn.commit()


def list_live_insights(paths: RuntimePaths, strategy_version_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if strategy_version_id:
        query = """
            SELECT id, strategy_version_id, action, symbol, reason_code, score, payload_json, created_at
            FROM live_insights
            WHERE strategy_version_id = ?
            ORDER BY id DESC
            LIMIT ?
        """
        params: tuple[Any, ...] = (strategy_version_id, limit)
    else:
        query = """
            SELECT id, strategy_version_id, action, symbol, reason_code, score, payload_json, created_at
            FROM live_insights
            ORDER BY id DESC
            LIMIT ?
        """
        params = (limit,)
    with connect(paths) as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {
            "id": int(row["id"]),
            "strategy_version_id": row["strategy_version_id"],
            "action": row["action"],
            "symbol": row["symbol"],
            "reason_code": row["reason_code"],
            "score": float(row["score"]),
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def create_job(paths: RuntimePaths, job_type: str, payload: dict[str, Any]) -> str:
    job_id = str(uuid.uuid4())
    now = _utc_now()
    with connect(paths) as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, job_type, status, payload_json, result_json, error_text, fallback_reason, created_at, updated_at)
            VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, ?)
            """,
            (job_id, job_type, "queued", json.dumps(payload), now, now),
        )
        conn.commit()
    return job_id


def update_job_status(
    paths: RuntimePaths,
    job_id: str,
    status: str,
    result: Optional[dict[str, Any]] = None,
    error_text: Optional[str] = None,
    fallback_reason: Optional[str] = None,
) -> None:
    with connect(paths) as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, result_json = ?, error_text = ?, fallback_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                json.dumps(result) if result is not None else None,
                error_text,
                fallback_reason,
                _utc_now(),
                job_id,
            ),
        )
        conn.commit()


def get_job(paths: RuntimePaths, job_id: str) -> dict[str, Any]:
    with connect(paths) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"job not found: {job_id}")
    return {
        "id": row["id"],
        "job_type": row["job_type"],
        "status": row["status"],
        "payload": json.loads(row["payload_json"]),
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error_text": row["error_text"],
        "fallback_reason": row["fallback_reason"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def append_job_event(paths: RuntimePaths, job_id: str, event_type: str, payload: dict[str, Any]) -> None:
    with connect(paths) as conn:
        conn.execute(
            "INSERT INTO job_events (job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (job_id, event_type, json.dumps(payload), _utc_now()),
        )
        conn.commit()


def list_job_events_after(paths: RuntimePaths, last_id: int) -> list[dict[str, Any]]:
    with connect(paths) as conn:
        rows = conn.execute(
            "SELECT id, job_id, event_type, payload_json, created_at FROM job_events WHERE id > ? ORDER BY id ASC",
            (last_id,),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "job_id": row["job_id"],
            "event_type": row["event_type"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def append_audit_event(paths: RuntimePaths, event_type: str, payload: dict[str, Any]) -> None:
    merged_payload = redact_payload(dict(payload))
    merged_payload.setdefault("trace_id", get_trace_id())
    with connect(paths) as conn:
        conn.execute(
            "INSERT INTO audit_events (event_type, payload_json, created_at) VALUES (?, ?, ?)",
            (event_type, json.dumps(merged_payload), _utc_now()),
        )
        conn.commit()


def list_audit_events(paths: RuntimePaths, event_type: Optional[str] = None) -> list[dict[str, Any]]:
    if event_type:
        query = "SELECT id, event_type, payload_json, created_at FROM audit_events WHERE event_type = ? ORDER BY id ASC"
        params: tuple[Any, ...] = (event_type,)
    else:
        query = "SELECT id, event_type, payload_json, created_at FROM audit_events ORDER BY id ASC"
        params = ()
    with connect(paths) as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {
            "id": int(row["id"]),
            "event_type": row["event_type"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def create_oauth_state(paths: RuntimePaths, connector: str, state: str) -> None:
    if not connector:
        raise ValueError("connector is required")
    if not state:
        raise ValueError("state is required")
    with connect(paths) as conn:
        conn.execute(
            """
            INSERT INTO oauth_states (state, connector, created_at, consumed_at)
            VALUES (?, ?, ?, NULL)
            """,
            (state, connector, _utc_now()),
        )
        conn.commit()


def consume_oauth_state(paths: RuntimePaths, connector: str, state: str, max_age_seconds: int) -> None:
    if not connector:
        raise ValueError("connector is required")
    if not state:
        raise ValueError("state is required")
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")

    with connect(paths) as conn:
        row = conn.execute(
            """
            SELECT created_at, consumed_at
            FROM oauth_states
            WHERE connector = ? AND state = ?
            """,
            (connector, state),
        ).fetchone()
        if row is None:
            raise ValueError(f"oauth state not found for connector={connector}")
        if row["consumed_at"] is not None:
            raise ValueError(f"oauth state already consumed for connector={connector}")

        created_at = datetime.fromisoformat(row["created_at"])
        age = datetime.now(timezone.utc) - created_at
        if age.total_seconds() > max_age_seconds:
            raise ValueError(
                f"oauth state expired for connector={connector} age_seconds={int(age.total_seconds())}"
            )

        consumed_at = _utc_now()
        result = conn.execute(
            """
            UPDATE oauth_states
            SET consumed_at = ?
            WHERE connector = ? AND state = ? AND consumed_at IS NULL
            """,
            (consumed_at, connector, state),
        )
        if result.rowcount != 1:
            raise ValueError(f"failed to consume oauth state for connector={connector}")
        conn.commit()


def consume_latest_oauth_state(paths: RuntimePaths, connector: str, max_age_seconds: int) -> str:
    if not connector:
        raise ValueError("connector is required")
    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")

    with connect(paths) as conn:
        rows = conn.execute(
            """
            SELECT state, created_at
            FROM oauth_states
            WHERE connector = ? AND consumed_at IS NULL
            ORDER BY created_at DESC
            """,
            (connector,),
        ).fetchall()

        if not rows:
            raise ValueError(f"no pending oauth state for connector={connector}; generate a fresh connect_url")
        if len(rows) > 1:
            raise ValueError(
                f"multiple pending oauth states for connector={connector}; generate a fresh connect_url and retry once"
            )

        row = rows[0]
        state = str(row["state"])
        created_at = datetime.fromisoformat(str(row["created_at"]))
        age = datetime.now(timezone.utc) - created_at
        if age.total_seconds() > max_age_seconds:
            raise ValueError(
                f"latest oauth state expired for connector={connector} age_seconds={int(age.total_seconds())}"
            )

        consumed_at = _utc_now()
        result = conn.execute(
            """
            UPDATE oauth_states
            SET consumed_at = ?
            WHERE connector = ? AND state = ? AND consumed_at IS NULL
            """,
            (consumed_at, connector, state),
        )
        if result.rowcount != 1:
            raise ValueError(f"failed to consume latest oauth state for connector={connector}")
        conn.commit()
        return state


def upsert_connector_session(paths: RuntimePaths, connector: str, payload: dict[str, Any]) -> None:
    if not connector:
        raise ValueError("connector is required")
    now = _utc_now()
    serialized = json.dumps(payload)
    if encryption_enabled():
        serialized = encrypt_json(serialized)
    with connect(paths) as conn:
        conn.execute(
            """
            INSERT INTO connector_sessions (connector, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(connector)
            DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
            """,
            (connector, serialized, now, now),
        )
        conn.commit()


def get_connector_session(paths: RuntimePaths, connector: str) -> Optional[dict[str, Any]]:
    if not connector:
        raise ValueError("connector is required")
    with connect(paths) as conn:
        row = conn.execute(
            """
            SELECT payload_json
            FROM connector_sessions
            WHERE connector = ?
            """,
            (connector,),
        ).fetchone()
    if row is None:
        return None
    serialized = str(row["payload_json"])
    plain = decrypt_json(serialized)
    return json.loads(plain)


def save_tax_report(paths: RuntimePaths, run_id: str, payload: dict[str, Any]) -> str:
    report_id = str(uuid.uuid4())
    with connect(paths) as conn:
        conn.execute(
            "INSERT INTO tax_reports (id, run_id, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (report_id, run_id, json.dumps(payload), _utc_now()),
        )
        conn.commit()
    return report_id


def append_tool_context_delta(
    paths: RuntimePaths,
    session_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    tool_output: dict[str, Any],
) -> int:
    if not session_id.strip():
        raise ValueError("session_id is required")
    if not tool_name.strip():
        raise ValueError("tool_name is required")
    with connect(paths) as conn:
        cur = conn.execute(
            """
            INSERT INTO tool_context_deltas (session_id, tool_name, input_json, output_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                tool_name,
                json.dumps(redact_payload(tool_input)),
                json.dumps(redact_payload(tool_output)),
                _utc_now(),
            ),
        )
        conn.commit()
    return int(cur.lastrowid)


def save_session_state_snapshot(paths: RuntimePaths, session_id: str, state: dict[str, Any]) -> int:
    if not session_id.strip():
        raise ValueError("session_id is required")
    with connect(paths) as conn:
        cur = conn.execute(
            "INSERT INTO session_state_snapshots (session_id, state_json, created_at) VALUES (?, ?, ?)",
            (session_id, json.dumps(redact_payload(state)), _utc_now()),
        )
        conn.commit()
    return int(cur.lastrowid)


def get_latest_session_state_snapshot(paths: RuntimePaths, session_id: str) -> dict[str, Any]:
    if not session_id.strip():
        raise ValueError("session_id is required")
    with connect(paths) as conn:
        row = conn.execute(
            """
            SELECT id, state_json, created_at
            FROM session_state_snapshots
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"session snapshot not found for session_id={session_id}")
    return {
        "snapshot_id": int(row["id"]),
        "session_id": session_id,
        "state": json.loads(row["state_json"]),
        "created_at": row["created_at"],
    }


def list_tool_context_deltas(paths: RuntimePaths, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    with connect(paths) as conn:
        rows = conn.execute(
            """
            SELECT id, session_id, tool_name, input_json, output_json, created_at
            FROM tool_context_deltas
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "session_id": row["session_id"],
            "tool_name": row["tool_name"],
            "input": json.loads(row["input_json"]),
            "output": json.loads(row["output_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def list_session_state_snapshots(paths: RuntimePaths, session_id: str, limit: int = 2) -> list[dict[str, Any]]:
    if not session_id.strip():
        raise ValueError("session_id is required")
    if limit <= 0:
        raise ValueError("limit must be positive")
    with connect(paths) as conn:
        rows = conn.execute(
            """
            SELECT id, state_json, created_at
            FROM session_state_snapshots
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                "snapshot_id": int(row["id"]),
                "session_id": session_id,
                "state": json.loads(row["state_json"]),
                "created_at": row["created_at"],
            }
        )
    return payload


def upsert_kite_candle_cache(
    paths: RuntimePaths,
    cache_key: str,
    symbol: str,
    instrument_token: str,
    interval: str,
    from_ts: str,
    to_ts: str,
    row_count: int,
    dataset_hash: str,
) -> None:
    if not cache_key.strip():
        raise ValueError("cache_key is required")
    if row_count < 0:
        raise ValueError("row_count must be non-negative")
    with connect(paths) as conn:
        conn.execute(
            """
            INSERT INTO kite_candle_cache
              (cache_key, symbol, instrument_token, interval, from_ts, to_ts, row_count, dataset_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
              row_count = excluded.row_count,
              dataset_hash = excluded.dataset_hash,
              created_at = excluded.created_at
            """,
            (
                cache_key,
                symbol,
                instrument_token,
                interval,
                from_ts,
                to_ts,
                int(row_count),
                dataset_hash,
                _utc_now(),
            ),
        )
        conn.commit()


def get_kite_candle_cache(paths: RuntimePaths, cache_key: str) -> Optional[dict[str, Any]]:
    if not cache_key.strip():
        raise ValueError("cache_key is required")
    with connect(paths) as conn:
        row = conn.execute(
            """
            SELECT cache_key, symbol, instrument_token, interval, from_ts, to_ts, row_count, dataset_hash, created_at
            FROM kite_candle_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
    if row is None:
        return None
    return {
        "cache_key": row["cache_key"],
        "symbol": row["symbol"],
        "instrument_token": row["instrument_token"],
        "interval": row["interval"],
        "from_ts": row["from_ts"],
        "to_ts": row["to_ts"],
        "row_count": int(row["row_count"]),
        "dataset_hash": row["dataset_hash"],
        "created_at": row["created_at"],
    }
