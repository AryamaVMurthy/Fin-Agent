# Stage 1 Operator Runbook

## Scope

This runbook covers Stage 1 operations for:
- API service startup and health
- OpenCode OAuth checks
- Kite auth and account checks
- Data import, PIT validation, and preflight gates
- Backtest execution, async jobs, compare flows
- Tuning/deep analysis, visualization, live lifecycle
- Custom code backtest + patch suggestions
- Audit and structured log troubleshooting

## 1) Start and Health

Start API:

```bash
./scripts/serve.sh
```

Health check:

```bash
curl -sS http://127.0.0.1:8080/health
```

Expected:

```json
{"status":"ok"}
```

## 2) OpenCode OAuth

Status:

```bash
curl -sS http://127.0.0.1:8080/v1/auth/opencode/openai/oauth/status
```

Connect action:

```bash
curl -sS http://127.0.0.1:8080/v1/auth/opencode/openai/oauth/connect
```

If not connected, run:

```bash
opencode auth login openai
```

Alternative:
- Set `OPENAI_API_KEY` in `.env.local` and restart services.

## 3) Kite Auth

Status:

```bash
curl -sS http://127.0.0.1:8080/v1/auth/kite/status
```

Connect:

```bash
curl -sS http://127.0.0.1:8080/v1/auth/kite/connect
```

If API returns `reauth_required`, reconnect via `/v1/auth/kite/connect`.

## 4) Data + PIT Gates

Import OHLCV:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/data/import \
  -H 'content-type: application/json' \
  -d '{"path":"/absolute/path/to/prices.csv"}'
```

Import fundamentals/corporate actions/ratings:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/data/import/fundamentals \
  -H 'content-type: application/json' \
  -d '{"path":"/absolute/path/to/fundamentals.csv"}'

curl -sS -X POST http://127.0.0.1:8080/v1/data/import/corporate-actions \
  -H 'content-type: application/json' \
  -d '{"path":"/absolute/path/to/actions.csv"}'

curl -sS -X POST http://127.0.0.1:8080/v1/data/import/ratings \
  -H 'content-type: application/json' \
  -d '{"path":"/absolute/path/to/ratings.csv"}'
```

Fundamentals as-of:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/data/fundamentals/as-of \
  -H 'content-type: application/json' \
  -d '{"symbol":"ABC","as_of":"2025-01-15T00:00:00Z"}'
```

Completeness:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/world-state/completeness \
  -H 'content-type: application/json' \
  -d '{"universe":["ABC"],"start_date":"2025-01-01","end_date":"2025-01-10","strict_mode":false}'
```

PIT validation:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/world-state/validate-pit \
  -H 'content-type: application/json' \
  -d '{"universe":["ABC"],"start_date":"2025-01-01","end_date":"2025-01-10","strict_mode":true}'
```

## 5) Preflight Budgets

World-state:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/preflight/world-state \
  -H 'content-type: application/json' \
  -d '{"universe":["ABC"],"start_date":"2025-01-01","end_date":"2025-01-10","max_allowed_seconds":20}'
```

Backtest:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/preflight/backtest \
  -H 'content-type: application/json' \
  -d '{"strategy_name":"SMA","intent_snapshot_id":"<id>","max_allowed_seconds":30}'
```

Tuning:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/preflight/tuning \
  -H 'content-type: application/json' \
  -d '{"num_trials":50,"per_trial_estimated_seconds":1.2,"max_allowed_seconds":60}'
```

Custom code:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/preflight/custom-code \
  -H 'content-type: application/json' \
  -d '{"universe":["ABC"],"start_date":"2025-01-01","end_date":"2025-01-10","complexity_multiplier":1.2,"max_allowed_seconds":60}'
```

If preflight fails, API returns `400` with remediation text.

## 6) Backtests and Compare

Run:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/backtests/run \
  -H 'content-type: application/json' \
  -d '{"strategy_name":"SMA","intent":{"universe":["ABC"],"start_date":"2025-01-01","end_date":"2025-01-10","initial_capital":100000,"short_window":2,"long_window":4,"max_positions":1}}'
```

Async run:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/backtests/run-async \
  -H 'content-type: application/json' \
  -d '{"strategy_name":"SMA","intent_snapshot_id":"<id>"}'
```

Job status:

```bash
curl -sS http://127.0.0.1:8080/v1/jobs/<job_id>
```

Compare:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/backtests/compare \
  -H 'content-type: application/json' \
  -d '{"baseline_run_id":"<run1>","candidate_run_id":"<run2>"}'
```

## 7) Tuning + Analysis + Visualization + Live

Derive tuning search space:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/tuning/search-space/derive \
  -H 'content-type: application/json' \
  -d '{"strategy_name":"Tune","intent":{"universe":["ABC"],"start_date":"2025-01-01","end_date":"2025-01-10","initial_capital":100000,"short_window":2,"long_window":4,"max_positions":1},"optimization_target":"sharpe","risk_mode":"balanced","policy_mode":"user_selected","include_layers":["signal","execution"]}'
