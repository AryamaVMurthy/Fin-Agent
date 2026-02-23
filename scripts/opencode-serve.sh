#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "${ROOT_DIR}/.env.local" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "${ROOT_DIR}/.env.local"
  set +a
fi

if [[ "${FIN_AGENT_OPENCODE_USE_GLOBAL_CONFIG:-0}" != "1" ]]; then
  CONFIG_HOME_BASE="${FIN_AGENT_OPENCODE_CONFIG_HOME:-${ROOT_DIR}/.finagent/opencode-config}"
  CONFIG_DIR="${CONFIG_HOME_BASE}/opencode"
  CONFIG_PATH="${CONFIG_DIR}/opencode.json"
  MODEL_VALUE="${FIN_AGENT_OPENCODE_MODEL:-openai/gpt-5.2-codex}"
  mkdir -p "${CONFIG_DIR}"
  if [[ "${FIN_AGENT_OPENCODE_PRESERVE_CONFIG:-0}" != "1" || ! -f "${CONFIG_PATH}" ]]; then
    cat > "${CONFIG_PATH}" <<JSON
{
  "\$schema": "https://opencode.ai/config.json",
  "model": "${MODEL_VALUE}",
  "plugin": [
    "oh-my-opencode",
    "opencode-beads"
  ]
}
JSON
  fi
  export XDG_CONFIG_HOME="${CONFIG_HOME_BASE}"
  echo "Using isolated OpenCode config at ${CONFIG_PATH}"
else
  echo "Using global OpenCode config (FIN_AGENT_OPENCODE_USE_GLOBAL_CONFIG=1)"
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
