# Stage 1 MVP Implementation Plan (Beads-Backed)

> **For Codex/Claude:** Execute this plan bead-by-bead. Do not implement outside the active bead scope.

**Goal:** Ship a Stage-1, chat-first, agent-centric trading copilot on OpenCode server mode with PIT backtesting, explainable artifacts, strategy versioning, and optional live in-app insights (no news/social/macro).

**Architecture:** OpenCode server mode is the interaction kernel; a thin Bun/TS wrapper schedules explicit tools; heavy compute is done by Python CLIs with strict manifests. All state is local-first (SQLite + DuckDB + artifacts) with explicit provenance and no silent fallbacks.

**Tech Stack:** Bun/TypeScript (OpenCode + wrapper), Python (pandas/numpy/pyarrow + chosen backtest library), SQLite (control plane), DuckDB + Parquet (analytics), SSE events for job wakeups.

---

## Beads: Canonical Backlog

Top-level Stage-1 epic:
- `Fin-Agent-ysh` Stage 1 MVP: Agent-First Trading Copilot

Main epics:
- `Fin-Agent-ysh.1` OpenCode Wrapper + Tooling Kernel
- `Fin-Agent-ysh.3` Data + PIT World-State (Stage 1)
- `Fin-Agent-ysh.4` Strategy Lifecycle (Intake->Spec->Versioning)
- `Fin-Agent-ysh.7` Backtesting + Metrics + Compare
- `Fin-Agent-ysh.5` Tuning + Deep Analysis + Suggestions
- `Fin-Agent-ysh.8` Visualization + Artifacts
- `Fin-Agent-ysh.6` Live Insights + Boundary Candidates
- `Fin-Agent-ysh.9` Custom Python Strategy Lane (Sandboxed)
- `Fin-Agent-ysh.2` Integrations (Kite, OpenCode-native Codex/OpenAI OAuth)
- `Fin-Agent-ysh.10` Safety, Observability, and Runbooks

First vertical slice:
- `Fin-Agent-ysh.11` Tracer Bullet E2E: Chat -> CSV OHLCV -> SMA Strategy -> Backtest -> Charts -> Save

## Execution Order (Recommended)

### Phase 0: Foundational Decisions and Exploration
1. `Fin-Agent-ysh.1.1` Decision: vendor/wrap OpenCode server mode
2. `Fin-Agent-ysh.7.1` Decision: Stage-1 backtest engine/library
3. `Fin-Agent-ysh.9.1` Decision: sandbox mechanism for custom code
4. `Fin-Agent-ysh.1.2` Explore OpenCode server mode endpoints and extension points

Deliverable: ADR(s) in `docs/adrs/` that make later implementation unblocked and deterministic.

### Phase 1: Tooling Kernel (Agent-First Runtime)
5. `Fin-Agent-ysh.1.3` Wrapper skeleton in `apps/fin-agent/`
6. `Fin-Agent-ysh.1.7` Local state layout + `.gitignore` for `.finagent/`
7. `Fin-Agent-ysh.1.5` `.opencode/` scaffolding (tools/skills/commands/rules)
8. `Fin-Agent-ysh.1.4` Job queue + tool runner + SSE wakeups
9. `Fin-Agent-ysh.10.1` Structured logs + trace IDs
10. `Fin-Agent-ysh.10.2` Audit ledger for decisions/tool calls
11. `Fin-Agent-ysh.1.6` Preflight runtime estimation + budgets
12. `Fin-Agent-ysh.10.3` Enforce preflight budgets and safe aborts

Deliverable: a working OpenCode-based chat surface that can schedule a long-running Python tool and get agent re-entry upon completion.

### Phase 2: Stage-1 Data (Local Import First) + PIT Core
13. `Fin-Agent-ysh.3.1` Instrument master + universe resolver
14. `Fin-Agent-ysh.3.2` OHLCV import pipeline (CSV/Parquet)
15. `Fin-Agent-ysh.3.3` Technicals compute pipeline (indicator set)
16. `Fin-Agent-ysh.3.8` PIT world_state.build + manifest hashing
17. `Fin-Agent-ysh.3.9` PIT validate + leak check gates
18. `Fin-Agent-ysh.3.7` Data completeness + explicit skip reporting

