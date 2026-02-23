from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.storage.paths import RuntimePaths


class DiagnosticsReadinessTests(unittest.TestCase):
    def test_readiness_returns_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir) / ".finagent")
            paths.ensure()
            with patch.object(app_module, "_runtime_paths", return_value=paths):
                with patch.dict(
                    "os.environ",
                    {
                        "FIN_AGENT_KITE_API_KEY": "kite_key",
                        "FIN_AGENT_KITE_API_SECRET": "kite_secret",
                        "FIN_AGENT_KITE_REDIRECT_URI": "http://127.0.0.1:8080/v1/auth/kite/callback",
                        "FIN_AGENT_ENCRYPTION_KEY": "testkey",
                    },
                    clear=False,
                ):
                    with patch(
                        "fin_agent.api.app.opencode_auth_integration.get_openai_oauth_status",
                        return_value={"opencode_installed": True, "connected": True, "error": None},
                    ):
                        out = app_module.diagnostics_readiness()
        self.assertIn("checks", out)
        self.assertIn("ready", out)

    def test_readiness_accepts_opencode_api_credential_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir) / ".finagent")
            paths.ensure()
            with patch.object(app_module, "_runtime_paths", return_value=paths):
                with patch.dict(
                    "os.environ",
                    {
                        "FIN_AGENT_KITE_API_KEY": "kite_key",
                        "FIN_AGENT_KITE_API_SECRET": "kite_secret",
                        "FIN_AGENT_KITE_REDIRECT_URI": "http://127.0.0.1:8080/v1/auth/kite/callback",
                        "FIN_AGENT_ENCRYPTION_KEY": "testkey",
                        "OPENAI_API_KEY": "sk-test-value",
                    },
                    clear=False,
                ):
                    with patch(
                        "fin_agent.api.app.opencode_auth_integration.get_openai_oauth_status",
                        return_value={
                            "opencode_installed": True,
                            "connected": True,
                            "provider": "OpenAI",
                            "method": "api",
                            "connected_methods": ["api_env"],
                            "oauth_connected": False,
                            "api_connected": True,
                        },
                    ):
                        out = app_module.diagnostics_readiness()
        self.assertTrue(out["ready"])


if __name__ == "__main__":
    unittest.main()
