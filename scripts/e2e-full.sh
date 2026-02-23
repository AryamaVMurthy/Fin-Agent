#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

API_PORT="${FIN_AGENT_E2E_API_PORT:-18080}"
WRAPPER_PORT="${FIN_AGENT_E2E_WRAPPER_PORT:-18090}"
OPENCODE_HOST="${OPENCODE_HOSTNAME:-127.0.0.1}"
OPENCODE_PORT_VALUE="${OPENCODE_PORT:-4096}"
OPENCODE_BASE="http://${OPENCODE_HOST}:${OPENCODE_PORT_VALUE}"
WITH_PROVIDERS=0
WITH_OPENCODE=0
WITH_WEB_VISUAL=0
WITH_WEB_PLAYWRIGHT=0
REQUIRE_DOCTOR=1
DRY_RUN=0
OUTPUT_DIR=""
RUNTIME_HOME=""

usage() {
  cat <<'EOF'
usage: scripts/e2e-full.sh [options]

Options:
  --api-port N           API port (default: 18080)
  --wrapper-port N       Wrapper port (default: 18090)
  --with-providers       Run strict live provider checks (Kite/NSE; TradingView if configured)
  --with-opencode        Run strict OpenCode auth checks
  --with-web-playwright  Run full Playwright interaction web UI checks
  --with-web-visual      Run Playwright visual web UI checks
  --skip-doctor          Skip scripts/doctor.sh gate
  --output-dir DIR       Output directory for logs/artifacts
  --runtime-home DIR     FIN_AGENT_HOME to use for runtime state (default: OUTPUT_DIR/runtime)
  --dry-run              Print planned gates and exit
  -h, --help             Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-port)
      API_PORT="$2"
      shift 2
      ;;
    --wrapper-port)
      WRAPPER_PORT="$2"
      shift 2
      ;;
    --with-providers)
      WITH_PROVIDERS=1
      shift
      ;;
    --with-opencode)
      WITH_OPENCODE=1
      shift
      ;;
    --with-web-playwright)
      WITH_WEB_PLAYWRIGHT=1
      shift
      ;;
    --with-web-visual)
      WITH_WEB_VISUAL=1
      shift
      ;;
    --skip-doctor)
      REQUIRE_DOCTOR=0
      shift
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --runtime-home)
      RUNTIME_HOME="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ${DRY_RUN} -eq 1 ]]; then
  cat <<EOF
rigorous e2e dry-run
api_port=${API_PORT}
wrapper_port=${WRAPPER_PORT}
opencode_base=${OPENCODE_BASE}
with_providers=${WITH_PROVIDERS}
with_opencode=${WITH_OPENCODE}
with_web_playwright=${WITH_WEB_PLAYWRIGHT}
with_web_visual=${WITH_WEB_VISUAL}
require_doctor=${REQUIRE_DOCTOR}
runtime_home=${RUNTIME_HOME:-"(output_dir/runtime)"}
gates:
  - service startup + health parity
  - deterministic data imports + intent/strategy/world-state
  - backtest compare + tuning derive/run + analysis
  - code strategy lane + visualizations + live lifecycle
  - tax + session memory + diagnostics/observability
  - wrapper parity checks
  - optional strict providers gate
  - optional strict opencode gate
  - optional strict playwright interaction gate
  - optional playwright web visual gate
  - artifact summary and step logs
EOF
  exit 0
fi

if [[ ! -x .venv312/bin/python ]]; then
  echo "missing .venv312/bin/python; run ./scripts/install-linux.sh" >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "node is required" >&2
  exit 1
fi

if [[ ${REQUIRE_DOCTOR} -eq 1 ]]; then
  ./scripts/doctor.sh
fi

if [[ -z "${OUTPUT_DIR}" ]]; then
  RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
  OUTPUT_DIR="${ROOT_DIR}/.finagent/verification/rigorous-${RUN_TS}"
fi

if [[ -z "${RUNTIME_HOME}" ]]; then
  RUNTIME_HOME="${OUTPUT_DIR}/runtime"
fi

mkdir -p "${OUTPUT_DIR}/logs" "${OUTPUT_DIR}/artifacts/http" "${OUTPUT_DIR}/data" "${RUNTIME_HOME}"
RUNTIME_HOME="$(cd "${RUNTIME_HOME}" && pwd)"

