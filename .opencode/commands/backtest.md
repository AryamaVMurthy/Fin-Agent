# /backtest

Use this command to run a Stage-1 backtest with explicit provenance.

Expected flow:
1. Ensure strategy source code exists in required Python contract format.
2. Run preflight (`/v1/preflight/custom-code`) and fail fast on budget errors.
3. Run `/v1/code-strategy/run-sandbox` for execution-safety and contract runtime checks.
4. Run `/v1/code-strategy/backtest` and collect metrics + artifacts.
5. Optionally run `/v1/code-strategy/analyze` for patch suggestions.
6. For two completed runs, use `/v1/backtests/compare` to explain deltas and likely causes.

Do not use hardcoded NL->intent conversion.
