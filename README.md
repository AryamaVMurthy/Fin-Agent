# Fin-Agent

Stage-1 implementation (agent-first trading copilot) is now end-to-end complete for Stage-1 scope:

1. Chat-first intent capture (`interactive` + `assistant-default` modes).
2. Data import pipelines:
   - OHLCV (`.csv`/`.parquet`)
   - fundamentals (strict `published_at`)
   - corporate actions (strict `effective_at`)
   - analyst ratings (strict `revised_at`)
3. PIT world-state build with strict validation, leak checks, completeness reporting, and explicit adjustment policy.
4. Deterministic backtests with artifacts:
   - equity curve
   - drawdown
   - trade blotter (entry/exit/pnl/reason codes)
   - signal context map
5. Compare runs, tuning ledger review, and analysis diagnostics.
6. Custom Python strategy lane:
   - contract validation
   - sandbox execution (CPU/memory/time limits)
   - code backtest
   - patch suggestions only (no auto-apply)
7. Live lifecycle + in-app insights:
   - activate/pause/stop
   - insight feed
   - deterministic boundary candidates + boundary chart visualization
8. Integrations:
   - Kite connect/status/callback/profile/holdings
   - Kite instrument/candle/quote fetch endpoints
   - NSE quote endpoint
   - TradingView screener endpoint (session-based, optional)
   - OpenCode-native OpenAI OAuth status/connect helper
9. Tax overlay + hardening:
   - optional India STCG/LTCG + charges tax report endpoint
   - session snapshot/rehydrate + context delta persistence
   - provider health, observability metrics, readiness diagnostics endpoints
10. Observability:
   - structured logs with trace IDs
   - audit event ledger
   - runbook in `docs/runbooks/stage1-operator.md`

## Runtime

- Python API: `py/fin_agent/api/app.py`
- Python CLI: `py/fin_agent/cli.py`
- Wrapper skeleton: `apps/fin-agent/src/index.mjs`

## Local setup

```bash
env -u PYTHONHOME -u PYTHONPATH /usr/bin/python3 -m venv .venv312
env -u PYTHONHOME -u PYTHONPATH .venv312/bin/pip install duckdb fastapi uvicorn pydantic
```

## Credentials

Use `Docs/credentials.md` for exact local credential setup.
Quick start:

```bash
cp .env.example .env.local
```

OpenAI auth for this repo:
- Preferred: OpenCode native OAuth (`opencode auth login openai` or `/connect` in TUI).
- Optional: `OPENAI_API_KEY` in `.env.local` for API-key based provider auth.

OpenCode auth/server helper scripts:

```bash
./scripts/opencode-auth-openai.sh
./scripts/opencode-serve.sh
```

Linux packaging and diagnostics scripts:

```bash
./scripts/install-linux.sh
./scripts/gen-encryption-key.sh --write
./scripts/doctor.sh
./scripts/start-all.sh
./scripts/publish-readiness.sh
./scripts/release-tui.sh --version 0.1.0
./scripts/e2e-smoke.sh
./scripts/e2e-full.sh
./scripts/e2e-full.sh --with-providers --with-opencode --runtime-home ./.finagent
```

NPM wrapper CLI:

```bash
cd apps/fin-agent
npm install
node src/cli.mjs --help
```

Release runbook:
- `docs/runbooks/publish-stage1.md`

## Run API

```bash
./scripts/serve.sh
```

Kite auth endpoints:

```bash
curl -sS http://127.0.0.1:8080/v1/auth/kite/status
curl -sS http://127.0.0.1:8080/v1/auth/kite/connect
```

## Run tests

```bash
env -u PYTHONHOME -u PYTHONPATH PYTHONPATH=py .venv312/bin/python -m unittest discover -s py/tests -p 'test_*.py'
```

Current verification baseline:
- Full suite passes: `81` tests.
