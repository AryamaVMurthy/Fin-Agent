#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

echo "[fin-agent] Linux installer starting"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "node is required" >&2
  exit 1
fi

if [[ ! -d .venv312 ]]; then
  python3 -m venv .venv312
fi

.venv312/bin/pip install --upgrade pip >/dev/null
.venv312/bin/pip install duckdb fastapi pydantic uvicorn cryptography >/dev/null

( cd apps/fin-agent && npm install --silent )

echo "[fin-agent] install complete"
echo "Next: ./scripts/doctor.sh"
