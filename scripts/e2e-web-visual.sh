#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

URL="${FIN_AGENT_WEB_URL:-http://127.0.0.1:18090/app}"
OUTPUT_DIR=""
DRY_RUN=0

usage() {
  cat <<'USAGE'
usage: scripts/e2e-web-visual.sh [options]

Options:
  --url URL          Web UI URL (default: http://127.0.0.1:18090/app)
  --output-dir DIR   Output directory for screenshots
  --dry-run          Print planned visual checks and exit
  -h, --help         Show help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      URL="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
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

if [[ -z "${OUTPUT_DIR}" ]]; then
  RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
  OUTPUT_DIR="${ROOT_DIR}/.finagent/verification/web-visual-${RUN_TS}"
fi

if [[ ${DRY_RUN} -eq 1 ]]; then
  cat <<DRY
web visual e2e dry-run
url=${URL}
output_dir=${OUTPUT_DIR}
checks:
  - desktop screenshot (chromium)
  - mobile screenshot (chromium mobile viewport)
  - playwright-driven browser rendering gate
DRY
  exit 0
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required for Playwright visual checks" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
DESKTOP_OUT="${OUTPUT_DIR}/desktop.png"
MOBILE_OUT="${OUTPUT_DIR}/mobile.png"

npx -y playwright@1.52.0 install chromium
npx -y playwright@1.52.0 screenshot --browser=chromium --device="Desktop Chrome" "${URL}" "${DESKTOP_OUT}"
npx -y playwright@1.52.0 screenshot --browser=chromium --viewport-size="390,844" "${URL}" "${MOBILE_OUT}"

if [[ ! -s "${DESKTOP_OUT}" || ! -s "${MOBILE_OUT}" ]]; then
  echo "playwright screenshots missing or empty" >&2
  exit 1
fi

echo "web visual e2e passed"
echo "desktop=${DESKTOP_OUT}"
echo "mobile=${MOBILE_OUT}"
