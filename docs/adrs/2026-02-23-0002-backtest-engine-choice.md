# ADR 0002: Stage 1 Backtest Engine Choice

- Date: 2026-02-23
- Status: Accepted
- Bead: `Fin-Agent-ysh.7.1`

## Context

Stage 1 requires deterministic and explainable backtesting with:
- PIT dataset manifests
- explicit cost/slippage assumptions
- reproducible metrics (Sharpe, CAGR, drawdown)
- straightforward integration with custom Python strategy lane

## Decision

Use a custom minimal deterministic engine for Stage 1 core backtests.

Implementation details:
- pandas-based vectorized signal preprocessing
- event-style portfolio simulation loop for deterministic fills and cash/position updates
- explicit slippage/cost model functions
- manifest-driven replay guarantees

## Why this option

- Full control over determinism and provenance.
- Smaller dependency surface for strict fail-fast behavior.
- Easier to enforce no-silent-fallback contract.
- Direct compatibility with custom-code strategy contract.

## Non-goals (Stage 1)

- Advanced derivatives/portfolio optimizers.
- Broker-grade execution simulation.
- Multi-venue microstructure modeling.

## Consequences

- More in-house code to maintain.
- We may later swap/augment with a library backend for specialized strategies.
- Engine API must remain stable for future adapter-based extension.

## Revisit Triggers

- If strategy scope outgrows minimal engine.
- If performance is insufficient for expected universe sizes.
- If a library backend can satisfy determinism and explainability constraints better.

