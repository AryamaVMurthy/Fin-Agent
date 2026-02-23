# /providers

Use this command for provider data fetch/sync actions.

## Kite instruments sync

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/kite/instruments/sync \
  -H 'content-type: application/json' \
  -d '{"exchange":"NSE","max_rows":20000}'
```

## Kite candles fetch

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/kite/candles/fetch \
  -H 'content-type: application/json' \
  -d '{"symbol":"INFY","instrument_token":"408065","interval":"5minute","from_ts":"2026-02-20 09:15:00","to_ts":"2026-02-20 15:30:00","persist":true}'
```

## NSE quote

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/nse/quote \
  -H 'content-type: application/json' \
  -d '{"symbol":"INFY"}'
```

## TradingView scan

```bash
curl -sS -X POST http://127.0.0.1:8080/v1/tradingview/screener/run \
  -H 'content-type: application/json' \
  -d '{"where":[],"columns":["name","close","volume"],"limit":25}'
```

Requires `FIN_AGENT_TRADINGVIEW_SESSIONID` in environment.
