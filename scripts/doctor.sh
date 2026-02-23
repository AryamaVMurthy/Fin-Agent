#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

check() {
  local name="$1"
  local cmd="$2"
  if bash -lc "$cmd" >/dev/null 2>&1; then
    echo "PASS  ${name}"
  else
    echo "FAIL  ${name}"
    return 1
  fi
}

fail=0
check "python-venv" "test -x .venv312/bin/python" || fail=1
check "node" "command -v node" || fail=1
check "opencode" "command -v opencode" || fail=1
check "api-script" "test -x scripts/serve.sh" || fail=1
check "wrapper-entry" "test -f apps/fin-agent/src/index.mjs" || fail=1
check "env-local" "test -f .env.local" || fail=1
check "kite-env" "grep -q FIN_AGENT_KITE_API_KEY .env.local && grep -q FIN_AGENT_KITE_API_SECRET .env.local && grep -q FIN_AGENT_KITE_REDIRECT_URI .env.local" || fail=1
check "encryption-key" "grep -q FIN_AGENT_ENCRYPTION_KEY .env.local" || fail=1
check "opencode-openai-auth" "opencode auth list | rg -qi 'OpenAI[[:space:]]+(oauth|api)' || rg -q '^OPENAI_API_KEY=.+$' .env.local" || fail=1

if [[ ${fail} -ne 0 ]]; then
  if ! grep -q '^FIN_AGENT_ENCRYPTION_KEY=.\+$' .env.local 2>/dev/null; then
    echo "remediation: generate and write encryption key with ./scripts/gen-encryption-key.sh --write" >&2
  fi
  echo "doctor: not ready" >&2
  exit 1
fi

echo "doctor: ready"
