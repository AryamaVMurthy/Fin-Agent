from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import duckdb
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from fin_agent.backtest.compare import compare_backtest_runs
from fin_agent.analysis.preflight import (
    enforce_custom_code_budget,
    enforce_world_state_budget,
)
from fin_agent.code_strategy.analysis import analyze_code_strategy_run
from fin_agent.code_strategy.backtest import run_code_strategy_backtest
from fin_agent.code_strategy.runner import run_code_strategy_sandbox
from fin_agent.code_strategy.validator import validate_code_strategy_source
from fin_agent.data.importer import (
    import_corporate_actions_file,
    import_fundamentals_file,
    import_ohlcv_file,
    import_ratings_file,
    query_fundamentals_as_of,
)
from fin_agent.data.technicals import compute_sma_features
from fin_agent.data.universe import resolve_universe
from fin_agent.integrations import kite as kite_integration
from fin_agent.integrations import opencode_auth as opencode_auth_integration
from fin_agent.integrations import rate_limit as rate_limit_integration
from fin_agent.integrations import tradingview as tradingview_integration
from fin_agent.integrations.nse import fetch_nse_equity_quote
from fin_agent.live.service import boundary_candidates as select_boundary_candidates
from fin_agent.live.service import build_live_snapshot, write_boundary_chart
from fin_agent.observability.context import get_trace_id, reset_trace_id, set_trace_id
from fin_agent.security import encryption_enabled, redact_payload
from fin_agent.screener.service import run_formula_screen, validate_formula
from fin_agent.storage import duckdb_store, sqlite_store
from fin_agent.storage.paths import RuntimePaths
from fin_agent.tax import IndiaTaxAssumptions, compute_tax_report
from fin_agent.world_state.service import (
    build_data_completeness_report,
    build_world_state_manifest,
    validate_world_state_pit,
)

def _runtime_paths() -> RuntimePaths:
    root = Path(os.environ.get("FIN_AGENT_HOME", ".finagent"))
    return RuntimePaths(root=root)


def _current_trace_id() -> str:
    return get_trace_id()


def _write_structured_log(event_type: str, payload: dict[str, Any]) -> None:
    paths = _runtime_paths()
    paths.ensure()
    log_path = paths.logs_dir / "structured.log"
    row = redact_payload(
        {
        "event_type": event_type,
        "trace_id": _current_trace_id(),
        **payload,
        }
    )
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _append_audit_event(paths: RuntimePaths, event_type: str, payload: dict[str, Any]) -> None:
    sqlite_store.append_audit_event(
        paths,
        event_type,
        {
            **redact_payload(payload),
            "trace_id": _current_trace_id(),
        },
    )


def _read_structured_log_stats(paths: RuntimePaths) -> dict[str, Any]:
    log_path = paths.logs_dir / "structured.log"
    if not log_path.exists():
        return {
            "request_count": 0,
            "error_count": 0,
            "avg_request_duration_ms": 0.0,
        }
    request_count = 0
    error_count = 0
    durations: list[float] = []
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event_type") == "request.end":
                request_count += 1
                durations.append(float(row.get("duration_ms", 0.0)))
            if str(row.get("event_type", "")).endswith("error"):
                error_count += 1
    avg = sum(durations) / len(durations) if durations else 0.0
    return {
        "request_count": request_count,
        "error_count": error_count,
        "avg_request_duration_ms": round(avg, 4),
    }


def _max_backtest_seconds() -> float:
    value = os.environ.get("FIN_AGENT_MAX_BACKTEST_SECONDS", "30")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"invalid FIN_AGENT_MAX_BACKTEST_SECONDS value: {value}") from exc
    if parsed <= 0:
        raise ValueError("FIN_AGENT_MAX_BACKTEST_SECONDS must be positive")
    return parsed


def _max_world_state_seconds() -> float:
    value = os.environ.get("FIN_AGENT_MAX_WORLD_STATE_SECONDS", "20")
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"invalid FIN_AGENT_MAX_WORLD_STATE_SECONDS value: {value}") from exc
    if parsed <= 0:
        raise ValueError("FIN_AGENT_MAX_WORLD_STATE_SECONDS must be positive")
    return parsed


class ImportRequest(BaseModel):
    path: str


class FundamentalsAsOfRequest(BaseModel):
    symbol: str
    as_of: str


class StrategyBuildRequest(BaseModel):
    strategy_name: str = Field(min_length=3)


class AgentDecidesProposeRequest(BaseModel):
    universe: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    initial_capital: float | None = Field(default=None, gt=0)
    short_window: int | None = Field(default=None, ge=1)
    long_window: int | None = Field(default=None, ge=2)
    max_positions: int | None = Field(default=None, ge=1)


class DecisionCardItem(BaseModel):
    field: str
    value: Any
    source: str
    rationale: str
    confidence: float = Field(ge=0, le=1)


class AgentDecidesConfirmRequest(BaseModel):
    intent: dict[str, Any]
    decision_card: list[DecisionCardItem]


class WorldBuildRequest(BaseModel):
    universe: list[str]
    start_date: str
    end_date: str
    adjustment_policy: str = "none"


class WorldValidationRequest(WorldBuildRequest):
    strict_mode: bool = True


class PreflightWorldStateRequest(WorldBuildRequest):
    max_allowed_seconds: float = Field(gt=0)


class TechnicalsRequest(BaseModel):
    universe: list[str]
    start_date: str
    end_date: str
    short_window: int = Field(ge=1, default=5)
    long_window: int = Field(ge=2, default=20)


class BacktestRequest(BaseModel):
    strategy_name: str


class BacktestCompareRequest(BaseModel):
    baseline_run_id: str
    candidate_run_id: str


class PreflightBacktestRequest(BacktestRequest):
    max_allowed_seconds: float = Field(gt=0)


class PreflightTuningRequest(BaseModel):
    num_trials: int = Field(gt=0)
    per_trial_estimated_seconds: float = Field(gt=0)
    max_allowed_seconds: float = Field(gt=0)


class PreflightCustomCodeRequest(WorldBuildRequest):
    complexity_multiplier: float = Field(gt=0)
    max_allowed_seconds: float = Field(gt=0)


class CodeStrategyValidateRequest(BaseModel):
    strategy_name: str | None = None
    source_code: str


class CodeStrategySaveRequest(BaseModel):
    strategy_name: str = Field(min_length=1)
    source_code: str


class CodeStrategyRunRequest(BaseModel):
    source_code: str
    timeout_seconds: int = Field(gt=0, default=5)
    memory_mb: int = Field(gt=0, default=256)
    cpu_seconds: int = Field(gt=0, default=2)


class CodeStrategyBacktestRequest(BaseModel):
    strategy_name: str = Field(min_length=1)
    source_code: str
    universe: list[str] = Field(min_length=1)
    start_date: str
    end_date: str
    initial_capital: float = Field(gt=0)
    timeout_seconds: int = Field(gt=0, default=5)
    memory_mb: int = Field(gt=0, default=256)
    cpu_seconds: int = Field(gt=0, default=2)


class CodeStrategyAnalyzeRequest(BaseModel):
    run_id: str
    source_code: str
    max_suggestions: int = Field(gt=0, le=20, default=5)


