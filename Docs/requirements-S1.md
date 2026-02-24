# Phase 1 Complete MVP Plan: Agent-First Chat Trading Copilot (End-to-End, Usable)

## 1. Brief Summary
Build a chat-first system (OpenCode/OpenClaw style) with one main orchestrator agent that uses tools for everything.  
Phase 1 delivers complete strategy lifecycle: interactive strategy intake, strategy creation, save/version, PIT world-state build (time-travel), backtest, tuning ledger review, visualization, live in-app insights/alerts, boundary-near suggestions, and persistent context/memory.

Latest locked additions included:
- Interactive strategy intake flow.
- Optional assisted-default mode (agent fills defaults, user confirms).
- Custom Python strategy lane (sandboxed).
- Strong context/memory persistence and replay.
- Stage 1 scope only (no news/social/macro ingestion yet).

---

## 2. Product Boundaries

## In Scope (Phase 1)
- Chat-native UX with minimal settings.
- NSE equity universe (structured selectors + watchlist support).
- Data families: OHLCV/technicals, fundamentals/financials, corporate actions, ratings.
- Point-in-time world simulation at each historical timestamp for backtests.
- Deterministic run manifests and leak checks.
- Strategy versioning + edit anytime + rerun anytime.
- Live in-app signals and near-boundary opportunities.
- Kite account connect.
- Codex/OpenAI connect through OpenCode native OAuth only (no external API key flow in Fin-Agent).
- Custom Python strategy execution in isolated sandbox.
- Agent-generated strategy improvement suggestions and patch suggestions.

## Out of Scope (Phase 1)
- News sentiment, rumors, social media, macro/Fed inputs.
- Auto-order execution.
- Multi-agent autonomous decomposition as default runtime.
- Multi-broker routing.

---

## 3. App Surfaces (All Parts of the App)

## 3.1 Chat Console (Primary)
- Natural language + slash commands.
- Full audit trace of agent actions and tool calls.
- Progressive responses (questionnaire, run status, results, next actions).

## 3.2 Settings Panel (Minimal)
- Universe defaults.
- Timeframe defaults.
- Benchmark + cost model.
- PIT strictness (default hard block).
- Strategy-intake mode default (`interactive` or assisted-default).

## 3.3 Strategy Library
- Drafts, saved versions, diffs, cloned variants.
- Strategy metadata: objective, constraints, run history, active state.
- “Save anytime” from any workflow state.

## 3.4 Runs Workspace
- Backtest runs, compare runs, tuning runs.
- Artifacts: equity, drawdown, trades, exposures, leak report, world-state manifest.

## 3.5 Visualization Workspace
- Equity curve, drawdown, trade timeline, signal map, indicator overlays.
- Strategy boundary charts and “close opportunity” list.

## 3.6 Live Insights Feed
- Active strategy suggestions (buy/sell/hold/watch).
- Boundary-near and similar pattern alerts.
- In-app only notifications.

## 3.7 Accounts/Connectors
- Kite connect/status/refresh.
- Codex/OpenAI connect/status via OpenCode native OAuth (`/connect` or `opencode auth login openai`).

---

## 4. Agent-Centric Runtime Design

## Core Principle
- One main agent handles all user intents.
- All actions happen through explicit tools.
- Event-driven loop: user input -> tool call -> result -> agent re-entry -> next step.
- No standalone NLP intent-parser pipeline in Stage 1; reasoning/orchestration stays agent-driven.
- No keyword/regex-first decision logic for strategy reasoning; use agent + tool/evaluator loops.

## Phase 1 Agent Modes
- `interactive_user_guided`: asks all required trade design questions.
- `assisted-default`: agent proposes full parameter set + decision summary; user confirms or edits.

## Hard Constraints
- No hidden fallback.
- No fake data.
- No silent defaults in critical paths.
- Missing critical data => explicit error + remediation.
- Any non-critical scope reduction must include explicit `fallback_reason` surfaced to the user.

