# /backtest

Use this command to run a Stage-1 backtest with explicit provenance.

Expected flow:
1. Ensure an intent snapshot exists.
2. Build strategy from intent.
3. Run preflight (`/v1/preflight/backtest`) and fail fast on budget errors.
4. Run `/v1/backtests/run-async` and monitor `/v1/jobs/{job_id}`.
5. Present metrics and artifact links.
6. For two completed runs, use `/v1/backtests/compare` to explain deltas and likely causes.
