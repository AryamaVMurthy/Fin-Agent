#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

URL="${FIN_AGENT_WEB_URL:-http://127.0.0.1:18090}"
API_BASE="${FIN_AGENT_API_BASE:-http://127.0.0.1:18080}"
OUTPUT_DIR=""
SEED=1
CHAT_WARMUP=0
DRY_RUN=0
WEB_APP_DIR="${ROOT_DIR}/apps/fin-agent-web"

usage() {
  cat <<'USAGE'
usage: scripts/e2e-web-playwright.sh [options]

Options:
  --url URL            Wrapper base URL (default: http://127.0.0.1:18090)
  --api-base URL       API base for deterministic seeding (default: http://127.0.0.1:18080)
  --output-dir DIR     Output directory for results/traces
  --seed               Run deterministic seed before Playwright (default)
  --no-seed            Skip deterministic seed step
  --chat-warmup        Send real warmup chat request before Playwright
  --no-chat-warmup     Skip chat warmup request (default)
  --dry-run            Print planned actions and exit
  -h, --help           Show help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      URL="$2"
      shift 2
      ;;
    --api-base)
      API_BASE="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --seed)
      SEED=1
      shift
      ;;
    --no-seed)
      SEED=0
      shift
      ;;
    --chat-warmup)
      CHAT_WARMUP=1
      shift
      ;;
    --no-chat-warmup)
      CHAT_WARMUP=0
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

if [[ -z "${OUTPUT_DIR}" ]]; then
  RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
  OUTPUT_DIR="${ROOT_DIR}/.finagent/verification/web-playwright-${RUN_TS}"
fi

OUTPUT_DIR="$(env -u PYTHONHOME -u PYTHONPATH python3 - "${OUTPUT_DIR}" <<'PY'
import os
import sys

print(os.path.abspath(sys.argv[1]))
PY
)"

if [[ ${DRY_RUN} -eq 1 ]]; then
  cat <<DRY
web playwright e2e dry-run
url=${URL}
api_base=${API_BASE}
output_dir=${OUTPUT_DIR}
seed=${SEED}
chat_warmup=${CHAT_WARMUP}
steps:
  - deterministic seed via scripts/seed-web-e2e.sh
  - health checks (/health, /v1/chat/health)
  - optional real chat warmup request (/v1/chat/respond)
  - playwright chromium install
  - run chat journey specs
  - run workspace journey specs
  - run robustness specs
  - write traces/screenshots/results
DRY
  exit 0
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required for Playwright tests" >&2
  exit 1
fi

if [[ ! -f "${WEB_APP_DIR}/package.json" ]]; then
  echo "missing web app package manifest: ${WEB_APP_DIR}/package.json" >&2
  exit 1
fi

if [[ ! -d "${WEB_APP_DIR}/node_modules/@playwright/test" ]]; then
  npm --prefix "${WEB_APP_DIR}" ci
fi

WRAPPER_BASE="$(env -u PYTHONHOME -u PYTHONPATH python3 - "${URL}" <<'PY'
import sys
from urllib.parse import urlsplit

url = sys.argv[1]
parts = urlsplit(url)
if not parts.scheme or not parts.netloc:
    raise SystemExit(f"invalid --url value: {url}")
print(f"{parts.scheme}://{parts.netloc}")
PY
)"

mkdir -p "${OUTPUT_DIR}"
SEED_SUMMARY="${OUTPUT_DIR}/seed-summary.json"

if [[ ${SEED} -eq 1 ]]; then
  bash scripts/seed-web-e2e.sh --api-base "${API_BASE}" --output-json "${SEED_SUMMARY}"
fi

if ! curl -fsS "${API_BASE}/health" >/dev/null 2>&1; then
  echo "api health check failed at ${API_BASE}/health" >&2
  exit 1
fi

if ! curl -fsS "${WRAPPER_BASE}/health" >/dev/null 2>&1; then
  echo "wrapper health check failed at ${WRAPPER_BASE}/health" >&2
  exit 1
fi

if ! curl -fsS "${WRAPPER_BASE}/v1/chat/health" >/dev/null 2>&1; then
  echo "chat bridge health check failed at ${WRAPPER_BASE}/v1/chat/health; ensure real opencode server is running and reachable by wrapper" >&2
  exit 1
fi

if [[ ${CHAT_WARMUP} -eq 1 ]]; then
  WRAPPER_BASE_ENV="${WRAPPER_BASE}"
  env -u PYTHONHOME -u PYTHONPATH WRAPPER_BASE="${WRAPPER_BASE_ENV}" python3 - <<'PY'
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

wrapper_base = os.environ["WRAPPER_BASE"].rstrip("/")
payload = {
    "message": "e2e warmup ping",
    "title": "e2e-warmup",
}
request = urllib.request.Request(
    url=f"{wrapper_base}/v1/chat/respond",
    method="POST",
    data=json.dumps(payload).encode("utf-8"),
    headers={"content-type": "application/json"},
)
try:
    with urllib.request.urlopen(request, timeout=240) as response:
        if int(response.status) != 200:
            raise RuntimeError(f"chat warmup failed status={response.status}")
        body = response.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"chat warmup returned invalid json: {body}") from exc
        if not isinstance(parsed.get("session_id"), str) or not parsed["session_id"].strip():
            raise RuntimeError(f"chat warmup missing session_id: {parsed}")
except urllib.error.HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    raise SystemExit(f"chat warmup failed status={exc.code} detail={detail}") from exc
except urllib.error.URLError as exc:
    raise SystemExit(f"chat warmup failed reason={exc.reason}") from exc
except Exception as exc:  # pragma: no cover - surfaced in script stderr
    raise SystemExit(str(exc)) from exc
PY
fi

(
  cd "${WEB_APP_DIR}"
  npx playwright install chromium
)

(
  cd "${WEB_APP_DIR}"
  PLAYWRIGHT_BASE_URL="${WRAPPER_BASE}" \
  PLAYWRIGHT_RESULTS_DIR="${OUTPUT_DIR}/results" \
  PLAYWRIGHT_SEED_SUMMARY="${SEED_SUMMARY}" \
  npx playwright test --config e2e/playwright.config.mjs
)

echo "web playwright e2e passed"
echo "results=${OUTPUT_DIR}/results"
