#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "${ROOT_DIR}/.env.local" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "${ROOT_DIR}/.env.local"
  set +a
fi

if ! command -v opencode >/dev/null 2>&1; then
  echo "opencode is not installed in PATH" >&2
  exit 1
fi

if ! opencode auth list | rg -qi "OpenAI[[:space:]]+(oauth|api)"; then
  if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "OpenCode OpenAI auth is not connected (oauth/api) and OPENAI_API_KEY is not set." >&2
    echo "Run: ./scripts/opencode-auth-openai.sh or set OPENAI_API_KEY in .env.local" >&2
    exit 1
  fi
fi

HOSTNAME_VALUE="${OPENCODE_HOSTNAME:-127.0.0.1}"
PORT_VALUE="${OPENCODE_PORT:-4096}"

if [[ -n "${OPENCODE_SERVER_PASSWORD:-}" ]]; then
  echo "Starting secured OpenCode server on http://${HOSTNAME_VALUE}:${PORT_VALUE}"
  exec opencode serve --hostname "${HOSTNAME_VALUE}" --port "${PORT_VALUE}"
fi

echo "Starting OpenCode server (no password) on http://${HOSTNAME_VALUE}:${PORT_VALUE}"
exec opencode serve --hostname "${HOSTNAME_VALUE}" --port "${PORT_VALUE}"
