# ADR 0001: OpenCode Wrapper Strategy

- Date: 2026-02-23
- Status: Accepted
- Bead: `Fin-Agent-ysh.1.1`

## Context

Stage 1 must be agent-first and chat-first, with OpenCode server mode as the runtime base and finance behavior layered as tools. We need a strategy that keeps upstream compatibility while enabling local finance workflows.

Validated upstream references (2026-02-23):
- `anomalyco/opencode` default branch: `dev`
- server implementation: Hono-based HTTP API
- OpenAPI endpoint: `/doc`
- global event stream: `/global/event`
- basic auth support: `OPENCODE_SERVER_PASSWORD` (+ optional username)

## Decision

Use a wrapper-first architecture:

1. Keep OpenCode as an external runtime process (`opencode serve`), not a hard fork.
2. Build a small `apps/fin-agent` wrapper service for:
   - tool orchestration
   - long-running job tracking
   - finance-specific API endpoints
   - event bridge to/from OpenCode sessions
3. Keep finance compute in Python under `py/fin_agent`.
4. Add `.opencode` project-level extensions in this repo for commands/skills/tools.

## Why this option

- Lowest upgrade friction with upstream OpenCode.
- Avoids immediate fork maintenance.
- Preserves strict agent-first design by routing all finance operations through tools.
- Supports future fallback to a fork only when upstream extension points are insufficient.

## Consequences

- Wrapper must manage lifecycle/config for OpenCode process.
- Contract tests are needed between wrapper and OpenCode server endpoints.
- If upstream API shapes break, wrapper adapters must be updated.

## Revisit Triggers

- If required hooks cannot be implemented without patching OpenCode internals.
- If session/event APIs change incompatibly.
- If a stable plugin API is added upstream that can replace wrapper glue.