if [[ -f .env.local ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.local
  set +a
fi

ENCRYPTION_KEY="${FIN_AGENT_ENCRYPTION_KEY:-}"
if [[ -z "${ENCRYPTION_KEY}" ]]; then
  ENCRYPTION_KEY="$(./scripts/gen-encryption-key.sh --print)"
fi

cat > "${OUTPUT_DIR}/data/prices.csv" <<'CSV'
timestamp,symbol,open,high,low,close,volume
2025-01-01T00:00:00Z,ABC,100,101,99,100,1000
2025-01-02T00:00:00Z,ABC,100,102,99,101,1100
2025-01-03T00:00:00Z,ABC,101,104,100,103,1200
2025-01-04T00:00:00Z,ABC,103,105,102,104,1200
2025-01-05T00:00:00Z,ABC,104,106,103,105,1300
2025-01-06T00:00:00Z,ABC,105,107,104,106,1300
2025-01-07T00:00:00Z,ABC,106,106,100,101,1400
2025-01-08T00:00:00Z,ABC,101,103,99,100,1400
2025-01-09T00:00:00Z,ABC,100,102,98,99,1500
2025-01-10T00:00:00Z,ABC,99,101,97,98,1500
CSV

cat > "${OUTPUT_DIR}/data/fundamentals.csv" <<'CSV'
symbol,published_at,pe_ratio,eps
ABC,2024-12-31T00:00:00Z,18.5,5.2
ABC,2025-01-08T00:00:00Z,19.1,5.3
CSV

cat > "${OUTPUT_DIR}/data/actions.csv" <<'CSV'
symbol,effective_at,action_type,action_value
ABC,2025-01-05T00:00:00Z,dividend,2.0
CSV

cat > "${OUTPUT_DIR}/data/ratings.csv" <<'CSV'
symbol,revised_at,agency,rating
ABC,2025-01-06T00:00:00Z,BankX,buy
CSV

API_PID=""
WRAPPER_PID=""
OPENCODE_PID=""

cleanup() {
  if [[ -n "${WRAPPER_PID}" ]]; then
    kill "${WRAPPER_PID}" >/dev/null 2>&1 || true
    wait "${WRAPPER_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${API_PID}" ]]; then
    kill "${API_PID}" >/dev/null 2>&1 || true
    wait "${API_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${OPENCODE_PID}" ]]; then
    kill "${OPENCODE_PID}" >/dev/null 2>&1 || true
    wait "${OPENCODE_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ ${WITH_OPENCODE} -eq 1 || ${WITH_WEB_PLAYWRIGHT} -eq 1 ]]; then
  if curl -fsS "${OPENCODE_BASE}/global/health" >/dev/null 2>&1; then
    echo "reusing existing opencode server at ${OPENCODE_BASE}"
  else
    OPENCODE_HOSTNAME="${OPENCODE_HOST}" \
      OPENCODE_PORT="${OPENCODE_PORT_VALUE}" \
      bash scripts/opencode-serve.sh >"${OUTPUT_DIR}/logs/opencode.log" 2>&1 &
    OPENCODE_PID=$!
    for _ in $(seq 1 200); do
      if curl -fsS "${OPENCODE_BASE}/global/health" >/dev/null 2>&1; then
        break
      fi
      sleep 0.1
    done
    if ! curl -fsS "${OPENCODE_BASE}/global/health" >/dev/null 2>&1; then
      echo "opencode health check failed at ${OPENCODE_BASE}/global/health" >&2
      exit 1
    fi
  fi
fi

env -u PYTHONHOME -u PYTHONPATH \
  PYTHONPATH="${ROOT_DIR}/py" \
  FIN_AGENT_HOME="${RUNTIME_HOME}" \
  FIN_AGENT_ENCRYPTION_KEY="${ENCRYPTION_KEY}" \
  .venv312/bin/python -m uvicorn fin_agent.api.app:app --host 127.0.0.1 --port "${API_PORT}" \
  >"${OUTPUT_DIR}/logs/api.log" 2>&1 &
API_PID=$!

