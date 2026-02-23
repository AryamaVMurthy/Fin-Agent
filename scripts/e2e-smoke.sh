#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

DRY_RUN=0
API_PORT="${FIN_AGENT_SMOKE_API_PORT:-18080}"
WRAPPER_PORT="${FIN_AGENT_SMOKE_WRAPPER_PORT:-18090}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --api-port)
      API_PORT="$2"
      shift 2
      ;;
    --wrapper-port)
      WRAPPER_PORT="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      echo "usage: $0 [--dry-run] [--api-port N] [--wrapper-port N]" >&2
      exit 1
      ;;
  esac
done

if [[ ${DRY_RUN} -eq 1 ]]; then
  cat <<EOF
smoke dry-run
api_port=${API_PORT}
wrapper_port=${WRAPPER_PORT}
checks:
  - GET /health
  - POST /v1/data/import
  - POST /v1/data/technicals/compute
  - POST /v1/screener/run
  - POST /v1/session/snapshot (x2)
  - GET /v1/session/diff
  - wrapper GET /health
EOF
  exit 0
fi

if lsof -i:"${API_PORT}" >/dev/null 2>&1; then
  echo "api port already in use: ${API_PORT}" >&2
  exit 1
fi
if lsof -i:"${WRAPPER_PORT}" >/dev/null 2>&1; then
  echo "wrapper port already in use: ${WRAPPER_PORT}" >&2
  exit 1
fi

if [[ ! -x .venv312/bin/python ]]; then
  echo "missing .venv312/bin/python; run ./scripts/install-linux.sh" >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "node is required for wrapper smoke test" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
API_PID=""
WRAPPER_PID=""

cleanup() {
  if [[ -n "${WRAPPER_PID}" ]]; then
    kill "${WRAPPER_PID}" >/dev/null 2>&1 || true
    wait "${WRAPPER_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${API_PID}" ]]; then
    kill "${API_PID}" >/dev/null 2>&1 || true
    wait "${API_PID}" >/dev/null 2>&1 || true
  fi
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

ENCRYPTION_KEY="$(./scripts/gen-encryption-key.sh --print)"
cat > "${TMP_DIR}/prices.csv" <<'CSV'
timestamp,symbol,open,high,low,close,volume
2026-02-17T00:00:00Z,INFY,100,102,99,101,100000
2026-02-18T00:00:00Z,INFY,101,104,100,103,110000
2026-02-19T00:00:00Z,INFY,103,105,102,104,120000
2026-02-17T00:00:00Z,TCS,200,202,198,199,80000
2026-02-18T00:00:00Z,TCS,199,201,197,198,85000
2026-02-19T00:00:00Z,TCS,198,200,196,197,90000
CSV

FIN_AGENT_HOME="${TMP_DIR}/.finagent" \
FIN_AGENT_ENCRYPTION_KEY="${ENCRYPTION_KEY}" \
env -u PYTHONHOME -u PYTHONPATH PYTHONPATH="${ROOT_DIR}/py" \
  .venv312/bin/python -m uvicorn fin_agent.api.app:app --host 127.0.0.1 --port "${API_PORT}" >"${TMP_DIR}/api.log" 2>&1 &
API_PID="$!"

FIN_AGENT_API="http://127.0.0.1:${API_PORT}" \
PORT="${WRAPPER_PORT}" \
node apps/fin-agent/src/index.mjs >"${TMP_DIR}/wrapper.log" 2>&1 &
WRAPPER_PID="$!"

sleep 2

curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null
curl -fsS "http://127.0.0.1:${WRAPPER_PORT}/health" >/dev/null

curl -fsS -X POST "http://127.0.0.1:${API_PORT}/v1/data/import" \
  -H "content-type: application/json" \
  -d "{\"path\":\"${TMP_DIR}/prices.csv\"}" >/dev/null

curl -fsS -X POST "http://127.0.0.1:${API_PORT}/v1/data/technicals/compute" \
  -H "content-type: application/json" \
  -d '{"universe":["INFY","TCS"],"start_date":"2026-02-17","end_date":"2026-02-19","short_window":2,"long_window":3}' >/dev/null

curl -fsS -X POST "http://127.0.0.1:${API_PORT}/v1/screener/run" \
  -H "content-type: application/json" \
  -d '{"formula":"volume > 50000 and return_1d_pct > -1000","as_of":"2026-02-19","universe":["INFY","TCS"],"rank_by":"return_1d_pct","sort_order":"desc"}' >/dev/null

curl -fsS -X POST "http://127.0.0.1:${API_PORT}/v1/session/snapshot" \
  -H "content-type: application/json" \
  -d '{"session_id":"smoke","state":{"a":1}}' >/dev/null
curl -fsS -X POST "http://127.0.0.1:${API_PORT}/v1/session/snapshot" \
  -H "content-type: application/json" \
  -d '{"session_id":"smoke","state":{"a":2}}' >/dev/null
curl -fsS "http://127.0.0.1:${API_PORT}/v1/session/diff?session_id=smoke" >/dev/null

echo "smoke: ok"
echo "api_log=${TMP_DIR}/api.log"
echo "wrapper_log=${TMP_DIR}/wrapper.log"