```

Key response fields:
- `search_space` (effective parameter grid)
- `tuning_plan.layers` (enabled/disabled layer decisions)
- `tuning_plan.graph` (objective->layer->parameter graph)
- `estimated_trials`

Run tuning:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/tuning/run \
  -H 'content-type: application/json' \
  -d '{"strategy_name":"Tune","intent":{"universe":["ABC"],"start_date":"2025-01-01","end_date":"2025-01-10","initial_capital":100000,"short_window":2,"long_window":4,"max_positions":1},"optimization_target":"sharpe","risk_mode":"balanced","policy_mode":"user_selected","include_layers":["signal","execution"],"max_trials":5}'
```

Key response fields:
- `best_candidate`
- `top_candidates`
- `sensitivity_analysis`
- `tuning_plan`

Deep dive:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/analysis/deep-dive \
  -H 'content-type: application/json' \
  -d '{"run_id":"<run_id>"}'
```

Trade blotter and boundary visualization:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/visualize/trade-blotter \
  -H 'content-type: application/json' \
  -d '{"run_id":"<run_id>"}'

curl -sS -X POST http://127.0.0.1:8080/v1/visualize/boundary \
  -H 'content-type: application/json' \
  -d '{"strategy_version_id":"<strategy_version_id>","top_k":10}'
```

Live lifecycle and feed:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/live/activate \
  -H 'content-type: application/json' \
  -d '{"strategy_version_id":"<strategy_version_id>"}'

curl -sS "http://127.0.0.1:8080/v1/live/feed?strategy_version_id=<strategy_version_id>&limit=50"
curl -sS "http://127.0.0.1:8080/v1/live/boundary-candidates?strategy_version_id=<strategy_version_id>&top_k=10"

curl -sS -X POST http://127.0.0.1:8080/v1/live/pause \
  -H 'content-type: application/json' \
  -d '{"strategy_version_id":"<strategy_version_id>"}'

curl -sS -X POST http://127.0.0.1:8080/v1/live/stop \
  -H 'content-type: application/json' \
  -d '{"strategy_version_id":"<strategy_version_id>"}'
```

Custom code backtest + analysis:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/code-strategy/backtest \
  -H 'content-type: application/json' \
  -d '{"strategy_name":"CodeStrat","source_code":"<python code>","universe":["ABC"],"start_date":"2025-01-01","end_date":"2025-01-10","initial_capital":100000}'

curl -sS -X POST http://127.0.0.1:8080/v1/code-strategy/analyze \
  -H 'content-type: application/json' \
  -d '{"run_id":"<code_run_id>","source_code":"<python code>"}'
```

## 8) Audit and Logs

Audit events:

```bash
curl -sS "http://127.0.0.1:8080/v1/audit/events?limit=100"
```

Structured logs:

```bash
tail -f .finagent/logs/structured.log
```

Use `trace_id` to correlate:
- request.start / request.end / request.error
- job events
- audit events

## 9) Standard Failure Handling

1. Stop unsafe progression.
2. Capture exact API error payload.
3. Find matching `trace_id` in structured logs and audit events.
4. Apply remediation from API error text.
5. Re-run from last safe step.

## 9) Tax Overlay Report

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/backtests/tax/report \
  -H 'content-type: application/json' \
  -d '{"run_id":"<run_id>","enabled":true,"stcg_rate":0.20,"ltcg_rate":0.125}'
```

## 10) Session Rehydrate and Context Delta

Persist a session snapshot:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/session/snapshot \
  -H 'content-type: application/json' \
  -d '{"session_id":"default","state":{"last_strategy_id":"<id>","last_formula":"close > open"}}'
```

Rehydrate session:

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/session/rehydrate \
  -H 'content-type: application/json' \
  -d '{"session_id":"default"}'
```

Diff latest two snapshots:

```bash
curl -sS "http://127.0.0.1:8080/v1/session/diff?session_id=default"
```

## 11) Readiness and Provider Diagnostics

```bash
curl -sS http://127.0.0.1:8080/v1/providers/health
curl -sS http://127.0.0.1:8080/v1/observability/metrics
curl -sS http://127.0.0.1:8080/v1/diagnostics/readiness
```

## 12) Linux Packaging and Startup

```bash
./scripts/install-linux.sh
./scripts/gen-encryption-key.sh --write
./scripts/doctor.sh
./scripts/start-all.sh
./scripts/release-tui.sh --version 0.1.0
./scripts/e2e-smoke.sh
./scripts/e2e-full.sh
# optional strict live-provider + opencode gates:
./scripts/e2e-full.sh --with-providers --with-opencode
# if Kite session already exists in default local store:
./scripts/e2e-full.sh --with-providers --runtime-home ./.finagent
```
