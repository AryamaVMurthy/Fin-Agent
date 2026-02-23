# /brainstorm

Use this command to start or continue a brainstorm session.

Expected flow:
1. Lock `IntentSnapshot` fields via `/v1/brainstorm/lock`.
2. Generate strategy via `/v1/strategy/from-intent`.
3. Ask user to confirm strategy assumptions before backtest.