class TuningSearchSpaceRequest(BaseModel):
    strategy_name: str = Field(min_length=1)
    optimization_target: str = "sharpe"
    risk_mode: str = "balanced"
    policy_mode: str = "agent_decides"
    include_layers: list[str] | None = None
    freeze_params: dict[str, float] | None = None
    search_space_overrides: dict[str, list[float]] | None = None
    max_drawdown_limit: float | None = Field(default=None, gt=0)
    turnover_cap: int | None = Field(default=None, gt=0)


class TuningRunRequest(TuningSearchSpaceRequest):
    search_space: dict[str, list[float]] | None = None
    max_trials: int = Field(gt=0, default=20)
    per_trial_estimated_seconds: float = Field(gt=0, default=0.5)


class AnalysisDeepDiveRequest(BaseModel):
    run_id: str


class TradeBlotterRequest(BaseModel):
    run_id: str


class BoundaryVisualizationRequest(BaseModel):
    strategy_version_id: str
    top_k: int = Field(gt=0, le=100, default=10)


class LiveActivateRequest(BaseModel):
    strategy_version_id: str


class LiveLifecycleRequest(BaseModel):
    strategy_version_id: str


class KiteInstrumentsSyncRequest(BaseModel):
    exchange: str | None = None
    max_rows: int = Field(default=20000, gt=0)


class KiteCandlesFetchRequest(BaseModel):
    symbol: str = Field(min_length=1)
    instrument_token: str = Field(min_length=1)
    interval: str = Field(min_length=1)
    from_ts: str = Field(min_length=1)
    to_ts: str = Field(min_length=1)
    persist: bool = True
    use_cache: bool = True
    force_refresh: bool = False


class KiteQuotesFetchRequest(BaseModel):
    instruments: list[str] = Field(min_length=1)
    persist: bool = True


class ScreenerFormulaValidateRequest(BaseModel):
    formula: str = Field(min_length=1)


class ScreenerRunRequest(BaseModel):
    formula: str = Field(min_length=1)
    as_of: str
    universe: list[str] = Field(min_length=1)
    top_k: int = Field(default=50, gt=0)
    rank_by: str | None = None
    sort_order: str = "desc"


class TradingViewScanRequest(BaseModel):
    where: list[dict[str, Any]] | None = None
    columns: list[str] | None = None
    limit: int = Field(default=50, gt=0)


class NseQuoteRequest(BaseModel):
    symbol: str = Field(min_length=1)


class BacktestTaxReportRequest(BaseModel):
    run_id: str
    enabled: bool = False
    stcg_rate: float = Field(default=0.20, gt=0)
    ltcg_rate: float = Field(default=0.125, gt=0)
    ltcg_exemption_amount: float = Field(default=125000.0, ge=0)
    apply_cess: bool = True
    cess_rate: float = Field(default=0.04, ge=0)
    include_charges: bool = True


class SessionSnapshotRequest(BaseModel):
    session_id: str = Field(min_length=1)
    state: dict[str, Any]


class SessionRehydrateRequest(BaseModel):
    session_id: str = Field(min_length=1)


class ContextDeltaRequest(BaseModel):
    session_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    tool_input: dict[str, Any]
    tool_output: dict[str, Any]


app = FastAPI(title="Fin-Agent Stage 1 API", version="0.1.0")


@app.middleware("http")
async def trace_logging_middleware(request, call_next):  # type: ignore[no-untyped-def]
    trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
    token = set_trace_id(trace_id)
    started = time.perf_counter()
    _write_structured_log(
        "request.start",
        {
            "method": request.method,
            "path": request.url.path,
        },
    )
    status_code = 500
    try:
        response = await call_next(request)
        status_code = int(response.status_code)
        response.headers["x-trace-id"] = trace_id
        return response
    except Exception as exc:  # noqa: BLE001
        _write_structured_log(
            "request.error",
            {
                "method": request.method,
                "path": request.url.path,
                "error": str(exc),
                "remediation": "check structured.log with same trace_id and inspect failing endpoint payload",
            },
        )
        raise
    finally:
        duration_ms = (time.perf_counter() - started) * 1000.0
        _write_structured_log(
            "request.end",
            {
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 3),
            },
        )
        reset_trace_id(token)


@app.on_event("startup")
def startup() -> None:
    paths = _runtime_paths()
    paths.ensure()
    sqlite_store.init_db(paths)
    duckdb_store.init_db(paths)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _load_kite_config_or_raise() -> kite_integration.KiteConfig:
    try:
        return kite_integration.load_kite_config_from_env()
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"invalid Kite config: {exc}. Set FIN_AGENT_KITE_API_KEY, FIN_AGENT_KITE_API_SECRET, FIN_AGENT_KITE_REDIRECT_URI.",
        ) from exc


def _kite_access_token_or_reauth_required(paths: RuntimePaths) -> tuple[str, dict[str, Any]]:
    session = sqlite_store.get_connector_session(paths, connector="kite")
    if session is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "reauth_required",
                "message": "kite session not found",
                "remediation": "call /v1/auth/kite/connect and complete login",
            },
        )
    token = session.get("token", {})
    access_token = str(token.get("access_token", "")).strip()
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "reauth_required",
                "message": "kite access token missing in stored session",
                "remediation": "call /v1/auth/kite/connect and complete login",
            },
        )
    return access_token, session


def _map_kite_error(exc: ValueError) -> HTTPException:
    text = str(exc)
    if "TokenException" in text or "invalid or has expired" in text.lower():
        return HTTPException(
            status_code=401,
            detail={
                "code": "reauth_required",
                "message": "kite access token is invalid or expired",
                "remediation": "call /v1/auth/kite/connect and complete login again",
                "source_error": text,
            },
        )
    return HTTPException(
        status_code=502,
        detail={
            "code": "kite_upstream_error",
            "message": "failed to fetch data from kite",
            "source_error": text,
        },
    )


def _json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provider_rate_limit_or_raise(provider: str) -> dict[str, float | int]:
    try:
        return rate_limit_integration.enforce_provider_limit(provider)
    except ValueError as exc:
        text = str(exc)
        if text.startswith("provider_rate_limited"):
            retry_after = 1.0
            marker = "retry_after_seconds="
            idx = text.find(marker)
            if idx >= 0:
                retry_fragment = text[idx + len(marker):].strip()
                try:
                    retry_after = float(retry_fragment)
                except ValueError:
                    retry_after = 1.0
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "provider_rate_limited",
                    "provider": provider,
                    "source_error": text,
                    "retry_after_seconds": retry_after,
                    "remediation": "retry after the suggested delay or reduce polling frequency",
                },
            ) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _kite_candle_cache_key(request: KiteCandlesFetchRequest) -> str:
    return _json_hash(
        {
            "symbol": request.symbol,
            "instrument_token": request.instrument_token,
            "interval": request.interval,
            "from_ts": request.from_ts,
            "to_ts": request.to_ts,
        }
    )


