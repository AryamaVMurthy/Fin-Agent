# Credentials Setup (Exact Process)

This is the single place to keep local credentials for Fin-Agent.

## 1) Create local secrets file

From repo root:

```bash
cp .env.example .env.local
```

` .env.local` is gitignored and stays on your machine.

## 2) Fill required values in `.env.local`

### OpenCode server auth (only if you protect `opencode serve`)

```bash
OPENCODE_SERVER_USERNAME=opencode
OPENCODE_SERVER_PASSWORD=your_server_password
```

### Codex/OpenAI provider (MANDATORY PATH)

Do not add external OpenAI keys in `.env.local` for Fin-Agent.
Use OpenCode native OAuth integration only.

Run one of:

```bash
opencode auth login openai
```

or in OpenCode TUI:

```bash
/connect
```

then choose:
- `OpenAI`
- `ChatGPT Pro/Plus` OAuth flow

This stores OAuth credentials in OpenCode auth storage and Fin-Agent uses that integration path.

### Kite/Zerodha (for integration phase)

```bash
FIN_AGENT_KITE_API_KEY=your_kite_api_key
FIN_AGENT_KITE_API_SECRET=your_kite_api_secret
FIN_AGENT_KITE_REDIRECT_URI=http://127.0.0.1:8080/v1/auth/kite/callback
FIN_AGENT_KITE_ACCESS_TOKEN=
```

Leave `FIN_AGENT_KITE_ACCESS_TOKEN` blank initially. It is generated after login/authorization and is short-lived.
`FIN_AGENT_KITE_REDIRECT_URI` must exactly match the redirect configured in Zerodha app settings.

## 3) Run services

The run scripts now auto-load `.env.local`.

```bash
./scripts/serve.sh
```

or dev mode:

```bash
./scripts/dev.sh
```

## 3.2) Complete Kite OAuth from local API

After `./scripts/serve.sh` is running:

```bash
curl -sS http://127.0.0.1:8080/v1/auth/kite/status
curl -sS http://127.0.0.1:8080/v1/auth/kite/connect
```

Open the returned `connect_url` in browser and complete login.
Zerodha will redirect to:

```text
http://127.0.0.1:8080/v1/auth/kite/callback?request_token=...&state=...
```

Then verify:

```bash
curl -sS http://127.0.0.1:8080/v1/auth/kite/status
```

## 3.1) OpenCode-native Codex auth + server process

Run OAuth login once:

```bash
./scripts/opencode-auth-openai.sh
```

Start OpenCode server with enforcement:

```bash
./scripts/opencode-serve.sh
```

`scripts/opencode-serve.sh` fails fast if OpenCode OpenAI OAuth is not connected.

## 4) How to give creds to me safely in this chat

- Do not paste raw secrets in chat.
- Tell me: `Creds are in .env.local` and I will continue implementation.
- For Codex/OpenAI, tell me: `OpenCode OpenAI OAuth is connected`.
- When I reach integration steps that truly require login flow, I will stop and ask you before making external auth calls.

## 5) Credential rotation

When rotating keys:

1. Update `.env.local`.
2. Restart services.
3. Revoke old provider/broker tokens from provider dashboards.
