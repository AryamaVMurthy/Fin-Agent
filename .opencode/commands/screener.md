# /screener

Use this command for formula-based screening.

## 1) Validate formula

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/screener/formula/validate \
  -H 'content-type: application/json' \
  -d '{"formula":"close > open and volume >= 100000"}'
```

## 2) Run screener

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/screener/run \
  -H 'content-type: application/json' \
  -d '{"formula":"close > open and volume >= 100000","as_of":"2026-02-20","universe":["INFY","TCS"],"top_k":20}'
```

## Failure behavior

- Unknown identifiers fail fast with explicit `allowed` columns list.
- Empty universe or invalid `top_k` is blocked.