FIN_AGENT_API="http://127.0.0.1:${API_PORT}" \
  OPENCODE_API="${OPENCODE_BASE}" \
  PORT="${WRAPPER_PORT}" \
  node apps/fin-agent/src/index.mjs >"${OUTPUT_DIR}/logs/wrapper.log" 2>&1 &
WRAPPER_PID=$!

for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 && \
     curl -fsS "http://127.0.0.1:${WRAPPER_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done

env -u PYTHONHOME -u PYTHONPATH \
  PYTHONPATH="${ROOT_DIR}/py" \
  E2E_API_BASE="http://127.0.0.1:${API_PORT}" \
  E2E_WRAPPER_BASE="http://127.0.0.1:${WRAPPER_PORT}" \
  E2E_OUTPUT_DIR="${OUTPUT_DIR}" \
  E2E_RUNTIME_DIR="${RUNTIME_HOME}" \
  E2E_WITH_PROVIDERS="${WITH_PROVIDERS}" \
  E2E_WITH_OPENCODE="${WITH_OPENCODE}" \
  .venv312/bin/python - <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
from fin_agent.verification.ui_dashboard import generate_rigorous_ui_dashboard


API_BASE = os.environ["E2E_API_BASE"]
WRAPPER_BASE = os.environ["E2E_WRAPPER_BASE"]
OUTPUT_DIR = Path(os.environ["E2E_OUTPUT_DIR"])
WITH_PROVIDERS = os.environ.get("E2E_WITH_PROVIDERS", "0") == "1"
WITH_OPENCODE = os.environ.get("E2E_WITH_OPENCODE", "0") == "1"
HTTP_DIR = OUTPUT_DIR / "artifacts" / "http"
DATA_DIR = OUTPUT_DIR / "data"
RUNTIME_DIR = OUTPUT_DIR / "runtime"
if "E2E_RUNTIME_DIR" in os.environ:
    RUNTIME_DIR = Path(os.environ["E2E_RUNTIME_DIR"])


@dataclass
class StepResult:
    name: str
    status: str
    duration_ms: float
    detail: str


steps: list[StepResult] = []
step_counter = 0