def _flatten_state_diff(path: str, before: Any, after: Any, changes: list[dict[str, Any]]) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        keys = sorted(set(before.keys()) | set(after.keys()))
        for key in keys:
            current_path = f"{path}.{key}" if path else str(key)
            if key not in before:
                changes.append({"path": current_path, "change_type": "added", "before": None, "after": after[key]})
                continue
            if key not in after:
                changes.append({"path": current_path, "change_type": "removed", "before": before[key], "after": None})
                continue
            _flatten_state_diff(current_path, before[key], after[key], changes)
        return
    if isinstance(before, list) and isinstance(after, list):
        if before != after:
            changes.append({"path": path or "$", "change_type": "changed", "before": before, "after": after})
        return
    if before != after:
        changes.append({"path": path or "$", "change_type": "changed", "before": before, "after": after})


@app.get("/v1/auth/kite/connect")
def auth_kite_connect() -> dict[str, Any]:
    config = _load_kite_config_or_raise()
    paths = _runtime_paths()
    state = kite_integration.generate_oauth_state()
    sqlite_store.create_oauth_state(paths, connector="kite", state=state)
    connect_url = kite_integration.build_login_url(config=config, state=state)
    _append_audit_event(
        paths,
        "auth.kite.connect.requested",
        {
            "connector": "kite",
            "redirect_uri": config.redirect_uri,
        },
    )
    return {
        "connector": "kite",
        "connect_url": connect_url,
        "redirect_uri": config.redirect_uri,
        "state": state,
    }


@app.get("/v1/auth/opencode/openai/oauth/status")
def auth_opencode_openai_oauth_status() -> dict[str, Any]:
    status = opencode_auth_integration.get_openai_oauth_status()
    if not status.get("opencode_installed", False):
        raise HTTPException(
            status_code=500,
            detail="opencode not available in PATH; install opencode and retry",
        )
    if status.get("error"):
        raise HTTPException(status_code=502, detail=str(status["error"]))
    return status


@app.get("/v1/auth/opencode/openai/oauth/connect")
def auth_opencode_openai_oauth_connect() -> dict[str, Any]:
    status = opencode_auth_integration.get_openai_oauth_status()
    if not status.get("opencode_installed", False):
        raise HTTPException(
            status_code=500,
            detail="opencode not available in PATH; install opencode and retry",
        )
    if status.get("error"):
        raise HTTPException(status_code=502, detail=str(status["error"]))

    if status.get("connected"):
        return {
            **status,
            "action": "already_connected",
            "message": "OpenCode OpenAI credential already connected",
        }

    return {
        **status,
        "action": "run_connect_command",
        "message": "Run OpenAI OAuth login in terminal/OpenCode TUI, or provide OPENAI_API_KEY in environment",
        "connect_command": "opencode auth login openai",
        "tui_command": "/connect",
    }


