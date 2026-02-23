# Repo Structure (Stage 1 Target)

This repo is intended to be a GitHub-maintained monorepo that wraps OpenCode server mode and adds a finance tool layer (Stage 1 scope).

## Top-Level Layout

```
.
├─ .opencode/                     # OpenCode project extensions (tools/skills/commands/rules)
│  ├─ tools/                       # Tool definitions (TS) that call Python/CLI jobs
│  ├─ skills/                      # Reusable workflow docs for the agent
│  ├─ commands/                    # Slash commands to trigger workflows
│  └─ rules/                       # Safety, timeouts, budgets, policy prompts
│
├─ apps/
│  └─ fin-agent/                   # Bun/TS wrapper app around opencode server mode
│     ├─ src/
│     ├─ package.json
│     └─ bun.lockb
│
├─ vendor/
│  └─ opencode/                    # OpenCode upstream (submodule or vendored fork)
│
├─ py/                             # Python workspace for finance compute
│  ├─ fin_agent/                   # Python package: data, PIT, backtest, tuning, viz, sandbox
│  │  ├─ __init__.py
│  │  ├─ cli/                      # Click/Typer CLIs invoked by tools
│  │  ├─ data/                     # ingest/import, providers, schemas
│  │  ├─ pit/                      # world-state build + leak checks
│  │  ├─ strategy/                 # StrategySpec, validation, templates
│  │  ├─ backtest/                 # backtest engine integration + metrics
│  │  ├─ tuning/                   # hyperparam search + constraints
│  │  ├─ viz/                      # charts + reports -> artifacts
│  │  ├─ sandbox/                  # custom-code runner + resource limits
│  │  └─ storage/                  # sqlite/duckdb IO, manifests, hashing
│  ├─ pyproject.toml
│  └─ uv.lock (or poetry.lock)
│
├─ scripts/                        # Bash helpers for dev and ops
│  ├─ dev.sh
│  ├─ serve.sh
│  └─ worker.sh
│
├─ docs/                           # Living docs (implementation plans, ADRs)
│  ├─ plans/
│  └─ adrs/
│
├─ Docs/                           # Legacy docs already in repo (keep, migrate later)
│
├─ .finagent/                      # Local runtime state (NOT committed)
│  ├─ state.sqlite                 # control-plane DB
│  ├─ analytics.duckdb             # analytic DB
│  ├─ artifacts/                   # charts/reports/manifests (files)
│  └─ logs/
│
├─ .beads/                         # Beads tracking (committed if team wants shared backlog)
├─ .gitignore
└─ README.md
```

## What Lives Where

- `.opencode/`: the “agent-first” layer.
  - Tools are small TS shims that schedule jobs and call Python CLIs.
  - Skills/commands codify the allowed workflows: brainstorm, build strategy, backtest, tune, analyze, visualize, save, activate.

- `apps/fin-agent/`: the wrapper service.
  - Responsible for: auth wiring, tool routing, job queue/worker coordination, SSE event bridging.
  - Keeps OpenCode as the base runtime and UI.

- `vendor/opencode/`: OpenCode upstream.
  - Default: keep as a git submodule.
  - If core modifications are required: fork and vendor here, with a clear ADR.

- `py/fin_agent/`: finance compute.
  - All PIT simulation, data ingestion, indicator compute, backtests, tuning, and charting lives here.

- `.finagent/`: local state.
  - SQLite: strategy versions, intent snapshots, run manifests, tool call audit.
  - DuckDB: OHLCV/features/trades/equity curves.
  - Artifacts: reports/charts/manifests exported by jobs.

## Git Hygiene

- Commit: code (`apps/`, `py/`, `.opencode/`, `docs/`, `Docs/`).
- Do not commit: `.finagent/` (runtime state) and large raw datasets unless explicitly intended.
- Decide whether `.beads/` is committed:
  - Personal-only planning: keep it local and exclude via gitignore.
  - Team-shared planning: commit `.beads/` so backlog is shared.

