from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def get_openai_oauth_status(timeout_seconds: float = 8.0) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if shutil.which("opencode") is None:
        return {
            "opencode_installed": False,
            "connected": False,
            "provider": "OpenAI",
            "method": "oauth",
            "error": "opencode not found in PATH",
        }

    try:
        proc = subprocess.run(
            ["opencode", "auth", "list"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {
            "opencode_installed": True,
            "connected": False,
            "provider": "OpenAI",
            "method": "oauth",
            "error": "opencode auth list timed out",
        }
    output = _strip_ansi((proc.stdout or "") + "\n" + (proc.stderr or ""))
    if proc.returncode != 0:
        return {
            "opencode_installed": True,
            "connected": False,
            "provider": "OpenAI",
            "method": "oauth",
            "error": f"opencode auth list failed with exit_code={proc.returncode}",
        }

    oauth_connected = bool(re.search(r"\bOpenAI\b\s+oauth\b", output, flags=re.IGNORECASE))
    api_connected_cli = bool(re.search(r"\bOpenAI\b\s+api\b", output, flags=re.IGNORECASE))
    api_connected_env = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    api_connected = api_connected_cli or api_connected_env
    connected_methods: list[str] = []
    if oauth_connected:
        connected_methods.append("oauth")
    if api_connected_cli:
        connected_methods.append("api")
    if api_connected_env:
        connected_methods.append("api_env")
    connected = oauth_connected or api_connected
    method = "oauth_or_api"
    if oauth_connected:
        method = "oauth"
    elif api_connected:
        method = "api"
    return {
        "opencode_installed": True,
        "connected": connected,
        "provider": "OpenAI",
        "method": method,
        "oauth_connected": oauth_connected,
        "api_connected": api_connected,
        "connected_methods": connected_methods,
    }
