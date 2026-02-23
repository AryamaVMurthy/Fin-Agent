# /diagnostics

Use this command to verify deploy/readiness and provider health.

## Readiness

```bash
curl -sS http://127.0.0.1:8080/v1/diagnostics/readiness
```

## Observability metrics

```bash
curl -sS http://127.0.0.1:8080/v1/observability/metrics
```

## Provider health

```bash
curl -sS http://127.0.0.1:8080/v1/providers/health
```

## Tax report

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/backtests/tax/report \
  -H 'content-type: application/json' \
  -d '{"run_id":"<run-id>","enabled":true,"stcg_rate":0.20,"ltcg_rate":0.125}'
```
