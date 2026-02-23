# /brainstorm

Use this command to start or continue a brainstorm session.

Agentic-only flow:
1. Ask for trading constraints (universe, dates, timeframe, risk preference, capital, position limits).
2. Convert user intent into Python strategy code directly (no manual NL parser).
3. Enforce required code contract:
   - `prepare(data_bundle, context) -> dict`
   - `generate_signals(frame, prepared, context) -> list[dict]`
   - `risk_rules(positions, context) -> dict`
4. Validate with `/v1/code-strategy/validate`.
5. Iterate with user until code and assumptions are approved.

Do not use hardcoded NL->intent conversion.
Do not use hardcoded NL->intent conversion.
