# Finance Stage 1 Skill

Always run the strategy lifecycle in this order:
1. brainstorm lock
2. strategy build
3. world state build
4. backtest run
5. metrics + artifacts
6. save version

No silent fallbacks. Any skipped data must include `fallback_reason`.

Kite integration skill snippets:
- `auth.kite.status` -> `GET /v1/auth/kite/status`
- `auth.kite.connect` -> `GET /v1/auth/kite/connect`
- `kite.profile` -> `GET /v1/kite/profile`
- `kite.holdings` -> `GET /v1/kite/holdings`

If `code=reauth_required`, trigger reconnect flow and stop downstream Kite calls.

OpenCode OAuth snippets:
- `auth.opencode.openai.oauth.status` -> `GET /v1/auth/opencode/openai/oauth/status`
- `auth.opencode.openai.oauth.connect` -> `GET /v1/auth/opencode/openai/oauth/connect`

PIT/completeness snippets:
- `world_state.completeness` -> `POST /v1/world-state/completeness`
- `world_state.validate_pit` -> `POST /v1/world-state/validate-pit`

Preflight snippets:
- `preflight.world_state` -> `POST /v1/preflight/world-state`
- `preflight.backtest` -> `POST /v1/preflight/backtest`
- `preflight.tuning` -> `POST /v1/preflight/tuning`
- `preflight.custom_code` -> `POST /v1/preflight/custom-code`

Custom code snippets:
- `code.strategy.validate` -> `POST /v1/code-strategy/validate`
- `code.strategy.save` -> `POST /v1/code-strategy/save`
- `code.strategy.run_sandbox` -> `POST /v1/code-strategy/run-sandbox`
