#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

DRY_RUN=0
ALLOW_DIRTY=0
SKIP_AUTH=0
SKIP_TESTS=0
SKIP_SMOKE=0

usage() {
  cat <<'EOF'
usage: scripts/publish-readiness.sh [options]

Options:
  --dry-run       Print checks and exit
  --allow-dirty   Skip clean-worktree check
  --skip-auth     Skip npm auth check
  --skip-tests    Skip Python unit-test suite
  --skip-smoke    Skip smoke E2E execution
  -h, --help      Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --skip-auth)
      SKIP_AUTH=1
      shift
      ;;
    --skip-tests)
      SKIP_TESTS=1
      shift
      ;;
    --skip-smoke)
      SKIP_SMOKE=1
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

if [[ ${DRY_RUN} -eq 1 ]]; then
  cat <<EOF
publish readiness dry-run
allow_dirty=${ALLOW_DIRTY}
skip_auth=${SKIP_AUTH}
skip_tests=${SKIP_TESTS}
skip_smoke=${SKIP_SMOKE}
checks:
  - package metadata (npm publish-safe fields)
  - cli entrypoint exists
  - npm pack --dry-run
  - release archive dry-run
  - clean git worktree (unless --allow-dirty)
  - Python unit tests (unless --skip-tests)
  - smoke e2e run (unless --skip-smoke)
  - npm whoami auth (unless --skip-auth)
EOF
  exit 0
fi

check() {
  local name="$1"
  local cmd="$2"
  local remediation="$3"
  if bash -lc "$cmd" >/tmp/fin-agent-publish-check.out 2>/tmp/fin-agent-publish-check.err; then
    echo "PASS  ${name}"
    return 0
  fi
  echo "FAIL  ${name}" >&2
  if [[ -s /tmp/fin-agent-publish-check.err ]]; then
    sed -n '1,120p' /tmp/fin-agent-publish-check.err >&2
  elif [[ -s /tmp/fin-agent-publish-check.out ]]; then
    sed -n '1,120p' /tmp/fin-agent-publish-check.out >&2
  fi
  echo "remediation: ${remediation}" >&2
  return 1
}

fail=0

check \
  "npm-metadata" \
  "jq -e '.private == false and .bin[\"fin-agent\"] == \"src/cli.mjs\" and .license == \"MIT\" and .publishConfig.access == \"public\"' apps/fin-agent/package.json >/dev/null" \
  "update apps/fin-agent/package.json for publish-safe metadata" || fail=1

check \
  "cli-entrypoint" \
  "test -f apps/fin-agent/src/cli.mjs && node apps/fin-agent/src/cli.mjs --help >/dev/null" \
  "create or repair apps/fin-agent/src/cli.mjs" || fail=1

check \
  "npm-pack-dry-run" \
  "cd apps/fin-agent && npm pack --dry-run >/dev/null" \
  "fix npm package contents until npm pack --dry-run succeeds" || fail=1

check \
  "release-script-dry-run" \
  "bash scripts/release-tui.sh --dry-run --version readiness >/dev/null" \
  "fix scripts/release-tui.sh contract and copy paths" || fail=1

if [[ ${ALLOW_DIRTY} -eq 0 ]]; then
  check \
    "git-clean" \
    "test -z \"\$(git status --porcelain)\"" \
    "commit/stash/remove changes so git status is clean" || fail=1
else
  echo "SKIP  git-clean (allow_dirty enabled)"
fi

if [[ ${SKIP_TESTS} -eq 0 ]]; then
  check \
    "python-unit-tests" \
    "env -u PYTHONHOME -u PYTHONPATH PYTHONPATH=py ./.venv312/bin/python -m unittest discover -s py/tests -p 'test_*.py'" \
    "fix failing unit tests before publish" || fail=1
else
  echo "SKIP  python-unit-tests (skip_tests enabled)"
fi

if [[ ${SKIP_SMOKE} -eq 0 ]]; then
  check \
    "smoke-e2e" \
    "bash scripts/e2e-smoke.sh" \
    "fix startup/data/smoke integration failures" || fail=1
else
  echo "SKIP  smoke-e2e (skip_smoke enabled)"
fi

if [[ ${SKIP_AUTH} -eq 0 ]]; then
  check \
    "npm-auth" \
    "cd apps/fin-agent && npm whoami >/dev/null" \
    "run npm login (or npm adduser) with the target publishing account" || fail=1
else
  echo "SKIP  npm-auth (skip_auth enabled)"
fi

if [[ ${fail} -ne 0 ]]; then
  echo "publish-readiness: FAILED" >&2
  exit 1
fi

echo "publish-readiness: READY"
