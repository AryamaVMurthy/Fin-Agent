# Finance Stage 1 Skill

Agentic-only lifecycle (mandatory):
1. Gather user constraints in natural language.
2. Generate full Python strategy code in required contract format.
3. Validate source with `code_strategy_validate`.
4. Preflight with `preflight_custom_code`.
5. Run sandbox with `code_strategy_run_sandbox`.
6. Run backtest with `code_strategy_backtest`.
7. Analyze with `code_strategy_analyze`.
8. Save final strategy with `code_strategy_save`.

No silent fallbacks. Any skipped data must include `fallback_reason`.
No manual NL parsing, no regex conversion, no hardcoded NL->intent mapper.
No manual NL parsing, no regex conversion, no hardcoded NL->intent mapper.
No manual NL parsing, no regex conversion, no hardcoded NL->intent mapper.

Python strategy contract (required):
- `prepare(data_bundle, context) -> dict`
- `generate_signals(frame, prepared, context) -> list[dict]` with `symbol` and `signal`
- `risk_rules(positions, context) -> dict`

Kite integration skill snippets:
- `auth_kite_status` -> `GET /v1/auth/kite/status`
- `GET /v1/auth/kite/connect`
- `GET /v1/kite/profile`
- `GET /v1/kite/holdings`

If `code=reauth_required`, trigger reconnect flow and stop downstream Kite calls.

OpenCode OAuth snippets:
- `GET /v1/auth/opencode/openai/oauth/status`
- `GET /v1/auth/opencode/openai/oauth/connect`

PIT/completeness snippets:
- `world_state.completeness` -> `POST /v1/world-state/completeness`
- `world_state.validate_pit` -> `POST /v1/world-state/validate-pit`

Preflight snippets:
- `preflight.world_state` -> `POST /v1/preflight/world-state`
- `preflight_custom_code` -> `POST /v1/preflight/custom-code`

Disabled legacy preflight endpoints:
- `/v1/preflight/backtest` (HTTP 410)
- `/v1/preflight/tuning` (HTTP 410)

Custom code snippets (primary strategy path):
- `code_strategy_validate` -> `POST /v1/code-strategy/validate`
- `code_strategy_save` -> `POST /v1/code-strategy/save`
- `code_strategy_run_sandbox` -> `POST /v1/code-strategy/run-sandbox`
- `code_strategy_backtest` -> `POST /v1/code-strategy/backtest`
- `code_strategy_analyze` -> `POST /v1/code-strategy/analyze`
