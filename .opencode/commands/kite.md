# /kite

Use this command for Kite account actions.

## Flows

### 1) Check auth status

```bash
curl -sS http://127.0.0.1:8080/v1/auth/kite/status
```

### 2) Connect account

```bash
curl -sS http://127.0.0.1:8080/v1/auth/kite/connect
```

Open the returned `connect_url` and complete login.

### 3) Fetch profile

```bash
curl -sS http://127.0.0.1:8080/v1/kite/profile
```

### 4) Fetch holdings

```bash
curl -sS http://127.0.0.1:8080/v1/kite/holdings
```

## Failure behavior

- If session/token is missing or expired, API returns `401` with `code=reauth_required`.
- No silent fallback; user must reconnect.
