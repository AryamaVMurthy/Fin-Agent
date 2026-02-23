# Stage1 Publish Runbook

This runbook is the source of truth for shipping Fin-Agent to GitHub and npm.

## Preconditions

1. You are on the intended release branch (`main` unless explicitly overridden).
2. Local runtime prerequisites are installed (`python3`, `node`, `.venv312`).
3. Kite/OpenCode integration checks are only required for live-provider release evidence, not for deterministic CI release gates.

## Local release gate

Run strict publish readiness:

```bash
bash scripts/publish-readiness.sh
```

Expected outcome:

1. `publish-readiness: READY`
2. No failed checks.

If it fails:

1. Read the emitted remediation line for each failed check.
2. Fix root cause.
3. Re-run until all checks pass.

## Common blockers

### 1) npm auth missing

Symptom:

`npm whoami` fails with `ENEEDAUTH`.

Fix:

```bash
npm login
cd apps/fin-agent
npm whoami
```

### 2) Dirty git worktree

Symptom:

`git-clean` check fails.

Fix:

1. Commit intended changes.
2. Remove accidental artifacts.
3. Re-run readiness gate.

### 3) Metadata or package errors

Symptom:

`npm-metadata` or `npm-pack-dry-run` fails.

Fix:

1. Repair `apps/fin-agent/package.json`.
2. Verify `fin-agent` bin entry and `src/cli.mjs`.
3. Re-run readiness gate.

## GitHub publish flow

1. Push committed release changes.
2. Create and push a version tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

3. `release.yml` runs:
   - publish-readiness gate (CI mode),
   - deterministic strict E2E,
   - release archive generation,
   - GitHub Release asset upload (`dist/*.tar.gz`, `dist/*.sha256`).

## npm publish flow

`release.yml` publishes npm package only when:

1. Trigger is a `v*` tag.
2. `NPM_TOKEN` secret is present.

Package published from:

`apps/fin-agent/package.json`

## Post-publish verification

After release:

1. Confirm GitHub release assets are present.
2. Confirm npm package exists:

```bash
npm view fin-agent-wrapper version
```

3. Validate install/help output:

```bash
npm i -g fin-agent-wrapper
fin-agent --help
```
