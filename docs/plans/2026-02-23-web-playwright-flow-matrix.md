# Stage1 Web Playwright Flow Matrix

> **Scope:** Full browser-interaction E2E coverage for the web UI served from `/app` on top of wrapper + API.

## 1) Pass Criteria

A build is **Playwright-ready** only when all below are true:

1. All mandatory flow specs pass in Chromium in headed/trace-capable mode.
2. No uncaught browser console errors during normal flows.
3. No failed network requests for required API calls in normal flows.
4. All required artifacts are produced:
   - trace zip per failed test
   - screenshot on failure
   - run summary JSON
5. System-level gate (`scripts/e2e-full.sh`) passes with Playwright enabled.

## 2) Mandatory Flows

### A. Boot and Layout

1. Load `/app` and verify shell sections are visible:
   - `#chat-panel`
   - `#timeline-panel`
   - `#action-cards`
   - `#workspace-backtests`
   - `#workspace-tuning`
   - `#workspace-live`
   - `#workspace-diagnostics`
2. Verify status banner initializes without error state.

### B. Chat Journey

1. Fetch sessions via `/v1/chat/sessions`.
2. Create/select session via UI controls.
3. Send message through chat form.
4. Verify `/v1/chat/respond` is called and response appears in message list.
5. Trigger each action card and verify request/response path.
6. Verify timeline gets updated with chat events.

### C. Backtests Workspace

1. Open Backtests tab.
2. Verify rows populated from `/v1/backtests/runs`.
3. Click `View` on a run.
4. Verify detail panel is rendered and includes metrics.
5. Verify artifact images are rendered from `/v1/artifacts/file`.

### D. Tuning Workspace

1. Open Tuning tab.
2. Verify rows from `/v1/tuning/runs`.
3. Click `View` on a tuning run.
4. Verify detail panel includes trial/layer counts.

### E. Live Workspace

1. Open Live tab.
2. Verify rows from `/v1/live/states`.
3. Verify state columns (`strategy_version_id`, `status`, `updated_at`) render.

### F. Diagnostics Workspace

1. Open Diagnostics tab.
2. Verify `/v1/providers/health` payload displayed.
3. Verify `/v1/diagnostics/readiness` payload displayed.

### G. Timeline/Audit Flow

1. Trigger refresh timeline.
2. Verify `/v1/audit/events` call occurs.
3. Verify new entries appended in `#event-timeline`.

### H. Robustness Flows

1. Empty chat submission should produce visible error state.
2. Simulated backend 4xx/5xx should produce visible status banner error.
3. Test must fail on unexpected console errors (`error` level).

## 3) Required API Contract Coverage

Playwright assertions must explicitly confirm these endpoint touches during normal flows:

1. `/v1/chat/sessions`
2. `/v1/chat/respond`
3. `/v1/chat/sessions/{id}/messages`
4. `/v1/backtests/runs`
5. `/v1/backtests/runs/{run_id}`
6. `/v1/tuning/runs`
7. `/v1/tuning/runs/{tuning_run_id}`
8. `/v1/live/states`
9. `/v1/providers/health`
10. `/v1/diagnostics/readiness`
11. `/v1/audit/events`

## 4) Deterministic Data Preconditions

Before Playwright run:

1. Deterministic OHLCV/fundamentals/actions/ratings imported.
2. At least two backtest runs exist.
3. At least one tuning run exists with trials/layers.
4. At least one live state exists.
5. Wrapper and API health checks pass.

## 5) Test Stages

1. `stage-setup`: service boot + deterministic seed.
2. `stage-chat`: chat/session/action-card flows.
3. `stage-workspaces`: backtest/tuning/live/diagnostics flows.
4. `stage-robustness`: error and observability assertions.
5. `stage-evidence`: traces/screenshots/results bundling.

## 6) Failure Policy

1. Any failed mandatory flow is release-blocking.
2. Any missing artifact is release-blocking.
3. Any suppressed fallback behavior is release-blocking.
4. Retry allowed once for infra/network flake; second failure is hard fail.
