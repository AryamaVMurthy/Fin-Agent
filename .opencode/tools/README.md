# Finance Tool Surface

This directory is reserved for OpenCode tool definitions.

Current implementation route:
- Runtime API in `py/fin_agent/api/app.py`.
- Wrapper process in `apps/fin-agent/src/index.mjs`.

Planned tool mapping:
- `brainstorm.session.*`
- `brainstorm.agent_decides.*`
- `strategy.*`
- `world_state.*`
- `backtest.*`
- `visualize.*`
- `job.status`
- `auth.kite.connect`
- `auth.kite.status`
- `auth.opencode.openai.oauth.connect`
- `auth.opencode.openai.oauth.status`
- `kite.profile`
- `kite.holdings`
- `kite.instruments.sync`
- `kite.candles.fetch`
- `kite.quotes.fetch`
- `nse.quote`
- `tradingview.screener.run`
- `screener.formula.validate`
- `screener.run`
- `world-state.build`
- `world-state.validate`
- `strategy.from-intent`
- `backtest.run`
- `backtest.compare`
- `tuning.search-space.derive`
- `tuning.run`
- `analysis.deep-dive`
- `visualize.trade-blotter`
- `live.feed`
- `session.diff`
- `technicals.compute`
- `universe.resolve`
- `backtest.tax.report`
- `diagnostics.readiness`
- `providers.health`
- `session.rehydrate`
- `preflight.*`
- `audit.events`
- `code.strategy.validate`
- `code.strategy.save`
- `code.strategy.run_sandbox`

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
- `POST /v1/preflight/backtest`
- `POST /v1/preflight/tuning`
- `POST /v1/preflight/custom-code`

Strategy/backtest control endpoints currently implemented:
- `POST /v1/brainstorm/agent-decides/propose`
- `POST /v1/brainstorm/agent-decides/confirm`
- `POST /v1/backtests/compare`
- `GET /v1/audit/events`

Custom code lane endpoints currently implemented:
- `POST /v1/code-strategy/validate`
- `POST /v1/code-strategy/save`
- `POST /v1/code-strategy/run-sandbox`
