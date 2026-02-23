#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_PATH="${ROOT_DIR}/.env.local"
PRINT_ONLY=0
WRITE_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --print)
      PRINT_ONLY=1
      shift
      ;;
    --write)
      WRITE_ONLY=1
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      echo "usage: $0 [--print|--write]" >&2
      exit 1
      ;;
  esac
done

if [[ ${PRINT_ONLY} -eq 1 && ${WRITE_ONLY} -eq 1 ]]; then
  echo "--print and --write are mutually exclusive" >&2
  exit 1
fi

KEY="$(env -u PYTHONHOME -u PYTHONPATH python3 - <<'PY'
import base64
import os
print(base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"))
PY
)"

if [[ ${PRINT_ONLY} -eq 1 ]]; then
  echo "${KEY}"
  exit 0
fi

if [[ ${WRITE_ONLY} -eq 1 ]]; then
  if [[ ! -f "${ENV_PATH}" ]]; then
    echo ".env.local not found at ${ENV_PATH}" >&2
    echo "create it first: cp .env.example .env.local" >&2
    exit 1
  fi

  if grep -q '^FIN_AGENT_ENCRYPTION_KEY=' "${ENV_PATH}"; then
    sed -i "s|^FIN_AGENT_ENCRYPTION_KEY=.*$|FIN_AGENT_ENCRYPTION_KEY=${KEY}|" "${ENV_PATH}"
  else
    printf '\nFIN_AGENT_ENCRYPTION_KEY=%s\n' "${KEY}" >> "${ENV_PATH}"
  fi
  echo "updated .env.local with FIN_AGENT_ENCRYPTION_KEY"
  exit 0
fi

echo "generated FIN_AGENT_ENCRYPTION_KEY:"
echo "${KEY}"
echo
echo "to persist it into .env.local, run:"
echo "  ./scripts/gen-encryption-key.sh --write"
