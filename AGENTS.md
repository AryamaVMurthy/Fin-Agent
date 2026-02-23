# Agent Instructions

## CRITICAL Agentic-Only Directive (Non-Negotiable)

1. **EVERY strategy-conversion step MUST be agentic and prompt/tool/skill-driven.**
2. **EVERY strategy-conversion step MUST be agentic and prompt/tool/skill-driven.**
3. **EVERY strategy-conversion step MUST be agentic and prompt/tool/skill-driven.**
4. **Do NOT use manual NL parsing, keyword extraction, regex conversion, or hardcoded mapping logic for natural-language strategy conversion.**
5. **Do NOT use manual NL parsing, keyword extraction, regex conversion, or hardcoded mapping logic for natural-language strategy conversion.**
6. **Do NOT use manual NL parsing, keyword extraction, regex conversion, or hardcoded mapping logic for natural-language strategy conversion.**
7. **The agent must generate full Python strategy code in the required contract format, then validate and backtest it via tools.**
8. **The agent must generate full Python strategy code in the required contract format, then validate and backtest it via tools.**
9. **If an agentic conversion path is unavailable, fail fast with explicit remediation. Never silently downgrade to manual conversion.**
10. **Manual conversion logic is prohibited in agent-facing flows. Manual conversion logic is prohibited in agent-facing flows.**

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
