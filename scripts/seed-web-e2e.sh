#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

API_BASE="${FIN_AGENT_API_BASE:-http://127.0.0.1:18080}"
OUTPUT_JSON=""
WORK_DIR=""
KEEP_WORK_DIR=0
DRY_RUN=0

usage() {
  cat <<'USAGE'
usage: scripts/seed-web-e2e.sh [options]

Options:
  --api-base URL        Fin-Agent API base URL (default: http://127.0.0.1:18080)
  --output-json PATH    Where to write seed summary JSON
  --work-dir DIR        Working directory for generated deterministic CSV fixtures
  --keep-work-dir       Do not delete generated work directory
  --dry-run             Print planned API calls and exit
  -h, --help            Show help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base)
      API_BASE="$2"
      shift 2
      ;;
    --output-json)
      OUTPUT_JSON="$2"
      shift 2
      ;;
    --work-dir)
      WORK_DIR="$2"
      shift 2
      ;;
    --keep-work-dir)
      KEEP_WORK_DIR=1
      shift
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
  cat <<DRY
seed web e2e dry-run
api_base=${API_BASE}
output_json=${OUTPUT_JSON:-"(work-dir/seed-summary.json)"}
calls:
  - POST /v1/data/import
  - POST /v1/data/import/fundamentals
  - POST /v1/data/import/corporate-actions
  - POST /v1/data/import/ratings
  - POST /v1/backtests/run (x2)
  - POST /v1/tuning/run
  - POST /v1/live/activate
DRY
  exit 0
fi

if [[ -z "${WORK_DIR}" ]]; then
  WORK_DIR="$(mktemp -d)"
fi
mkdir -p "${WORK_DIR}"

if [[ -z "${OUTPUT_JSON}" ]]; then
  OUTPUT_JSON="${WORK_DIR}/seed-summary.json"
fi

cleanup() {
  if [[ ${KEEP_WORK_DIR} -eq 0 ]]; then
    rm -rf "${WORK_DIR}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

DATA_DIR="${WORK_DIR}/data"
mkdir -p "${DATA_DIR}"

cat > "${DATA_DIR}/prices.csv" <<'CSV'
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

cat > "${DATA_DIR}/fundamentals.csv" <<'CSV'
symbol,published_at,pe_ratio,eps
ABC,2024-12-31T00:00:00Z,18.5,5.2
ABC,2025-01-08T00:00:00Z,19.1,5.3
CSV

cat > "${DATA_DIR}/actions.csv" <<'CSV'
symbol,effective_at,action_type,action_value
ABC,2025-01-05T00:00:00Z,dividend,2.0
CSV

cat > "${DATA_DIR}/ratings.csv" <<'CSV'
symbol,revised_at,agency,rating
ABC,2025-01-06T00:00:00Z,BankX,buy
CSV

API_BASE_ENV="${API_BASE}"
OUTPUT_JSON_ENV="${OUTPUT_JSON}"
PRICES_CSV_ENV="${DATA_DIR}/prices.csv"
FUNDAMENTALS_CSV_ENV="${DATA_DIR}/fundamentals.csv"
ACTIONS_CSV_ENV="${DATA_DIR}/actions.csv"
RATINGS_CSV_ENV="${DATA_DIR}/ratings.csv"

API_BASE="${API_BASE_ENV}" \
OUTPUT_JSON="${OUTPUT_JSON_ENV}" \
PRICES_CSV="${PRICES_CSV_ENV}" \
FUNDAMENTALS_CSV="${FUNDAMENTALS_CSV_ENV}" \
ACTIONS_CSV="${ACTIONS_CSV_ENV}" \
RATINGS_CSV="${RATINGS_CSV_ENV}" \
env -u PYTHONHOME -u PYTHONPATH python3 - <<'PY'
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = os.environ["API_BASE"].rstrip("/")
OUTPUT_JSON = Path(os.environ["OUTPUT_JSON"])
PRICES_CSV = os.environ["PRICES_CSV"]
FUNDAMENTALS_CSV = os.environ["FUNDAMENTALS_CSV"]
ACTIONS_CSV = os.environ["ACTIONS_CSV"]
RATINGS_CSV = os.environ["RATINGS_CSV"]


def call(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"content-type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=f"{API_BASE}{path}",
        method=method,
        data=data,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"api call failed path={path} status={exc.code} detail={detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"api call failed path={path} reason={exc.reason}") from exc


call("POST", "/v1/data/import", {"path": PRICES_CSV})
call("POST", "/v1/data/import/fundamentals", {"path": FUNDAMENTALS_CSV})
call("POST", "/v1/data/import/corporate-actions", {"path": ACTIONS_CSV})
call("POST", "/v1/data/import/ratings", {"path": RATINGS_CSV})

intent_a = {
    "universe": ["ABC"],
    "start_date": "2025-01-01",
    "end_date": "2025-01-10",
    "initial_capital": 100000.0,
    "short_window": 2,
    "long_window": 4,
    "max_positions": 1,
}
intent_b = {
    **intent_a,
    "short_window": 3,
    "long_window": 5,
}

run_a = call("POST", "/v1/backtests/run", {"strategy_name": "UI Seed A", "intent": intent_a})
run_b = call("POST", "/v1/backtests/run", {"strategy_name": "UI Seed B", "intent": intent_b})
tuning = call(
    "POST",
    "/v1/tuning/run",
    {
        "strategy_name": "UI Seed Tune",
        "intent": intent_a,
        "max_trials": 2,
        "per_trial_estimated_seconds": 0.01,
    },
)

strategy_version_id = str(run_b.get("strategy_version_id", "")).strip()
if not strategy_version_id:
    raise RuntimeError("seed backtest missing strategy_version_id")

call("POST", "/v1/live/activate", {"strategy_version_id": strategy_version_id})

summary = {
    "api_base": API_BASE,
    "backtest_run_ids": [run_a.get("run_id"), run_b.get("run_id")],
    "strategy_version_id": strategy_version_id,
    "live_strategy_version_id": strategy_version_id,
    "tuning_run_id": tuning.get("tuning_run_id"),
}
if not all(isinstance(x, str) and x.strip() for x in summary["backtest_run_ids"]):
    raise RuntimeError(f"seed failed: invalid backtest run ids: {summary['backtest_run_ids']}")
if not isinstance(summary["tuning_run_id"], str) or not summary["tuning_run_id"].strip():
    raise RuntimeError(f"seed failed: invalid tuning_run_id: {summary['tuning_run_id']}")

OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
print(f"seed web e2e: ok")
print(f"summary={OUTPUT_JSON}")
PY
