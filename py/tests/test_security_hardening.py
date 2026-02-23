from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.security.redaction import redact_payload
from fin_agent.storage.paths import RuntimePaths


class SecurityHardeningTests(unittest.TestCase):
    def test_redaction_masks_sensitive_keys(self) -> None:
        payload = {
            "access_token": "abcdefghijklmnop",
            "nested": {"api_secret": "secret-value"},
            "normal": "value",
        }
        redacted = redact_payload(payload)
        self.assertEqual(redacted["normal"], "value")
        self.assertNotEqual(redacted["access_token"], "abcdefghijklmnop")
        self.assertIn("...", redacted["access_token"])
        self.assertNotEqual(redacted["nested"]["api_secret"], "secret-value")

    def test_observability_and_provider_health_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir) / ".finagent")
            with patch.object(app_module, "_runtime_paths", return_value=paths):
                with patch.dict(
                    "os.environ",
                    {
                        "FIN_AGENT_KITE_API_KEY": "kite_key",
                        "FIN_AGENT_KITE_API_SECRET": "kite_secret",
                        "FIN_AGENT_KITE_REDIRECT_URI": "http://127.0.0.1:8080/v1/auth/kite/callback",
                    },
                    clear=False,
                ):
                    metrics = app_module.observability_metrics()
                    health = app_module.providers_health()

        self.assertIn("metrics", metrics)
        self.assertIn("providers", health)
        self.assertIn("kite", health["providers"])


if __name__ == "__main__":
    unittest.main()