---

## 5. Mandatory Interactive Strategy Intake Specification

## 5.1 Intake Question Sets
1. Portfolio structure:
- Max open positions.
- Position sizing scheme.
- Max position weight.
- Sector concentration cap.
- Cash floor.

2. Trading horizon:
- Intraday/swing/weeks/months/long-term year+.
- Data timeframe.
- Holding period target.
- Rebalance frequency.

3. Buy/sell logic:
- Buy trigger family.
- Sell trigger family.
- Numeric thresholds.
- Confirmation requirements.
- Time-stop rules.

4. Risk style/objective:
- Safe/balanced/aggressive/max risk-reward.
- Primary optimization target (Sharpe/CAGR/Sortino/Calmar).
- Max drawdown tolerance.
- Stop-loss/take-profit schema.
- Exposure and leverage policy.

5. Universe constraints:
- Base universe.
- Liquidity rules.
- Market cap/fundamental/rating filters.
- Include/exclude lists.

6. Execution assumptions:
- Benchmark.
- Cost/slippage model.
- Execution timing assumptions.

## 5.2 Strategy Intake Lifecycle
- `start -> ask -> answer -> revise -> summarize -> lock`.
- Lock creates immutable `IntentSnapshot`.
- Strategy generation requires locked snapshot.

## 5.3 Assisted-Default Option
- Agent fills unresolved fields using policy templates.
- Returns `DecisionCard` with:
- chosen value,
- source (`agent_assumed`),
- rationale,
- confidence,
- expected impact.
- User can confirm all, edit specific fields, or switch to interactive mode.

---

## 6. Data and Time-Travel World Simulation

## 6.1 Data Entities
- Instrument master.
- OHLCV candles.
- Fundamentals/financials with `published_at`.
- Corporate actions with `effective_at`.
- Ratings/revisions with timestamp lineage.

## 6.2 PIT World-State Build
- Build historical “as-of” state from immutable snapshots only.
- Each backtest timestamp resolves only data known at that timestamp.
- Manifest includes all dataset hashes and policies used.

## 6.3 Leak and Readiness Gates
- `world_state.validate_pit`
- `world_state.leak_check`
- Any critical violation blocks backtest/live activation in strict mode (default).

---

## 7. Strategy Lifecycle (End-to-End)

1. User starts chat with idea.
2. Agent runs strategy intake session (interactive or assisted-default).
3. Agent creates explainable `StrategySpec`.
4. User reviews and saves version anytime.
5. Agent resolves universe and builds world state.
6. Agent runs backtest.
7. Agent visualizes metrics/artifacts.
8. Agent runs tuning from user objective/risk constraints.
9. Agent gives deep analysis + improvement suggestions.
10. User applies edits and saves new version.
11. User activates live insights.
12. Agent continues context-aware updates and boundary suggestions.

---

## 8. Custom Python Strategy Lane (Added)

## 8.1 Purpose
Allow user-written Python strategy logic to plug into same lifecycle: validate -> backtest -> analyze -> visualize -> improve.

## 8.2 Contract
Strict plugin interface with flexible internals:
- `prepare(data_bundle, context)`
- `generate_signals(frame, state, context)`
- `risk_rules(positions, context)`
- Structured output schema required.

Rule:
- Zero values allowed where typed and valid.
- Unlimited customization inside contract boundaries.

## 8.3 Execution
- Isolated sandbox worker.
- Resource limits (CPU/memory/time).
- Read-only mounted snapshots.
- Artifact-only writable output.
- No secret access.
- Fail fast on runtime or contract errors.

## 8.4 Improvement Workflow
- Agent performs code-aware analysis.
- Returns patch suggestions only (no auto-apply).
- User approves and versions code strategy.

---

## 9. Tool Registry (Canonical)

## Orchestration and UX
- `tools.list`
- `job.status`
- `artifact.fetch`