@app.get("/v1/auth/kite/callback")
def auth_kite_callback(
    request_token: str | None = Query(default=None),
    state: str | None = Query(default=None),
    action: str | None = Query(default=None),
    status: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> dict[str, Any]:
    if action == "cancel" or status == "error" or error:
        raise HTTPException(
            status_code=400,
            detail=f"kite authorization was not completed action={action} status={status} error={error}",
        )
    if not request_token:
        raise HTTPException(status_code=400, detail="missing required query param: request_token")

    paths = _runtime_paths()
    state_mode = "provided"
    resolved_state = state
    try:
        if resolved_state:
            sqlite_store.consume_oauth_state(paths, connector="kite", state=resolved_state, max_age_seconds=900)
        else:
            state_mode = "latest_pending"
            resolved_state = sqlite_store.consume_latest_oauth_state(paths, connector="kite", max_age_seconds=900)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    config = _load_kite_config_or_raise()
    try:
        session = kite_integration.create_kite_session(config=config, request_token=request_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"failed to complete Kite token exchange: {exc}",
        ) from exc

    sqlite_store.upsert_connector_session(paths, connector="kite", payload=session)
    profile = session.get("profile", {})
    _append_audit_event(
        paths,
        "auth.kite.connected",
        {
            "connector": "kite",
            "state_mode": state_mode,
            "oauth_state": resolved_state,
            "kite_user_id": profile.get("user_id"),
            "user_name": profile.get("user_name"),
        },
    )
    return {
        "connector": "kite",
        "status": "connected",
        "state_mode": state_mode,
        "kite_user_id": profile.get("user_id"),
        "user_name": profile.get("user_name"),
        "connected_at": session.get("connected_at"),
    }


@app.get("/v1/auth/kite/status")
def auth_kite_status() -> dict[str, Any]:
    paths = _runtime_paths()
    session = sqlite_store.get_connector_session(paths, connector="kite")

    config_error: str | None = None
    config: kite_integration.KiteConfig | None = None
    try:
        config = kite_integration.load_kite_config_from_env()
    except ValueError as exc:
        config_error = str(exc)

    connected = session is not None
    configured = config is not None
    response: dict[str, Any] = {
        "connector": "kite",
        "configured": configured,
        "connected": connected,
    }
    if not configured:
        response["config_error"] = config_error
        return response

    assert config is not None
    response["redirect_uri"] = config.redirect_uri
    response["api_key_suffix"] = config.api_key[-4:]

    if session is not None:
        profile = session.get("profile", {})
        token = session.get("token", {})
        response.update(
            {
                "kite_user_id": profile.get("user_id"),
                "user_name": profile.get("user_name"),
                "email": profile.get("email"),
                "connected_at": session.get("connected_at"),
                "login_time": token.get("login_time"),
                "access_token_masked": kite_integration.mask_secret(token.get("access_token")),
            }
        )
    return response


@app.get("/v1/kite/profile")
def kite_profile() -> dict[str, Any]:
    paths = _runtime_paths()
    _provider_rate_limit_or_raise("kite")
    config = _load_kite_config_or_raise()
    access_token, _session = _kite_access_token_or_reauth_required(paths)
    try:
        profile = kite_integration.fetch_profile(config=config, access_token=access_token)
    except ValueError as exc:
        raise _map_kite_error(exc) from exc
    return {"connector": "kite", "profile": profile}


@app.get("/v1/kite/holdings")
def kite_holdings() -> dict[str, Any]:
    paths = _runtime_paths()
    _provider_rate_limit_or_raise("kite")
    config = _load_kite_config_or_raise()
    access_token, _session = _kite_access_token_or_reauth_required(paths)
    try:
        holdings = kite_integration.fetch_holdings(config=config, access_token=access_token)
    except ValueError as exc:
        raise _map_kite_error(exc) from exc
    return {"connector": "kite", "holdings": holdings, "count": len(holdings)}


@app.post("/v1/kite/instruments/sync")
def kite_instruments_sync(request: KiteInstrumentsSyncRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    _provider_rate_limit_or_raise("kite")
    config = _load_kite_config_or_raise()
    access_token, _session = _kite_access_token_or_reauth_required(paths)
    try:
        rows = kite_integration.fetch_instruments(
            config=config,
            access_token=access_token,
            exchange=request.exchange,
        )
    except ValueError as exc:
        raise _map_kite_error(exc) from exc

    bounded = rows[: request.max_rows]
    now = datetime.now(timezone.utc).isoformat()
    dataset_hash = _json_hash(bounded)
    duckdb_store.init_db(paths)
    with duckdb.connect(str(paths.duckdb_path)) as conn:
        conn.execute("DELETE FROM market_instruments WHERE source = 'kite'")
        for row in bounded:
            conn.execute(
                """
                INSERT INTO market_instruments
                  (instrument_token, exchange, segment, tradingsymbol, name, lot_size, tick_size, expiry, strike, instrument_type, source, dataset_hash, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'kite', ?, CAST(? AS TIMESTAMP))
                """,
                [
                    str(row.get("instrument_token", "")).strip(),
                    str(row.get("exchange", "")).strip() or None,
                    str(row.get("segment", "")).strip() or None,
                    str(row.get("tradingsymbol", "")).strip(),
                    str(row.get("name", "")).strip() or None,
                    float(row.get("lot_size", 0.0)) if row.get("lot_size") is not None else None,
                    float(row.get("tick_size", 0.0)) if row.get("tick_size") is not None else None,
                    str(row.get("expiry", "")).strip() or None,
                    float(row.get("strike", 0.0)) if row.get("strike") is not None else None,
                    str(row.get("instrument_type", "")).strip() or None,
                    dataset_hash,
                    now,
                ],
            )
    _append_audit_event(
        paths,
        "kite.instruments.sync",
        {
            "exchange": request.exchange,
            "rows": len(bounded),
            "dataset_hash": dataset_hash,
        },
    )
    return {"connector": "kite", "rows": len(bounded), "dataset_hash": dataset_hash}


@app.post("/v1/kite/candles/fetch")
def kite_candles_fetch(request: KiteCandlesFetchRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    cache_key = _kite_candle_cache_key(request)
    if request.use_cache and not request.force_refresh:
        cached = sqlite_store.get_kite_candle_cache(paths, cache_key)
        if cached is not None:
            _append_audit_event(
                paths,
                "kite.candles.fetch.cache_hit",
                {
                    "symbol": request.symbol,
                    "instrument_token": request.instrument_token,
                    "interval": request.interval,
                    "cache_key": cache_key,
                    "dataset_hash": cached["dataset_hash"],
                    "rows": cached["row_count"],
                },
            )
            return {
                "connector": "kite",
                "symbol": request.symbol,
                "interval": request.interval,
                "rows": int(cached["row_count"]),
                "persisted_rows": 0,
                "dataset_hash": cached["dataset_hash"],
                "cache_hit": True,
                "cache_key": cache_key,
            }

    _provider_rate_limit_or_raise("kite")
    config = _load_kite_config_or_raise()
    access_token, _session = _kite_access_token_or_reauth_required(paths)
    try:
        rows = kite_integration.fetch_historical_candles(
            config=config,
            access_token=access_token,
            instrument_token=request.instrument_token,
            interval=request.interval,
            from_ts=request.from_ts,
            to_ts=request.to_ts,
        )
    except ValueError as exc:
        raise _map_kite_error(exc) from exc

    inserted = 0
    dataset_hash = _json_hash(rows)
    if request.persist:
        now = datetime.now(timezone.utc).isoformat()
        duckdb_store.init_db(paths)
        with duckdb.connect(str(paths.duckdb_path)) as conn:
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO market_ohlcv (timestamp, published_at, symbol, open, high, low, close, volume, source_file, dataset_hash, ingested_at)
                    VALUES (
                      CAST(? AS TIMESTAMP),
                      CAST(? AS TIMESTAMP),
                      ?, ?, ?, ?, ?, ?,
                      'kite_api', ?, CAST(? AS TIMESTAMP)
                    )
                    """,
                    [
                        row["timestamp"],
                        row["timestamp"],
                        request.symbol,
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row["volume"]),
                        dataset_hash,
                        now,
                    ],
                )
                inserted += 1
        sqlite_store.upsert_kite_candle_cache(
            paths,
            cache_key=cache_key,
            symbol=request.symbol,
            instrument_token=request.instrument_token,
            interval=request.interval,
            from_ts=request.from_ts,
            to_ts=request.to_ts,
            row_count=len(rows),
            dataset_hash=dataset_hash,
        )

    _append_audit_event(
        paths,
        "kite.candles.fetch",
        {
            "symbol": request.symbol,
            "instrument_token": request.instrument_token,
            "interval": request.interval,
            "rows": len(rows),
            "persisted_rows": inserted,
            "dataset_hash": dataset_hash,
            "cache_key": cache_key,
        },
    )
    return {
        "connector": "kite",
        "symbol": request.symbol,
        "interval": request.interval,
        "rows": len(rows),
        "persisted_rows": inserted,
        "dataset_hash": dataset_hash,
        "cache_hit": False,
        "cache_key": cache_key,
    }


@app.post("/v1/kite/quotes/fetch")
def kite_quotes_fetch(request: KiteQuotesFetchRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    _provider_rate_limit_or_raise("kite")
    config = _load_kite_config_or_raise()
    access_token, _session = _kite_access_token_or_reauth_required(paths)
    try:
        payload = kite_integration.fetch_ltp(
            config=config,
            access_token=access_token,
            instruments=request.instruments,
        )
    except ValueError as exc:
        raise _map_kite_error(exc) from exc

    persisted = 0
    if request.persist:
        now = datetime.now(timezone.utc).isoformat()
        duckdb_store.init_db(paths)
        with duckdb.connect(str(paths.duckdb_path)) as conn:
            for key, row in payload.items():
                conn.execute(
                    """
                    INSERT INTO market_quotes (quote_key, instrument_token, last_price, payload_json, source, fetched_at)
                    VALUES (?, ?, ?, ?, 'kite', CAST(? AS TIMESTAMP))
                    """,
                    [
                        key,
                        str(row.get("instrument_token", "")).strip() or None,
                        float(row.get("last_price", 0.0)) if row.get("last_price") is not None else None,
                        json.dumps(row, sort_keys=True, default=str),
                        now,
                    ],
                )
                persisted += 1

    _append_audit_event(
        paths,
        "kite.quotes.fetch",
        {
            "requested": len(request.instruments),
            "received": len(payload),
            "persisted": persisted,
        },
    )
    return {
        "connector": "kite",
        "requested": len(request.instruments),
        "received": len(payload),
        "persisted": persisted,
        "quotes": payload,
    }


@app.post("/v1/data/import")
def import_data(request: ImportRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    result = import_ohlcv_file(Path(request.path), paths)
    return {
        "source_path": result.source_path,
        "rows_inserted": result.rows_inserted,
        "dataset_hash": result.dataset_hash,
    }


@app.post("/v1/data/import/fundamentals")
def import_fundamentals(request: ImportRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        result = import_fundamentals_file(Path(request.path), paths)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "source_path": result.source_path,
        "rows_inserted": result.rows_inserted,
        "dataset_hash": result.dataset_hash,
    }


@app.post("/v1/data/import/corporate-actions")
def import_corporate_actions(request: ImportRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        result = import_corporate_actions_file(Path(request.path), paths)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "source_path": result.source_path,
        "rows_inserted": result.rows_inserted,
        "dataset_hash": result.dataset_hash,
    }


@app.post("/v1/data/import/ratings")
def import_ratings(request: ImportRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        result = import_ratings_file(Path(request.path), paths)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "source_path": result.source_path,
        "rows_inserted": result.rows_inserted,
        "dataset_hash": result.dataset_hash,
    }


@app.post("/v1/data/fundamentals/as-of")
def fundamentals_as_of(request: FundamentalsAsOfRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        row = query_fundamentals_as_of(paths, symbol=request.symbol, as_of=request.as_of)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"row": row}


@app.post("/v1/brainstorm/lock")
def lock_intent(intent: dict[str, Any]) -> dict[str, Any]:
    _legacy_endpoint_disabled("/v1/brainstorm/lock")
    return {}


@app.post("/v1/brainstorm/agent-decides/propose")
def brainstorm_agent_decides_propose(request: AgentDecidesProposeRequest) -> dict[str, Any]:
    _legacy_endpoint_disabled("/v1/brainstorm/agent-decides/propose")
    return {}


@app.post("/v1/brainstorm/agent-decides/confirm")
def brainstorm_agent_decides_confirm(request: AgentDecidesConfirmRequest) -> dict[str, Any]:
    _legacy_endpoint_disabled("/v1/brainstorm/agent-decides/confirm")
    return {}


@app.post("/v1/code-strategy/validate")
def code_strategy_validate(request: CodeStrategyValidateRequest) -> dict[str, Any]:
    try:
        validation = validate_code_strategy_source(request.source_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "strategy_name": request.strategy_name,
        "validation": validation,
    }


@app.post("/v1/code-strategy/save")
def code_strategy_save(request: CodeStrategySaveRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        validation = validate_code_strategy_source(request.source_code)
        saved = sqlite_store.save_code_strategy_version(
            paths,
            strategy_name=request.strategy_name,
            source_code=request.source_code,
            validation=validation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _append_audit_event(
        paths,
        "code.strategy.save",
        {
            "strategy_name": request.strategy_name,
            "strategy_id": saved["strategy_id"],
            "strategy_version_id": saved["strategy_version_id"],
            "version_number": saved["version_number"],
        },
    )
    return {
        **saved,
        "validation": validation,
    }


@app.get("/v1/code-strategies")
def code_strategies_list(limit: int = Query(default=100, gt=0)) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        strategies = sqlite_store.list_code_strategies(paths, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"strategies": strategies, "count": len(strategies)}


@app.get("/v1/code-strategies/{strategy_id}/versions")
def code_strategy_versions_list(strategy_id: str, limit: int = Query(default=100, gt=0)) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        versions = sqlite_store.list_code_strategy_versions(paths, strategy_id=strategy_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"strategy_id": strategy_id, "versions": versions, "count": len(versions)}


@app.post("/v1/code-strategy/run-sandbox")
def code_strategy_run_sandbox(request: CodeStrategyRunRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        validation = validate_code_strategy_source(request.source_code)
        run = run_code_strategy_sandbox(
            paths,
            source_code=request.source_code,
            timeout_seconds=request.timeout_seconds,
            memory_mb=request.memory_mb,
            cpu_seconds=request.cpu_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _append_audit_event(
        paths,
        "code.strategy.run_sandbox",
        {
            "run_id": run["run_id"],
            "result_path": run["result_path"],
        },
    )
    return {
        **run,
        "validation": validation,
    }


@app.post("/v1/code-strategy/backtest")
def code_strategy_backtest(request: CodeStrategyBacktestRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        complexity_multiplier = max(1.0, min(5.0, len(request.source_code.splitlines()) / 120.0))
        preflight = enforce_custom_code_budget(
            paths,
            universe=request.universe,
            start_date=request.start_date,
            end_date=request.end_date,
            complexity_multiplier=complexity_multiplier,
            max_estimated_seconds=_max_backtest_seconds(),
        )
        run = run_code_strategy_backtest(
            paths=paths,
            strategy_name=request.strategy_name,
            source_code=request.source_code,
            universe=request.universe,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            timeout_seconds=request.timeout_seconds,
            memory_mb=request.memory_mb,
            cpu_seconds=request.cpu_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _append_audit_event(
        paths,
        "code.backtest.run",
        {
            "run_id": run["run_id"],
            "strategy_name": request.strategy_name,
            "strategy_version_id": run["strategy_version_id"],
            "signals_count": run["signals_count"],
            "preflight": preflight,
        },
    )
    return {**run, "preflight": preflight}


@app.post("/v1/code-strategy/analyze")
def code_strategy_analyze(request: CodeStrategyAnalyzeRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        report = analyze_code_strategy_run(
            paths=paths,
            run_id=request.run_id,
            source_code=request.source_code,
            max_suggestions=request.max_suggestions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _append_audit_event(
        paths,
        "code.analysis.deep_dive",
        {
            "run_id": request.run_id,
            "suggestion_count": report["suggestion_count"],
            "mode": report["mode"],
            "auto_apply": report["auto_apply"],
        },
    )
    return report


def _legacy_endpoint_disabled(path: str) -> None:
    raise HTTPException(
        status_code=410,
        detail={
            "error": "legacy_endpoint_disabled",
            "path": path,
            "reason": "legacy intent/manual strategy flow has been removed",
            "remediation": {
                "required_flow": [
                    "code_strategy_validate",
                    "preflight_custom_code",
                    "code_strategy_run_sandbox",
                    "code_strategy_backtest",
                    "code_strategy_analyze",
                    "code_strategy_save",
                ],
                "message": "Use agent-generated Python strategy code and code-strategy tools only.",
            },
        },
    )


def _resolve_code_strategy_runtime(paths: RuntimePaths, strategy_version_id: str) -> dict[str, Any]:
    version = sqlite_store.get_code_strategy_version(paths, strategy_version_id)
    validation = version.get("validation", {})
    if not isinstance(validation, dict) or not bool(validation.get("valid", False)):
        raise ValueError(
            f"code strategy version is not valid for runtime: strategy_version_id={strategy_version_id}; "
            "re-validate and save strategy code before activation"
        )
    runs = sqlite_store.list_backtest_runs(paths, strategy_version_id=strategy_version_id, limit=1)
    if not runs:
        raise ValueError(
            f"no backtest run found for strategy_version_id={strategy_version_id}; "
            "run /v1/code-strategy/backtest first to establish runtime universe"
        )
    latest_run = runs[0]
    payload = latest_run.get("payload", {})
    universe = payload.get("universe")
    if not isinstance(universe, list) or len(universe) == 0:
        raise ValueError(
            f"backtest payload missing universe for strategy_version_id={strategy_version_id}; "
            "rerun /v1/code-strategy/backtest with a non-empty universe"
        )
    end_date = str(payload.get("end_date", "")).strip()
    if not end_date:
        raise ValueError(
            f"backtest payload missing end_date for strategy_version_id={strategy_version_id}; "
            "rerun /v1/code-strategy/backtest with explicit date range"
        )
    return {
        "strategy_version_id": version["strategy_version_id"],
        "strategy_name": version["strategy_name"],
        "source_code": version["source_code"],
        "universe": [str(item) for item in universe],
        "end_date": end_date,
        "latest_run_id": latest_run.get("run_id"),
    }


def _read_csv_rows(path: str) -> list[dict[str, Any]]:
    csv_path = Path(path)
    if not csv_path.exists():
        raise ValueError(f"artifact not found: {path}")
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


@app.post("/v1/strategy/from-intent")
def strategy_from_intent(request: StrategyBuildRequest) -> dict[str, Any]:
    _legacy_endpoint_disabled("/v1/strategy/from-intent")
    return {}


@app.get("/v1/strategies")
def strategies_list(limit: int = Query(default=100, gt=0)) -> dict[str, Any]:
    _legacy_endpoint_disabled("/v1/strategies")
    return {}


@app.get("/v1/strategies/{strategy_id}/versions")
def strategy_versions_list(strategy_id: str, limit: int = Query(default=100, gt=0)) -> dict[str, Any]:
    _legacy_endpoint_disabled("/v1/strategies/{strategy_id}/versions")
    return {}


@app.post("/v1/world-state/build")
def world_state_build(request: WorldBuildRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        preflight = enforce_world_state_budget(
            paths,
            request.universe,
            request.start_date,
            request.end_date,
            _max_world_state_seconds(),
        )
        manifest = build_world_state_manifest(
            paths,
            request.universe,
            request.start_date,
            request.end_date,
            adjustment_policy=request.adjustment_policy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        **manifest.__dict__,
        "preflight": preflight,
    }


@app.post("/v1/world-state/completeness")
def world_state_completeness(request: WorldValidationRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        report = build_data_completeness_report(
            paths,
            request.universe,
            request.start_date,
            request.end_date,
            strict_mode=request.strict_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return report.__dict__


@app.post("/v1/world-state/validate-pit")
def world_state_validate_pit(request: WorldValidationRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        report = validate_world_state_pit(
            paths,
            request.universe,
            request.start_date,
            request.end_date,
            strict_mode=request.strict_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return report.__dict__


@app.post("/v1/preflight/world-state")
def preflight_world_state(request: PreflightWorldStateRequest) -> dict[str, float]:
    paths = _runtime_paths()
    try:
        return enforce_world_state_budget(
            paths,
            request.universe,
            request.start_date,
            request.end_date,
            request.max_allowed_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/preflight/backtest")
def preflight_backtest(request: PreflightBacktestRequest) -> dict[str, float]:
    _legacy_endpoint_disabled("/v1/preflight/backtest")
    return {}


@app.post("/v1/preflight/tuning")
def preflight_tuning(request: PreflightTuningRequest) -> dict[str, float]:
    _legacy_endpoint_disabled("/v1/preflight/tuning")
    return {}


@app.post("/v1/preflight/custom-code")
def preflight_custom_code(request: PreflightCustomCodeRequest) -> dict[str, float]:
    paths = _runtime_paths()
    try:
        return enforce_custom_code_budget(
            paths,
            universe=request.universe,
            start_date=request.start_date,
            end_date=request.end_date,
            complexity_multiplier=request.complexity_multiplier,
            max_estimated_seconds=request.max_allowed_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/universe/resolve")
def universe_resolve(symbols: list[str]) -> dict[str, Any]:
    paths = _runtime_paths()
    universe = resolve_universe(paths, symbols)
    return {"universe": universe}


@app.post("/v1/data/technicals/compute")
def technicals_compute(request: TechnicalsRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    resolved = resolve_universe(paths, request.universe)
    rows = compute_sma_features(
        paths,
        universe=resolved,
        start_date=request.start_date,
        end_date=request.end_date,
        short_window=request.short_window,
        long_window=request.long_window,
    )
    return {"rows_inserted": rows, "universe": resolved}


@app.post("/v1/screener/formula/validate")
def screener_formula_validate(request: ScreenerFormulaValidateRequest) -> dict[str, Any]:
    try:
        result = validate_formula(request.formula)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "valid": result.valid,
        "sql_expression": result.sql_expression,
        "identifiers": result.identifiers,
    }


@app.post("/v1/screener/run")
def screener_run(request: ScreenerRunRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        payload = run_formula_screen(
            runtime_paths=paths,
            formula=request.formula,
            as_of=request.as_of,
            universe=request.universe,
            top_k=request.top_k,
            rank_by=request.rank_by,
            sort_order=request.sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _append_audit_event(
        paths,
        "screener.run",
        {
            "formula": request.formula,
            "as_of": request.as_of,
            "universe_size": len(request.universe),
            "count": payload["count"],
        },
    )
    return payload


@app.post("/v1/tradingview/screener/run")
def tradingview_screener_run(request: TradingViewScanRequest) -> dict[str, Any]:
    _provider_rate_limit_or_raise("tradingview")
    try:
        payload = tradingview_integration.run_tradingview_scan(
            where=request.where,
            columns=request.columns,
            limit=request.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "provider": "tradingview",
        "payload": payload,
    }


@app.post("/v1/nse/quote")
def nse_quote(request: NseQuoteRequest) -> dict[str, Any]:
    _provider_rate_limit_or_raise("nse")
    try:
        payload = fetch_nse_equity_quote(request.symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"provider": "nse", "payload": payload}


@app.post("/v1/tuning/search-space/derive")
def tuning_search_space_derive(request: TuningSearchSpaceRequest) -> dict[str, Any]:
    _legacy_endpoint_disabled("/v1/tuning/search-space/derive")
    return {}


@app.post("/v1/tuning/run")
def tuning_run(request: TuningRunRequest) -> dict[str, Any]:
    _legacy_endpoint_disabled("/v1/tuning/run")
    return {}


@app.get("/v1/tuning/runs")
def tuning_runs_list(
    strategy_name: str | None = None,
    limit: int = Query(default=100, gt=0),
) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        runs = sqlite_store.list_tuning_runs(paths, strategy_name=strategy_name, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"runs": runs, "count": len(runs)}


@app.get("/v1/tuning/runs/{tuning_run_id}")
def tuning_run_detail(tuning_run_id: str) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        tuning = sqlite_store.get_tuning_run(paths, tuning_run_id=tuning_run_id)
        trials = sqlite_store.list_tuning_trials(paths, tuning_run_id=tuning_run_id)
        layer_decisions = sqlite_store.list_tuning_layer_decisions(paths, tuning_run_id=tuning_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        **tuning,
        "trials": trials,
        "layer_decisions": layer_decisions,
    }


@app.post("/v1/analysis/deep-dive")
def analysis_deep_dive(request: AnalysisDeepDiveRequest) -> dict[str, Any]:
    _legacy_endpoint_disabled("/v1/analysis/deep-dive")
    return {}


@app.post("/v1/visualize/trade-blotter")
def visualize_trade_blotter(request: TradeBlotterRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        run = sqlite_store.get_backtest_run(paths, request.run_id)
        artifacts = run.get("artifacts", {})
        trade_path = str(artifacts.get("trade_blotter_path", "")).strip()
        signal_path = str(artifacts.get("signal_context_path", "")).strip()
        if not trade_path or not signal_path:
            raise ValueError("run artifacts missing trade_blotter_path/signal_context_path")
        trades = _read_csv_rows(trade_path)
        signals = _read_csv_rows(signal_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    threshold_crossings = [
        row
        for row in signals
        if str(row.get("reason_code", "")).startswith("signal_")
        or str(row.get("reason_code", "")).startswith("sma_cross")
    ]
    return {
        "run_id": request.run_id,
        "artifacts": {
            "trade_blotter_path": trade_path,
            "signal_context_path": signal_path,
        },
        "trade_count": len(trades),
        "signal_rows": len(signals),
        "threshold_crossings": len(threshold_crossings),
        "trades": trades,
    }


@app.post("/v1/visualize/boundary")
def visualize_boundary(request: BoundaryVisualizationRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        runtime = _resolve_code_strategy_runtime(paths, request.strategy_version_id)
        strategy_version_id = runtime["strategy_version_id"]
        snapshot = build_live_snapshot(
            paths,
            source_code=runtime["source_code"],
            universe=runtime["universe"],
            end_date=runtime["end_date"],
        )
        candidates = select_boundary_candidates(snapshot, top_k=request.top_k)
        chart_path = write_boundary_chart(paths, strategy_version_id, candidates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "strategy_version_id": strategy_version_id,
        "boundary_chart_path": chart_path,
        "candidates": candidates,
        "similarity_method": "distance_to_signal_decision_boundary",
    }


@app.post("/v1/live/activate")
def live_activate(request: LiveActivateRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        runtime = _resolve_code_strategy_runtime(paths, request.strategy_version_id)
        strategy_version_id = runtime["strategy_version_id"]
        snapshot = build_live_snapshot(
            paths,
            source_code=runtime["source_code"],
            universe=runtime["universe"],
            end_date=runtime["end_date"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for row in snapshot:
        sqlite_store.append_live_insight(
            paths,
            strategy_version_id=strategy_version_id,
            action=str(row["action"]),
            symbol=str(row["symbol"]),
            reason_code=str(row["reason_code"]),
            score=float(row["score"]),
            payload=row,
        )
    sqlite_store.upsert_live_state(
        paths,
        strategy_version_id=strategy_version_id,
        strategy_name=runtime["strategy_name"],
        status="active",
        payload={
            "last_snapshot_size": len(snapshot),
            "universe_size": len(runtime["universe"]),
            "latest_backtest_run_id": runtime["latest_run_id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    _append_audit_event(
        paths,
        "live.activate",
        {
            "strategy_version_id": strategy_version_id,
            "insight_count": len(snapshot),
        },
    )
    return {
        "strategy_version_id": strategy_version_id,
        "status": "active",
        "insight_count": len(snapshot),
    }


@app.post("/v1/live/pause")
def live_pause(request: LiveLifecycleRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        live_state = sqlite_store.get_live_state(paths, request.strategy_version_id)
        sqlite_store.upsert_live_state(
            paths,
            strategy_version_id=request.strategy_version_id,
            strategy_name=live_state["strategy_name"],
            status="paused",
            payload={**live_state["payload"], "paused_at": datetime.now(timezone.utc).isoformat()},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"strategy_version_id": request.strategy_version_id, "status": "paused"}


@app.post("/v1/live/stop")
def live_stop(request: LiveLifecycleRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        live_state = sqlite_store.get_live_state(paths, request.strategy_version_id)
        sqlite_store.upsert_live_state(
            paths,
            strategy_version_id=request.strategy_version_id,
            strategy_name=live_state["strategy_name"],
            status="stopped",
            payload={**live_state["payload"], "stopped_at": datetime.now(timezone.utc).isoformat()},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"strategy_version_id": request.strategy_version_id, "status": "stopped"}


@app.get("/v1/live/states")
def live_states_list(status: str | None = None, limit: int = Query(default=100, gt=0)) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        states = sqlite_store.list_live_states(paths, status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"states": states, "count": len(states)}


@app.get("/v1/live/states/{strategy_version_id}")
def live_state_detail(strategy_version_id: str) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        state = sqlite_store.get_live_state(paths, strategy_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return state


@app.get("/v1/live/feed")
def live_feed(strategy_version_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        insights = sqlite_store.list_live_insights(paths, strategy_version_id=strategy_version_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"insights": insights, "count": len(insights)}


@app.get("/v1/live/boundary-candidates")
def live_boundary_candidates(strategy_version_id: str, top_k: int = 10) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        runtime = _resolve_code_strategy_runtime(paths, strategy_version_id)
        strategy_version_id = runtime["strategy_version_id"]
        snapshot = build_live_snapshot(
            paths,
            source_code=runtime["source_code"],
            universe=runtime["universe"],
            end_date=runtime["end_date"],
        )
        candidates = select_boundary_candidates(snapshot, top_k=top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "strategy_version_id": strategy_version_id,
        "candidates": candidates,
        "count": len(candidates),
        "similarity_method": "distance_to_signal_decision_boundary",
    }


@app.get("/v1/backtests/runs")
def backtest_runs_list(strategy_version_id: str | None = None, limit: int = Query(default=100, gt=0)) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        runs = sqlite_store.list_backtest_runs(
            paths,
            strategy_version_id=strategy_version_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"runs": runs, "count": len(runs)}


@app.get("/v1/backtests/runs/{run_id}")
def backtest_run_detail(run_id: str) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        run = sqlite_store.get_backtest_run(paths, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return run


def _run_backtest_job(paths: RuntimePaths, job_id: str, trace_id: str) -> None:
    sqlite_store.update_job_status(
        paths,
        job_id,
        "failed",
        error_text=(
            "legacy async backtest jobs are disabled; use code_strategy_backtest from agent tools"
        ),
    )


@app.post("/v1/backtests/run")
def backtest_run(request: BacktestRequest) -> dict[str, Any]:
    _legacy_endpoint_disabled("/v1/backtests/run")
    return {}


@app.post("/v1/backtests/run-async")
def backtest_run_async(request: BacktestRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    _legacy_endpoint_disabled("/v1/backtests/run-async")
    return {}


@app.post("/v1/backtests/compare")
def backtest_compare(request: BacktestCompareRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    try:
        report = compare_backtest_runs(
            runtime_paths=paths,
            baseline_run_id=request.baseline_run_id,
            candidate_run_id=request.candidate_run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return report


@app.post("/v1/backtests/tax/report")
def backtest_tax_report(request: BacktestTaxReportRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    sqlite_store.init_db(paths)
    try:
        run = sqlite_store.get_backtest_run(paths, request.run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not request.enabled:
        return {
            "run_id": request.run_id,
            "enabled": False,
            "message": "tax overlay disabled; set enabled=true to compute post-tax report",
        }

    artifacts = run.get("artifacts", {})
    trade_path = str(artifacts.get("trade_blotter_path", "")).strip()
    if not trade_path:
        raise HTTPException(status_code=400, detail="run artifacts missing trade_blotter_path")

    payload = run.get("payload", {})
    strategy = payload.get("strategy", {})
    if not isinstance(strategy, dict) or not strategy:
        strategy = {
            "strategy_name": payload.get("strategy_name"),
            "initial_capital": payload.get("initial_capital"),
            "max_positions": max(1, len(payload.get("universe", []))) if isinstance(payload.get("universe", []), list) else 1,
            "universe": payload.get("universe", []),
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
        }
    assumptions = IndiaTaxAssumptions(
        stcg_rate=request.stcg_rate,
        ltcg_rate=request.ltcg_rate,
        ltcg_exemption_amount=request.ltcg_exemption_amount,
        apply_cess=request.apply_cess,
        cess_rate=request.cess_rate,
        include_charges=request.include_charges,
    )
    try:
        report = compute_tax_report(trade_blotter_path=trade_path, strategy_payload=strategy, assumptions=assumptions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    report_id = sqlite_store.save_tax_report(paths, run_id=request.run_id, payload=report)
    _append_audit_event(
        paths,
        "backtest.tax.report",
        {
            "run_id": request.run_id,
            "report_id": report_id,
            "enabled": True,
            "stcg_rate": request.stcg_rate,
            "ltcg_rate": request.ltcg_rate,
            "ltcg_exemption_amount": request.ltcg_exemption_amount,
            "apply_cess": request.apply_cess,
            "cess_rate": request.cess_rate,
            "include_charges": request.include_charges,
        },
    )
    return {
        "run_id": request.run_id,
        "report_id": report_id,
        "enabled": True,
        **report,
    }


@app.get("/v1/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    paths = _runtime_paths()
    return sqlite_store.get_job(paths, job_id)


@app.post("/v1/context/delta")
def context_delta(request: ContextDeltaRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    sqlite_store.init_db(paths)
    try:
        delta_id = sqlite_store.append_tool_context_delta(
            paths,
            session_id=request.session_id,
            tool_name=request.tool_name,
            tool_input=request.tool_input,
            tool_output=request.tool_output,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"delta_id": delta_id, "session_id": request.session_id, "tool_name": request.tool_name}


@app.post("/v1/session/snapshot")
def session_snapshot(request: SessionSnapshotRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    sqlite_store.init_db(paths)
    try:
        snapshot_id = sqlite_store.save_session_state_snapshot(paths, request.session_id, request.state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"snapshot_id": snapshot_id, "session_id": request.session_id}


@app.post("/v1/session/rehydrate")
def session_rehydrate(request: SessionRehydrateRequest) -> dict[str, Any]:
    paths = _runtime_paths()
    sqlite_store.init_db(paths)
    try:
        snapshot = sqlite_store.get_latest_session_state_snapshot(paths, request.session_id)
        recent_deltas = sqlite_store.list_tool_context_deltas(paths, request.session_id, limit=20)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "session_id": request.session_id,
        "snapshot": snapshot,
        "state": snapshot["state"],
        "recent_tool_deltas": recent_deltas,
    }


@app.get("/v1/session/diff")
def session_diff(session_id: str) -> dict[str, Any]:
    paths = _runtime_paths()
    sqlite_store.init_db(paths)
    try:
        snapshots = sqlite_store.list_session_state_snapshots(paths, session_id=session_id, limit=2)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if len(snapshots) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"need at least 2 snapshots for session diff session_id={session_id}",
        )
    latest = snapshots[0]
    previous = snapshots[1]
    changes: list[dict[str, Any]] = []
    _flatten_state_diff("", previous["state"], latest["state"], changes)
    return {
        "session_id": session_id,
        "latest_snapshot_id": latest["snapshot_id"],
        "previous_snapshot_id": previous["snapshot_id"],
        "changes": changes,
        "change_count": len(changes),
    }


@app.get("/v1/providers/health")
def providers_health() -> dict[str, Any]:
    paths = _runtime_paths()
    sqlite_store.init_db(paths)
    kite_session = sqlite_store.get_connector_session(paths, connector="kite")
    kite_configured = True
    try:
        kite_integration.load_kite_config_from_env()
    except ValueError:
        kite_configured = False

    tv_configured = bool(os.environ.get("FIN_AGENT_TRADINGVIEW_SESSIONID", "").strip())
    nse_available = True
    openai_auth = opencode_auth_integration.get_openai_oauth_status()
    kite_limit = rate_limit_integration.provider_limit("kite")
    nse_limit = rate_limit_integration.provider_limit("nse")
    tv_limit = rate_limit_integration.provider_limit("tradingview")
    return {
        "providers": {
            "kite": {
                "configured": kite_configured,
                "connected": kite_session is not None,
                "rate_limit": {
                    "max_requests": kite_limit.max_requests,
                    "window_seconds": kite_limit.window_seconds,
                },
            },
            "nse": {
                "configured": nse_available,
                "connected": nse_available,
                "rate_limit": {
                    "max_requests": nse_limit.max_requests,
                    "window_seconds": nse_limit.window_seconds,
                },
            },
            "tradingview": {
                "configured": tv_configured,
                "connected": tv_configured,
                "optional": True,
                "rate_limit": {
                    "max_requests": tv_limit.max_requests,
                    "window_seconds": tv_limit.window_seconds,
                },
            },
            "opencode_openai_auth": {
                "configured": bool(openai_auth.get("connected", False)),
                "method": openai_auth.get("method"),
                "connected_methods": openai_auth.get("connected_methods", []),
            },
        }
    }


@app.get("/v1/observability/metrics")
def observability_metrics() -> dict[str, Any]:
    paths = _runtime_paths()
    sqlite_store.init_db(paths)
    stats = _read_structured_log_stats(paths)
    return {
        "metrics": stats,
        "encryption_enabled": encryption_enabled(),
    }


@app.get("/v1/diagnostics/readiness")
def diagnostics_readiness() -> dict[str, Any]:
    paths = _runtime_paths()
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "name": "runtime_paths_writable",
            "ok": paths.root.exists() and paths.artifacts_dir.exists() and paths.logs_dir.exists(),
            "remediation": "run scripts/serve.sh to initialize runtime paths",
        }
    )

    try:
        kite_integration.load_kite_config_from_env()
        kite_ok = True
    except ValueError:
        kite_ok = False
    checks.append(
        {
            "name": "kite_env_configured",
            "ok": kite_ok,
            "remediation": "set FIN_AGENT_KITE_API_KEY, FIN_AGENT_KITE_API_SECRET, FIN_AGENT_KITE_REDIRECT_URI",
        }
    )

    oauth = opencode_auth_integration.get_openai_oauth_status()
    checks.append(
        {
            "name": "opencode_openai_auth_connected",
            "ok": bool(oauth.get("connected", False)),
            "remediation": "run opencode auth login openai or set OPENAI_API_KEY",
            "details": {
                "method": oauth.get("method"),
                "connected_methods": oauth.get("connected_methods", []),
            },
        }
    )

    checks.append(
        {
            "name": "encryption_key_configured",
            "ok": encryption_enabled(),
            "remediation": "set FIN_AGENT_ENCRYPTION_KEY (Fernet key) for encrypted secret storage",
        }
    )

    ready = all(bool(row["ok"]) for row in checks)
    return {
        "ready": ready,
        "checks": checks,
    }


@app.get("/v1/audit/events")
def audit_events(event_type: str | None = None, limit: int = 100) -> dict[str, Any]:
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be positive")
    paths = _runtime_paths()
    events = sqlite_store.list_audit_events(paths, event_type=event_type)
    return {"events": events[-limit:], "count": min(len(events), limit)}


@app.get("/v1/events/jobs")
async def stream_job_events(last_event_id: int = 0) -> StreamingResponse:
    paths = _runtime_paths()

    async def event_generator() -> Any:
        current = last_event_id
        while True:
            events = sqlite_store.list_job_events_after(paths, current)
            if events:
                for event in events:
                    current = event["id"]
                    yield f"id: {event['id']}\n"
                    yield "event: job_event\n"
                    yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/v1/artifacts")
def list_artifacts() -> dict[str, Any]:
    paths = _runtime_paths()
    files = sorted(paths.artifacts_dir.rglob("*"))
    return {"artifacts": [str(file) for file in files if file.is_file()]}


@app.get("/v1/artifacts/file")
def get_artifact(path: str) -> FileResponse:
    p = Path(path).resolve()
    if not p.exists():
        raise ValueError(f"artifact not found: {path}")
    return FileResponse(str(p))