Optional expansion (still Stage 1):
- `Fin-Agent-ysh.3.4` Fundamentals ingestion schema
- `Fin-Agent-ysh.3.5` Corporate actions + adjustment policy
- `Fin-Agent-ysh.3.6` Ratings schema

Deliverable: deterministic as-of world simulation with strict PIT validation by default.

### Phase 3: Strategy Lifecycle and Versioning
19. `Fin-Agent-ysh.4.1` Interactive strategy-intake session + immutable intake snapshot
20. `Fin-Agent-ysh.4.3` StrategySpec schema + validation + explainability contract
21. `Fin-Agent-ysh.4.4` Strategy library (save/version/diff/list + rerun)
22. `Fin-Agent-ysh.4.2` Assisted-default mode + confirmation/edit loop

Deliverable: user can chat, lock intent, produce StrategySpec, save versions, and rerun a chosen version.

### Phase 4: Backtesting + Metrics + Core Visualization
23. `Fin-Agent-ysh.7.2` code-strategy backtest integrated with PIT world state (deterministic manifests)
24. `Fin-Agent-ysh.7.3` Metrics + benchmark compare
25. `Fin-Agent-ysh.8.1` Artifact store + indexing
26. `Fin-Agent-ysh.8.2` Equity + drawdown charts
27. `Fin-Agent-ysh.7.4` Compare runs and versions

Deliverable: backtest results are explainable, artifacted, comparable, and replayable.

### Phase 5: Tracer Bullet Completion (E2E)
28. `Fin-Agent-ysh.11` Tracer bullet E2E demo and acceptance

Deliverable: the smallest fully usable end-to-end system works (chat->import->SMA spec->PIT->backtest->charts->save->rerun).

### Phase 6: Tuning + Deep Analysis + Advanced Visualization
29. `Fin-Agent-ysh.5.1` Search-space derivation (interactive tuning knobs)
30. `Fin-Agent-ysh.5.2` Tuning runner (budgeted)
31. `Fin-Agent-ysh.5.3` Deep-dive report + improvement suggestions
32. `Fin-Agent-ysh.8.3` Trade blotter + signal context maps
33. `Fin-Agent-ysh.8.4` Boundary charts + near-opportunity viz

Deliverable: user can tune and understand why the strategy behaves as it does.

### Phase 7: Live Insights and Boundary Candidates (In-App Only)
34. `Fin-Agent-ysh.6.2` Boundary candidate engine + similarity suggestions
35. `Fin-Agent-ysh.6.1` Live activate/pause/stop + in-app feed

Deliverable: saved strategies can produce an insights feed and “near-boundary” suggestions without autotrading.

### Phase 8: Custom Code Lane (Sandboxed)
36. `Fin-Agent-ysh.9.2` Code strategy scaffolding + contract validation
37. `Fin-Agent-ysh.9.3` Sandboxed code runner with resource limits
38. `Fin-Agent-ysh.9.4` Code backtest + analysis + patch suggestions

Deliverable: user can provide Python code, run it safely, and get improvement suggestions.

### Phase 9: External Integrations and Runbooks
39. `Fin-Agent-ysh.2.1` OpenCode-native Codex/OpenAI OAuth connect + status
40. `Fin-Agent-ysh.2.2` Kite connect + status
41. `Fin-Agent-ysh.10.4` Operator runbook

Deliverable: connectors are wired safely and operators have a troubleshooting guide.

---

## Repo Structure to Implement (Source of Truth)

- `Docs/repo-structure.md`
- `Docs/DesigndocS1.md`

---

## Working Agreement (Implementation Discipline)

- Beads is the backlog. Do not create GitHub issues for this phase.
- No silent fallbacks: every skip/scope reduction must carry `fallback_reason` and appear in outputs.
- No standalone NLP intent-parser layer in Stage 1. Intent and reasoning stay inside the orchestrator agent.
- No keyword/regex-first strategy reasoning. Use agent + tools/evaluators/control loops.
- Heavy tools must run via jobs and must pass preflight budgets first.
- Every run must emit a manifest and provenance record suitable for replay and audit.
- Codex/OpenAI integration policy: OpenCode native OAuth only (`/connect` or `opencode auth login openai`); do not add external OpenAI key flow to Fin-Agent.
