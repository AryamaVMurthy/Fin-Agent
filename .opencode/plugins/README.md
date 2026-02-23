# Fin-Agent Opencode Plugins

- `finagent-orchestrator.ts`: orchestration hooks, compaction context injection, and session snapshot persistence.
- `../tools/finagent-tools.ts`: finance tool surface backed by Fin-Agent API.

Both are intended to run inside Opencode server mode as local plugins.
Registration is declared in `.opencode/opencode.jsonc`.
