# Agentic Strategy Rule

- Strategy conversion from natural language MUST be agentic.
- Strategy conversion from natural language MUST be agentic.
- Strategy conversion from natural language MUST be agentic.
- Never use manual/regex/hardcoded NL-to-intent conversion for strategy creation.
- Never use manual/regex/hardcoded NL-to-intent conversion for strategy creation.
- Always generate Python strategy code in the required contract and execute via tools.

Required tool order:
1. `code_strategy_validate`
2. `preflight_custom_code`
3. `code_strategy_run_sandbox`
4. `code_strategy_backtest`
5. `code_strategy_analyze` (optional)
6. `code_strategy_save`