## Strategy workflow
- `code.strategy.validate`
- `code.strategy.save`
- `code.strategy.list`
- `code.strategy.versions`
- `code.strategy.run_sandbox`
- `code.strategy.backtest`
- `code.strategy.analyze`

## Accounts
- `auth.kite.connect`
- `auth.kite.status`
- `auth.opencode.openai.oauth.connect`
- `auth.opencode.openai.oauth.status`

## Strategy core
- `strategy_spec.validate`
- `strategy_version.create`
- `strategy_version.diff`
- `strategy.improve.suggest`
- `strategy.version.list`

## Data + universe
- `universe.resolve`
- `universe.snapshot.get`
- `data.instruments.sync`
- `data.ohlcv.fetch`
- `data.fundamentals.fetch`
- `data.corp_actions.fetch`
- `data.ratings.fetch`
- `data.completeness.report`

## PIT and simulation
- `world_state.build`
- `world_state.validate_pit`
- `world_state.leak_check`

## Compute and analysis
- `backtest.list`
- `backtest.compare`
- `tuning.list`
- `tuning.detail`
- `code.backtest.run`
- `code.analyze`

## Visualization
- `visualize.equity_curve`
- `visualize.drawdown`
- `visualize.signal_context`
- `visualize.feature_contrib`

## Live insights
- `live.activate`
- `live.pause`
- `live.stop`
- `live.signals.next`
- `live.boundary_candidates`

## Custom code
- `code.strategy.create`
- `code.strategy.version.create`
- `code.strategy.validate`
- `code.backtest.run`
- `code.analysis.deep_dive`
- `code.strategy.improvements`
- `code.patch.suggest`
- `code.visualize.metrics`

## Context and memory
- `memory.context.get`
- `memory.context.pin`
- `memory.context.clear_scope`

---

## 10. Core Types and Public Interfaces

## Domain types
- `IntentSnapshot`
- `DecisionCard`
- `StrategySpec`
- `StrategyVersion`
- `UniverseSpec`
- `UniverseSnapshot`
- `DatasetSnapshot`
- `WorldStateManifest`
- `LeakCheckReport`
- `BacktestRun`
- `BacktestArtifacts`
- `TuningRun`
- `LiveState`
- `SignalInsight`
- `CodeStrategyArtifact`
- `CodeStrategyVersion`
- `CodeExecutionRun`
- `CodePatchSuggestion`
- `SessionContext`
- `DecisionLog`

## API surface (v1)
- `POST /v1/chat/respond`
- `GET /v1/tools`
- `POST /v1/tools/{tool_id}/run`
- `POST /v1/code-strategy/validate`
- `POST /v1/code-strategy/save`
- `GET /v1/code-strategies`
- `GET /v1/code-strategies/{strategy_id}/versions`
- `POST /v1/universe/resolve`
- `POST /v1/world-state/completeness`
- `POST /v1/world-state/validate-pit`
- `POST /v1/world-state/build`
- `POST /v1/preflight/world-state`
- `POST /v1/preflight/custom-code`
- `POST /v1/code-strategy/run-sandbox`
- `POST /v1/code-strategy/backtest`
- `POST /v1/code-strategy/analyze`
- `GET /v1/backtests/runs`
- `GET /v1/backtests/runs/{run_id}`
- `GET /v1/tuning/runs`
- `GET /v1/tuning/runs/{tuning_run_id}`
- `POST /v1/live/activate`
- `POST /v1/live/pause`
- `POST /v1/live/stop`
- `GET /v1/live/feed`
- `GET /v1/live/states`
- `GET /v1/live/states/{strategy_version_id}`
- `GET /v1/live/boundary-candidates`
- `GET /v1/artifacts/{artifact_id}`

---

## 11. Context and Memory Design (Critical)

## Layers
- Session memory: active chat/thread state.
- Durable strategy memory: strategies, versions, runs, manifests.
- Decision memory: all user and agent assumptions with provenance.
- Retrieval index: IDs/tags/timestamps for deterministic rehydration.

