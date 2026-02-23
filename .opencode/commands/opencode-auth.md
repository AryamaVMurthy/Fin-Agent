# /opencode-auth

Use this command for OpenCode native OpenAI OAuth checks.

## 1) Check OAuth status

```bash
curl -sS http://127.0.0.1:8080/v1/auth/opencode/openai/oauth/status
```

## 2) Get connect action

```bash
curl -sS http://127.0.0.1:8080/v1/auth/opencode/openai/oauth/connect
```

If not connected, run:

```bash
opencode auth login openai
```

or OpenCode TUI:

```text
/connect
```
