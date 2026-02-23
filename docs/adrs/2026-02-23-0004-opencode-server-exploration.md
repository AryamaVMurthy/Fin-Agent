# ADR 0004: OpenCode Server Exploration Notes (Stage 1)

- Date: 2026-02-23
- Status: Accepted
- Bead: `Fin-Agent-ysh.1.2`

## Scope

Capture verified runtime/API details needed for wrapper integration.

## Verified Points

From live docs and upstream source (`anomalyco/opencode`, `dev`):

- Server mode command:
  - `opencode serve [--port] [--hostname] [--cors ...]`
- OpenAPI spec:
  - `GET /doc`
- Health endpoint:
  - `GET /global/health`
- Global SSE stream:
  - `GET /global/event`
- Optional HTTP basic auth:
  - `OPENCODE_SERVER_PASSWORD`
  - `OPENCODE_SERVER_USERNAME` (default `opencode`)
- Server implementation stack:
  - Hono routes + openapi generation

## Integration Plan for This Repo

- Wrapper assumes OpenCode is available as a process and discovers it by host/port.
- Wrapper preflight checks `/global/health` before accepting finance jobs.
- Wrapper stores OpenCode connection details in config and fails fast on mismatch.
- Event bridge subscribes to `/global/event` for cross-session updates.

## Open Questions

- Final transport contract for session-specific event wakeups.
- Whether `.opencode/tools` should call wrapper endpoints directly or shell scripts.