## Required per-field provenance
- `value`
- `source` (`user_explicit`, `agent_assumed`)
- `confidence`
- `justification`
- `last_modified_by`
- `timestamp`

## Guarantees
- Every tool call consumes and emits context delta.
- Crash/restart can resume exact workflow.
- Replay yields same parameterization and manifest lineage.

---

## 12. Explainability Contract (Human-Review Ready)
Every major result returns:
- Human summary.
- Machine spec JSON.
- Data provenance and snapshot hashes.
- Why decision was made.
- Confidence and risk notes.
- What to change next (actionable suggestions).
- For live mode: boundary-near opportunities and reason codes.

---

## 13. Security, Reliability, and Observability

## Security
- Secrets stored encrypted server-side only.
- No tokens in logs/artifacts.
- Sandbox isolation for custom code.
- Strict input/output schema validation.

## Reliability
- Idempotent tool invocation with request IDs.
- Deterministic seeds for backtest/tuning.
- Explicit dependency checks before compute.

## Observability
- Structured logs per tool call and decision.
- Trace IDs through agent and tools.
- Metrics: latency, failure class, gate failures, replay consistency.
- Audit ledger for all saves/activations.

---

## 14. Complete Functional Test Matrix

## Strategy intake and intent
1. Full interactive intake completion and lock.
2. Assisted-default suggestion generation and confirmation.
3. Mode switching without context loss.
4. Blocking behavior when required fields missing.

## Strategy and versioning
1. Save-anytime creates immutable versions.
2. Version diff accuracy.
3. Edit and rerun from older versions.

## PIT/data gates
1. Missing timestamped fundamentals blocks run.
2. Missing corporate action effective dates blocks run.
3. Leak-check failure blocks backtest/live (strict mode).

## Backtest/tuning/analysis
1. Deterministic re-run equality check.
2. Weighted objective tuning respects constraints.
3. Comparison report across runs and versions.
4. Agent suggestions change expected metrics directionally.

## Visualization
1. Equity/drawdown/trade charts generated.
2. Signal context chart reflects thresholds and nearby candidates.

## Live insights
1. Activate/pause/stop lifecycle.
2. Signal emission for direct and boundary-near cases.
3. In-app alert feed consistency.

## Custom code
1. Contract validation success/failure.
2. Sandbox runtime limits enforced.
3. Patch suggestions produced with rationale.
4. No auto-apply without user action.

## Context/memory
1. Resume session with exact current state.
2. Provenance fields present for all critical parameters.
3. Context compaction and rehydration consistency.

---

## 15. Delivery Stages (Implementation Plan)

## Stage A: Core platform foundation
- FastAPI gateway, tool registry, auth connectors, context store, audit schema.

## Stage B: Data and PIT readiness
- Instrument/OHLCV/fundamentals/corp-actions/ratings ingestion.
- Completeness and PIT validation tools.
- World-state and leak-check engine.

## Stage C: Agent workflows and strategy lifecycle
- Strategy-intake modes, intent locking, strategy spec generation, versioning.

## Stage D: Compute, tuning, and explainability
- Backtest engine, tuning engine, compare, deep analysis, explainability outputs.

## Stage E: Visualization and live insights
- Chart tools, live signal loop, boundary candidate logic, in-app alerts.

## Stage F: Custom code lane
- Sandbox runtime, code contract validator, code backtests, patch suggestions.

## Stage G: Hardening and release
- Determinism tests, security tests, observability dashboards, runbooks, rollback gates.

---

## 16. Explicit Assumptions and Defaults
- Default strategy-intake mode: `interactive_user_guided`.
- Assisted-default mode available at all times.
- PIT strict mode default: hard block on critical missing dependencies.
- Alerts default: in-app only.
- Stage 1 runtime: single orchestrator agent.
- Stage 1 data scope excludes news/social/macro.
- Strategy execution remains advisory, not auto-trading.
- Custom code improvement mode default: patch suggestions only.
