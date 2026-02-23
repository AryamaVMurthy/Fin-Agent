# Finance Tool Surface

This directory is reserved for OpenCode tool definitions.

Current implementation route:
- Runtime API in `py/fin_agent/api/app.py`.
- Wrapper process in `apps/fin-agent/src/index.mjs`.

Current agentic tool mapping (primary):
- `code_strategy_validate`
- `code_strategy_save`
- `code_strategy_run_sandbox`
- `code_strategy_backtest`
- `code_strategy_analyze`
- `preflight_custom_code`
- `backtest_compare`
- `visualize_trade_blotter`
- `backtest_tax_report`
- `world_state_build`
- `world_state_validate`
- `session_diff`
- `session_rehydrate`
- `technicals_compute`
- `universe_resolve`
- `screener_formula_validate`
- `screener_run`
- `kite_candles_fetch`
- `kite_instruments_sync`
- `auth_kite_status`
- `providers_health`
- `diagnostics_readiness`

Kite API endpoints currently implemented:
- `GET /v1/auth/kite/connect`
- `GET /v1/auth/kite/status`
- `GET /v1/auth/kite/callback`
- `GET /v1/kite/profile`
- `GET /v1/kite/holdings`
- `POST /v1/kite/instruments/sync`
- `POST /v1/kite/candles/fetch`
- `POST /v1/kite/quotes/fetch`

Screener endpoints currently implemented:
- `POST /v1/screener/formula/validate`
- `POST /v1/screener/run`

Provider endpoints currently implemented:
- `POST /v1/nse/quote`
- `POST /v1/tradingview/screener/run`

Hardening endpoints currently implemented:
- `POST /v1/backtests/tax/report`
- `POST /v1/context/delta`
- `POST /v1/session/snapshot`
- `POST /v1/session/rehydrate`
- `GET /v1/session/diff`
- `GET /v1/providers/health`
- `GET /v1/observability/metrics`
- `GET /v1/diagnostics/readiness`

OpenCode OAuth endpoints currently implemented:
- `GET /v1/auth/opencode/openai/oauth/status`
- `GET /v1/auth/opencode/openai/oauth/connect`

World-state + validation endpoints currently implemented:
- `POST /v1/world-state/build`
- `POST /v1/world-state/completeness`
- `POST /v1/world-state/validate-pit`

Preflight endpoints currently implemented:
- `POST /v1/preflight/world-state`
- `POST /v1/preflight/custom-code`

Legacy preflight endpoints disabled:
- `POST /v1/preflight/backtest` (HTTP 410)
- `POST /v1/preflight/tuning` (HTTP 410)

Agentic strategy control endpoints currently implemented:
- `POST /v1/code-strategy/validate`
- `POST /v1/code-strategy/save`
- `POST /v1/code-strategy/run-sandbox`
- `POST /v1/code-strategy/backtest`
- `POST /v1/code-strategy/analyze`
- `POST /v1/preflight/custom-code`
- `POST /v1/backtests/compare`
- `GET /v1/audit/events`

Legacy intent-based endpoints are disabled (HTTP 410) and must never be used:
- `/v1/brainstorm/*`
- `/v1/strategy/from-intent`
- `/v1/backtests/run*`
- `/v1/tuning/*` (intent-based variants)
- `/v1/analysis/deep-dive`
