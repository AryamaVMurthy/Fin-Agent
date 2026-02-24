# Stage 1 Progress (2026-02-23)

## Overall status

Stage-1 MVP scope is implemented end-to-end.

Beads status:
- `bd ready` -> `No open issues`
- Root epic `Fin-Agent-ysh` is closed

## Newly completed in this pass

- `Fin-Agent-ysh.3.4` fundamentals ingestion (`published_at` required) + as-of query
- `Fin-Agent-ysh.3.5` corporate actions ingestion (`effective_at` required) + explicit manifest adjustment policy
- `Fin-Agent-ysh.3.6` ratings ingestion (`revised_at` required)
- `Fin-Agent-ysh.5.1` legacy Stage-1 intent/tuning/deep-dive endpoint cleanup completed
- `Fin-Agent-ysh.6.1` live lifecycle (`activate/pause/stop`) + in-app feed
- `Fin-Agent-ysh.6.2` deterministic boundary candidates + similarity basis
- `Fin-Agent-ysh.8.3` trade blotter + signal context map artifacts
- `Fin-Agent-ysh.8.4` boundary chart + near-opportunity visualization
- `Fin-Agent-ysh.9.4` custom code backtest + patch-suggestion analysis

## API surface (incremental additions in this pass)

- `POST /v1/data/import/fundamentals`
- `POST /v1/data/import/corporate-actions`
- `POST /v1/data/import/ratings`
- `POST /v1/data/fundamentals/as-of`
- `POST /v1/code-strategy/validate`
- `POST /v1/code-strategy/save`
- `GET /v1/code-strategies`
- `GET /v1/code-strategies/{strategy_id}/versions`
- `POST /v1/code-strategy/run-sandbox`
- `POST /v1/code-strategy/backtest`
- `POST /v1/code-strategy/analyze`
- `POST /v1/preflight/world-state`
- `POST /v1/preflight/custom-code`
- `GET /v1/tuning/runs`
- `GET /v1/tuning/runs/{tuning_run_id}`
- `GET /v1/backtests/runs`
- `GET /v1/backtests/runs/{run_id}`
- `POST /v1/visualize/trade-blotter`
- `POST /v1/visualize/boundary`
- `POST /v1/live/activate`
- `POST /v1/live/pause`
- `POST /v1/live/stop`
- `GET /v1/live/feed`
- `GET /v1/live/boundary-candidates`
- `GET /v1/live/states`
- `GET /v1/live/states/{strategy_version_id}`
- `POST /v1/backtests/compare`
- `POST /v1/backtests/tax/report`
- `POST /v1/world-state/build`
- `POST /v1/world-state/completeness`
- `POST /v1/world-state/validate-pit`

## Verification evidence

Command:

```bash
env -u PYTHONHOME -u PYTHONPATH PYTHONPATH=py .venv312/bin/python -m unittest discover -s py/tests -p 'test_*.py'
```

Result:
- `Ran 51 tests in 12.050s`
- `OK`

Additional direct E2E:
- `py/tests/test_api_e2e.py` includes live path, tuning ledger path, data entity imports, code strategy backtest/analyze, and visualization checks.

## Policy lock remains enforced

- OpenCode-native OpenAI OAuth only (no external OpenAI API key flow in Fin-Agent)
- Single orchestrator agent-first runtime for Stage 1
- No standalone NLP parser layer
- No silent fallbacks on critical paths; explicit failures/remediation
