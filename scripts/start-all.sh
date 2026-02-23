#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

./scripts/doctor.sh

if lsof -i:8080 >/dev/null 2>&1; then
  echo "port 8080 already in use" >&2
  exit 1
fi
if lsof -i:8090 >/dev/null 2>&1; then
  echo "port 8090 already in use" >&2
  exit 1
fi

./scripts/serve.sh > .finagent/api.log 2>&1 &
API_PID=$!
( cd apps/fin-agent && npm run dev ) > .finagent/wrapper.log 2>&1 &
WRAPPER_PID=$!

sleep 2
curl -fsS http://127.0.0.1:8080/health >/dev/null
curl -fsS http://127.0.0.1:8090/health >/dev/null

echo "fin-agent api pid=${API_PID}"
echo "fin-agent wrapper pid=${WRAPPER_PID}"
echo "Run opencode separately: ./scripts/opencode-serve.sh"
