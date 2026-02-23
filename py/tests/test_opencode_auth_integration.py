from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from fin_agent.integrations import opencode_auth


class OpenCodeAuthIntegrationTests(unittest.TestCase):
    def test_detects_openai_api_auth_method(self) -> None:
        proc = subprocess.CompletedProcess(
            args=["opencode", "auth", "list"],
            returncode=0,
            stdout="OpenAI api\n",
            stderr="",
        )
        with patch("fin_agent.integrations.opencode_auth.shutil.which", return_value="/usr/bin/opencode"):
            with patch("fin_agent.integrations.opencode_auth.subprocess.run", return_value=proc):
                status = opencode_auth.get_openai_oauth_status()
        self.assertTrue(status["connected"])
        self.assertTrue(status["api_connected"])
        self.assertEqual(status["method"], "api")

    def test_detects_env_api_key_when_opencode_not_connected(self) -> None:
        proc = subprocess.CompletedProcess(
            args=["opencode", "auth", "list"],
            returncode=0,
            stdout="GitHub Copilot oauth\n",
            stderr="",
        )
        with patch("fin_agent.integrations.opencode_auth.shutil.which", return_value="/usr/bin/opencode"):
            with patch("fin_agent.integrations.opencode_auth.subprocess.run", return_value=proc):
                with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-value"}, clear=False):
                    status = opencode_auth.get_openai_oauth_status()
        self.assertTrue(status["connected"])
        self.assertTrue(status["api_connected"])
        self.assertIn("api_env", status["connected_methods"])


if __name__ == "__main__":
    unittest.main()
