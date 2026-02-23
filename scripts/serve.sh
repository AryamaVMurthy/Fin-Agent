#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${ROOT_DIR}/.venv312"

if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "python venv not found at ${VENV}; create it first" >&2
  exit 1
fi

if [[ -f "${ROOT_DIR}/.env.local" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "${ROOT_DIR}/.env.local"
  set +a
fi

export FIN_AGENT_HOME="${FIN_AGENT_HOME:-${ROOT_DIR}/.finagent}"
exec env -u PYTHONHOME -u PYTHONPATH PYTHONPATH="${ROOT_DIR}/py" "${VENV}/bin/python" -m uvicorn fin_agent.api.app:app --host 127.0.0.1 --port 8080
