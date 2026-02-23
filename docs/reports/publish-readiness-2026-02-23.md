# Publish Readiness Report (2026-02-23)

## Scope

Validation of Stage1 publish hardening for GitHub + npm after implementation of:

1. npm package metadata + CLI entrypoint
2. publish-readiness gate script
3. GitHub CI/release workflows
4. release governance docs and packaging updates

## Commands executed

1. `env -u PYTHONHOME -u PYTHONPATH PYTHONPATH=py ./.venv312/bin/python -m unittest discover -s py/tests -p 'test_*.py'`
   - Result: `PASS` (`91` tests)
2. `bash scripts/e2e-smoke.sh`
   - Result: `PASS`
3. `bash scripts/e2e-full.sh --skip-doctor`
   - Result: `PASS`
   - Run: `rigorous-20260223T113234Z`
4. `bash scripts/e2e-full.sh --with-providers --with-opencode --runtime-home .finagent`
   - Result: `PASS`
   - Run: `rigorous-20260223T113251Z`
5. `bash scripts/publish-readiness.sh --allow-dirty --skip-auth`
   - Result: `PASS` (`publish-readiness: READY`)
6. `cd apps/fin-agent && npm publish --dry-run`
   - Result: `PASS` (dry-run package publish path valid)
7. `bash scripts/publish-readiness.sh`
   - Result: `FAIL` (strict mode)

## Strict mode blockers (current)

`publish-readiness.sh` strict mode fails only on:

1. `git-clean`
   - Cause: repository has uncommitted/untracked changes.
   - Required action: commit/stash/remove changes and rerun gate.
2. `npm-auth`
   - Cause: npm session not authenticated on this machine (`ENEEDAUTH`).
   - Required action: `npm login` (or `npm adduser`) with the target publishing account.

All other strict checks pass:

1. npm metadata
2. CLI entrypoint
3. npm pack dry-run
4. release script dry-run
5. full Python test suite
6. smoke E2E

## Publishability decision

Current status: **conditionally ready**.

1. Engineering/product gates are green.
2. Final release gating is blocked only by operator actions (clean git state + npm auth).
3. After those two actions, rerun `bash scripts/publish-readiness.sh`; expected outcome should be `publish-readiness: READY`.