def _dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _http_json(method: str, base_url: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    url = f"{base_url}{path}"
    body = None
    headers = {"content-type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, method=method, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            status = int(response.getcode())
            data = json.loads(response.read().decode("utf-8"))
            return status, data
    except urllib.error.HTTPError as exc:
        detail_text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail_text)
        except json.JSONDecodeError:
            parsed = {"detail": detail_text}
        return int(exc.code), parsed
    except urllib.error.URLError as exc:
        return 0, {"detail": str(exc.reason)}


def _query_params(params: dict[str, Any]) -> str:
    query: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        query[key] = str(value)
    if not query:
        return ""
    return "?" + urllib.parse.urlencode(query)


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise RuntimeError(message)


def call(
    step_name: str,
    *,
    method: str,
    base_url: str,
    path: str,
    payload: dict[str, Any] | None = None,
    expect_status: int = 200,
) -> dict[str, Any]:
    global step_counter
    step_counter += 1
    started = time.perf_counter()
    status, data = _http_json(method, base_url, path, payload)
    duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
    _dump_json(
        HTTP_DIR / f"{step_counter:03d}-{step_name}.json",
        {
            "step_name": step_name,
            "method": method,
            "base_url": base_url,
            "path": path,
            "payload": payload,
            "status": status,
            "response": data,
            "duration_ms": duration_ms,
        },
    )
    if status != expect_status:
        raise RuntimeError(f"{step_name} failed status={status} expected={expect_status} detail={data}")
    return data


def run_step(name: str, fn) -> None:  # type: ignore[no-untyped-def]
    started = time.perf_counter()
    try:
        fn()
        duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
        steps.append(StepResult(name=name, status="passed", duration_ms=duration_ms, detail="ok"))
    except Exception as exc:  # noqa: BLE001
        duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
        steps.append(StepResult(name=name, status="failed", duration_ms=duration_ms, detail=str(exc)))
        raise


context: dict[str, Any] = {}


def core_flow() -> None:
    health_api = call("api-health", method="GET", base_url=API_BASE, path="/health")
    _assert(str(health_api.get("status", "")).lower() == "ok", f"api health payload unexpected: {health_api}")

    health_wrapper = call("wrapper-health", method="GET", base_url=WRAPPER_BASE, path="/health")
    _assert(health_wrapper == health_api, "wrapper /health parity mismatch")

    call(
        "import-ohlcv",
        method="POST",
        base_url=API_BASE,
        path="/v1/data/import",
        payload={"path": str(DATA_DIR / "prices.csv")},
    )
    import_fundamentals = call(
        "import-fundamentals",
        method="POST",
        base_url=API_BASE,
        path="/v1/data/import/fundamentals",
        payload={"path": str(DATA_DIR / "fundamentals.csv")},
    )
    _assert(int(import_fundamentals["rows_inserted"]) == 2, "fundamentals rows_inserted expected 2")
    call(
        "import-corporate-actions",
        method="POST",
        base_url=API_BASE,
        path="/v1/data/import/corporate-actions",
        payload={"path": str(DATA_DIR / "actions.csv")},
    )
    call(
        "import-ratings",
        method="POST",
        base_url=API_BASE,
        path="/v1/data/import/ratings",
        payload={"path": str(DATA_DIR / "ratings.csv")},
    )

    propose = call(
        "brainstorm-propose",
        method="POST",
        base_url=API_BASE,
        path="/v1/brainstorm/agent-decides/propose",
        payload={"universe": ["ABC"], "start_date": "2025-01-01", "end_date": "2025-01-10"},
    )
    context["intent"] = propose["proposed_intent"]
    confirm = call(
        "brainstorm-confirm",
        method="POST",
        base_url=API_BASE,
        path="/v1/brainstorm/agent-decides/confirm",
        payload={
            "intent": context["intent"],
            "decision_card": propose["decision_card"],
        },
    )
    context["intent_snapshot_id"] = confirm["intent_snapshot_id"]

    strategy = call(
        "strategy-from-intent",
        method="POST",
        base_url=API_BASE,
        path="/v1/strategy/from-intent",
        payload={"strategy_name": "Rigorous Base", "intent_snapshot_id": context["intent_snapshot_id"]},
    )
    context["strategy_version_id"] = strategy["strategy_version_id"]

    completeness = call(
        "world-completeness",
        method="POST",
        base_url=API_BASE,
        path="/v1/world-state/completeness",
        payload={
            "universe": ["ABC"],
            "start_date": "2025-01-01",
            "end_date": "2025-01-10",
            "strict_mode": False,
        },
    )
    _assert("skipped_features" in completeness, "world completeness missing expected keys")
    pit = call(
        "world-validate-pit",
        method="POST",
        base_url=API_BASE,
        path="/v1/world-state/validate-pit",
        payload={
            "universe": ["ABC"],
            "start_date": "2025-01-01",
            "end_date": "2025-01-10",
            "strict_mode": True,
        },
    )
    _assert(bool(pit.get("valid", False)), f"pit validation failed: {pit}")

    call(
        "preflight-backtest",
        method="POST",
        base_url=API_BASE,
        path="/v1/preflight/backtest",
        payload={
            "strategy_name": "Rigorous A",
            "intent_snapshot_id": context["intent_snapshot_id"],
            "max_allowed_seconds": 120.0,
        },
    )

    run_one = call(
        "backtest-run-a",
        method="POST",
        base_url=API_BASE,
        path="/v1/backtests/run",
        payload={
            "strategy_name": "Rigorous A",
            "intent": {**context["intent"], "short_window": 2, "long_window": 4, "max_positions": 1},
        },
    )
    run_two = call(
        "backtest-run-b",
        method="POST",
        base_url=API_BASE,
        path="/v1/backtests/run",
        payload={
            "strategy_name": "Rigorous B",
            "intent": {**context["intent"], "short_window": 3, "long_window": 5, "max_positions": 1},
        },
    )
    context["run_one_id"] = run_one["run_id"]
    context["run_two_id"] = run_two["run_id"]
    context["strategy_version_id"] = run_two["strategy_version_id"]

    compare = call(
        "backtest-compare",
        method="POST",
        base_url=API_BASE,
        path="/v1/backtests/compare",
        payload={"baseline_run_id": context["run_one_id"], "candidate_run_id": context["run_two_id"]},
    )
    _assert("metrics_delta" in compare, "compare response missing metrics_delta")

    call(
        "preflight-tuning",
        method="POST",
        base_url=API_BASE,
        path="/v1/preflight/tuning",
        payload={"num_trials": 6, "per_trial_estimated_seconds": 0.5, "max_allowed_seconds": 120.0},
    )

    tuning_space = call(
        "tuning-derive",
        method="POST",
        base_url=API_BASE,
        path="/v1/tuning/search-space/derive",
        payload={
            "strategy_name": "Rigorous Tune",
            "intent": {**context["intent"], "short_window": 2, "long_window": 4, "max_positions": 1},
            "optimization_target": "sharpe",
            "risk_mode": "balanced",
            "policy_mode": "user_selected",
            "include_layers": ["signal", "execution"],
        },
    )
    _assert("tuning_plan" in tuning_space and "graph" in tuning_space["tuning_plan"], "tuning derive missing plan graph")

    tuning_run = call(
        "tuning-run",
        method="POST",
        base_url=API_BASE,
        path="/v1/tuning/run",
        payload={
            "strategy_name": "Rigorous Tune",
            "intent": {**context["intent"], "short_window": 2, "long_window": 4, "max_positions": 1},
            "optimization_target": "sharpe",
            "risk_mode": "balanced",
            "policy_mode": "user_selected",
            "include_layers": ["signal", "execution"],
            "max_trials": 6,
        },
    )
    _assert("sensitivity_analysis" in tuning_run, "tuning run missing sensitivity_analysis")

    call(
        "analysis-deep-dive",
        method="POST",
        base_url=API_BASE,
        path="/v1/analysis/deep-dive",
        payload={"run_id": context["run_two_id"]},
    )
    blotter = call(
        "visualize-trade-blotter",
        method="POST",
        base_url=API_BASE,
        path="/v1/visualize/trade-blotter",
        payload={"run_id": context["run_two_id"]},
    )
    _assert(int(blotter.get("trade_count", 0)) >= 0, "trade blotter response invalid")

    activate = call(
        "live-activate",
        method="POST",
        base_url=API_BASE,
        path="/v1/live/activate",
        payload={"strategy_version_id": context["strategy_version_id"]},
    )
    _assert(str(activate.get("status")) == "active", "live activate did not return active status")

    feed = call(
        "live-feed",
        method="GET",
        base_url=API_BASE,
        path="/v1/live/feed" + _query_params({"strategy_version_id": context["strategy_version_id"], "limit": 20}),
    )
    _assert(int(feed.get("count", 0)) >= 1, "live feed expected at least one insight")

    call(
        "live-boundary-candidates",
        method="GET",
        base_url=API_BASE,
        path="/v1/live/boundary-candidates"
        + _query_params({"strategy_version_id": context["strategy_version_id"], "top_k": 5}),
    )
    boundary = call(
        "visualize-boundary",
        method="POST",
        base_url=API_BASE,
        path="/v1/visualize/boundary",
        payload={"strategy_version_id": context["strategy_version_id"], "top_k": 5},
    )
    chart_path = Path(str(boundary.get("boundary_chart_path", "")))
    _assert(chart_path.exists(), f"boundary chart artifact missing at {chart_path}")

    pause = call(
        "live-pause",
        method="POST",
        base_url=API_BASE,
        path="/v1/live/pause",
        payload={"strategy_version_id": context["strategy_version_id"]},
    )
    _assert(str(pause.get("status")) == "paused", "live pause failed")
    stop = call(
        "live-stop",
        method="POST",
        base_url=API_BASE,
        path="/v1/live/stop",
        payload={"strategy_version_id": context["strategy_version_id"]},
    )
    _assert(str(stop.get("status")) == "stopped", "live stop failed")

    strategy_code = """
def prepare(data_bundle, context):
    return {"ok": True}

def generate_signals(frame, state, context):
    return [{"symbol": "ABC", "signal": "buy"}]

def risk_rules(positions, context):
    return {"max_positions": 1}
"""
    validation = call(
        "code-validate",
        method="POST",
        base_url=API_BASE,
        path="/v1/code-strategy/validate",
        payload={"strategy_name": "Rigorous Code", "source_code": strategy_code},
    )
    _assert(bool(validation["validation"]["valid"]), "code strategy validation expected valid=true")
    call(
        "code-save",
        method="POST",
        base_url=API_BASE,
        path="/v1/code-strategy/save",
        payload={"strategy_name": "Rigorous Code", "source_code": strategy_code},
    )
    sandbox = call(
        "code-sandbox",
        method="POST",
        base_url=API_BASE,
        path="/v1/code-strategy/run-sandbox",
        payload={"source_code": strategy_code, "timeout_seconds": 3, "memory_mb": 128, "cpu_seconds": 1},
    )
    _assert(str(sandbox.get("status")) == "completed", "sandbox run expected completed status")
    code_backtest = call(
        "code-backtest",
        method="POST",
        base_url=API_BASE,
        path="/v1/code-strategy/backtest",
        payload={
            "strategy_name": "Rigorous Code",
            "source_code": strategy_code,
            "universe": ["ABC"],
            "start_date": "2025-01-01",
            "end_date": "2025-01-10",
            "initial_capital": 100000.0,
        },
    )
    call(
        "code-analyze",
        method="POST",
        base_url=API_BASE,
        path="/v1/code-strategy/analyze",
        payload={"run_id": code_backtest["run_id"], "source_code": strategy_code},
    )

    tax = call(
        "backtest-tax-report",
        method="POST",
        base_url=API_BASE,
        path="/v1/backtests/tax/report",
        payload={"run_id": context["run_two_id"], "enabled": True},
    )
    _assert(bool(tax.get("enabled", False)), "tax report expected enabled=true")

    call(
        "context-delta",
        method="POST",
        base_url=API_BASE,
        path="/v1/context/delta",
        payload={
            "session_id": "rigorous",
            "tool_name": "manual.check",
            "tool_input": {"k": 1},
            "tool_output": {"v": 2},
        },
    )
    call(
        "session-snapshot-1",
        method="POST",
        base_url=API_BASE,
        path="/v1/session/snapshot",
        payload={"session_id": "rigorous", "state": {"phase": 1}},
    )
    call(
        "session-snapshot-2",
        method="POST",
        base_url=API_BASE,
        path="/v1/session/snapshot",
        payload={"session_id": "rigorous", "state": {"phase": 2, "done": True}},
    )
    diff = call(
        "session-diff",
        method="GET",
        base_url=API_BASE,
        path="/v1/session/diff" + _query_params({"session_id": "rigorous"}),
    )
    _assert(int(diff.get("change_count", 0)) >= 1, "session diff expected at least one change")
    rehydrate = call(
        "session-rehydrate",
        method="POST",
        base_url=API_BASE,
        path="/v1/session/rehydrate",
        payload={"session_id": "rigorous"},
    )
    _assert("state" in rehydrate, "session rehydrate missing state")

    providers = call("providers-health", method="GET", base_url=API_BASE, path="/v1/providers/health")
    diagnostics = call("diagnostics-readiness", method="GET", base_url=API_BASE, path="/v1/diagnostics/readiness")
    observability = call("observability-metrics", method="GET", base_url=API_BASE, path="/v1/observability/metrics")
    _assert("providers" in providers, "providers health response invalid")
    _assert("checks" in diagnostics, "diagnostics response invalid")
    _assert("metrics" in observability, "observability response invalid")

    providers_wrapper = call(
        "providers-health-wrapper",
        method="GET",
        base_url=WRAPPER_BASE,
        path="/v1/providers/health",
    )
    _assert(providers_wrapper == providers, "wrapper providers health parity mismatch")

    universe_api = call(
        "universe-resolve-api",
        method="POST",
        base_url=API_BASE,
        path="/v1/universe/resolve",
        payload=["ABC"],
    )
    universe_wrapper = call(
        "universe-resolve-wrapper",
        method="POST",
        base_url=WRAPPER_BASE,
        path="/v1/universe/resolve",
        payload=["ABC"],
    )
    _assert(universe_wrapper == universe_api, "wrapper universe resolve parity mismatch")


def provider_flow() -> None:
    kite_status = call("kite-status", method="GET", base_url=API_BASE, path="/v1/auth/kite/status")
    _assert(bool(kite_status.get("configured")), f"kite not configured: {kite_status}")
    _assert(bool(kite_status.get("connected")), f"kite not connected: {kite_status}")

    call("kite-profile", method="GET", base_url=API_BASE, path="/v1/kite/profile")
    call("kite-holdings", method="GET", base_url=API_BASE, path="/v1/kite/holdings")
    call(
        "kite-instruments-sync",
        method="POST",
        base_url=API_BASE,
        path="/v1/kite/instruments/sync",
        payload={"exchange": "NSE", "max_rows": 1000},
    )

    db_path = RUNTIME_DIR / "analytics.duckdb"
    _assert(db_path.exists(), f"market db missing after instruments sync: {db_path}")
    with duckdb.connect(str(db_path)) as conn:
        row = conn.execute(
            """
            SELECT instrument_token, exchange, tradingsymbol
            FROM market_instruments
            WHERE exchange = 'NSE'
            ORDER BY tradingsymbol ASC
            LIMIT 1
            """
        ).fetchone()
    _assert(row is not None, "no NSE instrument row available after sync")
    instrument_token, exchange, tradingsymbol = row
    now_utc = datetime.now(timezone.utc)
    from_ts = (now_utc - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    to_ts = now_utc.strftime("%Y-%m-%d %H:%M:%S")
    candles_1 = call(
        "kite-candles-fetch",
        method="POST",
        base_url=API_BASE,
        path="/v1/kite/candles/fetch",
        payload={
            "symbol": str(tradingsymbol),
            "instrument_token": str(instrument_token),
            "interval": "day",
            "from_ts": from_ts,
            "to_ts": to_ts,
            "persist": True,
            "use_cache": True,
            "force_refresh": False,
        },
    )
    _assert(int(candles_1.get("rows", 0)) >= 0, f"unexpected candles response: {candles_1}")

    candles_2 = call(
        "kite-candles-cache-hit",
        method="POST",
        base_url=API_BASE,
        path="/v1/kite/candles/fetch",
        payload={
            "symbol": str(tradingsymbol),
            "instrument_token": str(instrument_token),
            "interval": "day",
            "from_ts": from_ts,
            "to_ts": to_ts,
            "persist": True,
            "use_cache": True,
            "force_refresh": False,
        },
    )
    _assert(bool(candles_2.get("cache_hit")), "expected second candle fetch to hit cache")

    quote_key = f"{exchange}:{tradingsymbol}"
    quotes = call(
        "kite-quotes-fetch",
        method="POST",
        base_url=API_BASE,
        path="/v1/kite/quotes/fetch",
        payload={"instruments": [quote_key], "persist": True},
    )
    _assert(int(quotes.get("received", 0)) >= 1, f"expected at least one quote for {quote_key}")

    call(
        "nse-quote",
        method="POST",
        base_url=API_BASE,
        path="/v1/nse/quote",
        payload={"symbol": str(tradingsymbol)},
    )

    providers = call("providers-health-live-check", method="GET", base_url=API_BASE, path="/v1/providers/health")
    tv = providers["providers"]["tradingview"]
    if tv.get("configured"):
        call(
            "tradingview-screener-run",
            method="POST",
            base_url=API_BASE,
            path="/v1/tradingview/screener/run",
            payload={"limit": 5},
        )


def opencode_flow() -> None:
    if subprocess.run(["bash", "-lc", "command -v opencode >/dev/null 2>&1"]).returncode != 0:
        raise RuntimeError("opencode binary not found in PATH")
    proc = subprocess.run(["opencode", "auth", "list"], check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"opencode auth list failed: {proc.stderr.strip() or proc.stdout.strip()}")
    listing = (proc.stdout or "") + "\n" + (proc.stderr or "")
    low = listing.lower()
    if "openai" not in low or ("oauth" not in low and "api" not in low):
        raise RuntimeError(f"opencode auth missing openai oauth/api entry: {listing}")

    status = call(
        "opencode-oauth-status",
        method="GET",
        base_url=API_BASE,
        path="/v1/auth/opencode/openai/oauth/status",
    )
    if not bool(status.get("connected")):
        raise RuntimeError(f"OpenCode OAuth not connected according to API status: {status}")

    chat_health = call(
        "wrapper-chat-health",
        method="GET",
        base_url=WRAPPER_BASE,
        path="/v1/chat/health",
    )
    _assert(bool(chat_health.get("healthy")), f"wrapper chat health unexpected payload: {chat_health}")

    sessions = call(
        "wrapper-chat-sessions",
        method="GET",
        base_url=WRAPPER_BASE,
        path="/v1/chat/sessions",
    )
    _assert("sessions" in sessions, f"wrapper chat sessions missing sessions key: {sessions}")


try:
    run_step("core-deterministic-flow", core_flow)
    if WITH_PROVIDERS:
        run_step("provider-live-flow", provider_flow)
    else:
        steps.append(StepResult(name="provider-live-flow", status="skipped", duration_ms=0.0, detail="enable --with-providers"))

    if WITH_OPENCODE:
        run_step("opencode-flow", opencode_flow)
    else:
        steps.append(StepResult(name="opencode-flow", status="skipped", duration_ms=0.0, detail="enable --with-opencode"))

    summary = {
        "status": "passed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_base": API_BASE,
        "wrapper_base": WRAPPER_BASE,
        "with_providers": WITH_PROVIDERS,
        "with_opencode": WITH_OPENCODE,
        "step_count": len(steps),
        "steps": [step.__dict__ for step in steps],
    }
    _dump_json(OUTPUT_DIR / "artifacts" / "summary.json", summary)
    with (OUTPUT_DIR / "artifacts" / "steps.jsonl").open("w", encoding="utf-8") as handle:
        for step in steps:
            handle.write(json.dumps(step.__dict__, sort_keys=True) + "\n")
    ui_payload = generate_rigorous_ui_dashboard(run_dir=OUTPUT_DIR, workspace_root=Path.cwd())
    print(f"rigorous e2e: passed")
    print(f"summary={OUTPUT_DIR / 'artifacts' / 'summary.json'}")
    print(f"ui_dashboard={ui_payload['paths']['dashboard']}")
except Exception as exc:  # noqa: BLE001
    summary = {
        "status": "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_base": API_BASE,
        "wrapper_base": WRAPPER_BASE,
        "with_providers": WITH_PROVIDERS,
        "with_opencode": WITH_OPENCODE,
        "failure": str(exc),
        "step_count": len(steps),
        "steps": [step.__dict__ for step in steps],
        "remediation": "inspect artifacts/http and logs/api.log/logs/wrapper.log, fix failing gate, rerun e2e-full.sh",
    }
    _dump_json(OUTPUT_DIR / "artifacts" / "summary.json", summary)
    with (OUTPUT_DIR / "artifacts" / "steps.jsonl").open("w", encoding="utf-8") as handle:
        for step in steps:
            handle.write(json.dumps(step.__dict__, sort_keys=True) + "\n")
    print(f"rigorous e2e: failed: {exc}")
    print(f"summary={OUTPUT_DIR / 'artifacts' / 'summary.json'}")
    raise
PY

echo "rigorous e2e output dir: ${OUTPUT_DIR}"
echo "api log: ${OUTPUT_DIR}/logs/api.log"
echo "wrapper log: ${OUTPUT_DIR}/logs/wrapper.log"
if [[ -f "${OUTPUT_DIR}/logs/opencode.log" ]]; then
  echo "opencode log: ${OUTPUT_DIR}/logs/opencode.log"
fi
echo "summary: ${OUTPUT_DIR}/artifacts/summary.json"

if [[ ${WITH_WEB_PLAYWRIGHT} -eq 1 ]]; then
  bash scripts/e2e-web-playwright.sh \
    --api-base "http://127.0.0.1:${API_PORT}" \
    --url "http://127.0.0.1:${WRAPPER_PORT}" \
    --output-dir "${OUTPUT_DIR}/artifacts/web-playwright"
fi

if [[ ${WITH_WEB_VISUAL} -eq 1 ]]; then
  bash scripts/e2e-web-visual.sh \
    --url "http://127.0.0.1:${WRAPPER_PORT}/app" \
    --output-dir "${OUTPUT_DIR}/artifacts/web-visual"
fi
