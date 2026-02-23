# ADR 0003: Sandbox Mechanism for Custom Python Strategies

- Date: 2026-02-23
- Status: Accepted
- Bead: `Fin-Agent-ysh.9.1`

## Context

Stage 1 must run user-supplied Python strategy code safely, without Docker as a hard dependency.

Requirements:
- fail closed if sandbox cannot be guaranteed
- resource limits (CPU/memory/time)
- read-only access to dataset snapshots
- isolated writable artifacts directory
- no secret leakage

## Decision

Use a two-layer sandbox policy:

1. Preferred runtime isolation: `bubblewrap` (`bwrap`) if present.
2. Mandatory resource controls in all cases:
   - `RLIMIT_CPU`
   - `RLIMIT_AS`
   - wall-clock timeout
3. No-network execution by default.
4. If `bwrap` is unavailable, custom-code execution is disabled with explicit error and remediation.

## Why this option

- Works without Docker.
- `bwrap` is widely available on Linux and suited for filesystem namespace isolation.
- Fail-closed behavior satisfies strict safety requirements.

## Consequences

- Host dependencies must include `bwrap` for custom-code lane.
- Different OS targets need equivalent isolation backends in future.
- Diagnostics must clearly show why execution was rejected.

## Revisit Triggers

- Multi-platform sandbox support requirements.
- Need for stronger seccomp/apparmor profiles.
- Operational constraints that require a managed container runtime.

