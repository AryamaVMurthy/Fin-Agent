# Rigorous End-User Verification Plan (Stage 1)

Date: 2026-02-23
Owner: `Fin-Agent-3oj`

## 1) Goal

Prove the system is publish-ready from a real user perspective with:

1. End-to-end execution (no unit-level mocks in the verification harness).
2. Full core user flows through running services.
3. Clear pass/fail evidence and artifact capture.
4. Explicit failure remediation instructions.

## 2) Verification Principles

1. No silent fallback: every skipped gate must be explicit and operator-visible.
2. Deterministic baseline: core flow uses controlled local datasets.
3. Live extensions: provider and OpenCode integration checks run in strict mode when enabled.
4. Evidence-first: every gate emits logs and JSON artifacts.

## 3) Flow Matrix

### A. Core deterministic product flow (mandatory)

1. Startup gates:
  - API boot + `/health`
  - Wrapper boot + `/health`
2. Data ingestion:
  - OHLCV import
  - Fundamentals/corporate-actions/ratings import
3. Intent + strategy:
  - `agent-decides/propose`
  - `agent-decides/confirm`
  - `strategy/from-intent`
4. World-state quality:
  - `completeness`
  - `validate-pit`
5. Backtest lifecycle:
  - `preflight/backtest`
  - `backtests/run` (two variants)
  - `backtests/compare`
6. Tuning lifecycle:
  - `preflight/tuning`
  - `tuning/search-space/derive` (policy-driven)
  - `tuning/run` (sensitivity + plan output)
7. Analysis + visualization:
  - `analysis/deep-dive`
  - `visualize/trade-blotter`
  - `visualize/boundary`
8. Live lifecycle:
  - `live/activate`
  - `live/feed`
  - `live/boundary-candidates`
  - `live/pause`
  - `live/stop`
9. Custom Python lane:
  - `code-strategy/validate`
  - `code-strategy/save`
  - `code-strategy/run-sandbox`
  - `code-strategy/backtest`
  - `code-strategy/analyze`
10. Tax + memory + diagnostics:
  - `backtests/tax/report`
  - `session/snapshot` (2x) + `session/diff` + `session/rehydrate`
  - `providers/health`
  - `observability/metrics`
  - `diagnostics/readiness`

### B. Wrapper parity flow (mandatory)

1. Execute key API calls through wrapper base URL.
2. Assert status/body parity with direct API endpoints.

### C. Provider live flow (optional strict gate)

1. Kite:
  - auth status must be `connected=true`
  - profile/holdings
  - instruments sync
  - candles fetch with cache validation
2. NSE:
  - quote fetch
3. TradingView:
  - screener run

When `--with-providers` is enabled, missing config or auth is a hard failure.

### D. OpenCode integration flow (optional strict gate)

1. `opencode` binary availability.
2. OpenAI auth presence (`oauth` or `api` credential).
3. Real server reachability via wrapper chat bridge:
  - `/v1/chat/health`
  - `/v1/chat/sessions`

When `--with-opencode` is enabled, missing auth is a hard failure.

### E. Real web interaction flow (optional strict gate)

1. Launch full Playwright interaction suite through wrapper:
  - chat journey
  - workspace journey
  - robustness journey
2. Uses deterministic seed via `scripts/seed-web-e2e.sh`.
3. No stubs; requires real OpenCode server.

When `--with-web-playwright` is enabled, any failing browser interaction gate is a hard failure.

### F. Publishability flow (mandatory)

1. `scripts/doctor.sh`
2. Linux install script sanity
3. release dry-run script
4. Python full test suite

## 4) Evidence Artifacts

A run must generate:

1. `logs/api.log`
2. `logs/wrapper.log`
3. `artifacts/summary.json`
4. `artifacts/steps.jsonl`
5. `artifacts/http/*.json` request/response captures
6. `artifacts/web-playwright/*` traces/screenshots/results (when enabled)
7. `logs/opencode.log` when e2e-full launches OpenCode locally

## 5) Pass Criteria

All mandatory gates pass:

1. Core deterministic flow.
2. Wrapper parity flow.
3. Publishability flow.

Optional gates pass when explicitly enabled:

1. Provider live flow (strict).
2. OpenCode flow (strict).
3. Real Playwright interaction flow (strict).

## 6) Failure Policy

On first failure:

1. Stop progression.
2. Emit failing gate ID, endpoint/command, and payload context.
3. Emit remediation line in summary artifact.
4. Exit non-zero.

## 7) Execution Plan

1. Add `scripts/e2e-full.sh` with strict gate execution.
2. Add script-level automated test coverage.
3. Run:
  - full python tests
  - e2e full deterministic run
  - optional live/provider run if configured.
4. Publish result summary in Beads issue notes.

## 8) Canonical Commands

1. Full strict real-stack run (no stubs):
  - `bash scripts/e2e-full.sh --with-opencode --with-web-playwright --with-web-visual --runtime-home .finagent`
2. Full strict with provider live checks:
  - `bash scripts/e2e-full.sh --with-opencode --with-providers --with-web-playwright --with-web-visual --runtime-home .finagent`
