from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from fin_agent.api import app as app_module


class OpenCodeAuthTests(unittest.TestCase):
    def test_auth_opencode_status_connected(self) -> None:
        with patch(
            "fin_agent.api.app.opencode_auth_integration.get_openai_oauth_status",
            return_value={
                "opencode_installed": True,
                "connected": True,
                "provider": "OpenAI",
                "method": "oauth",
            },
        ):
            response = app_module.auth_opencode_openai_oauth_status()
        self.assertTrue(response["connected"])
        self.assertTrue(response["opencode_installed"])

    def test_auth_opencode_connect_when_not_connected(self) -> None:
        with patch(
            "fin_agent.api.app.opencode_auth_integration.get_openai_oauth_status",
            return_value={
                "opencode_installed": True,
                "connected": False,
                "provider": "OpenAI",
                "method": "oauth_or_api",
            },
        ):
            response = app_module.auth_opencode_openai_oauth_connect()
        self.assertEqual(response["action"], "run_connect_command")
        self.assertIn("opencode auth login openai", response["connect_command"])

    def test_auth_opencode_connect_when_connected_with_api_credential(self) -> None:
        with patch(
            "fin_agent.api.app.opencode_auth_integration.get_openai_oauth_status",
            return_value={
                "opencode_installed": True,
                "connected": True,
                "provider": "OpenAI",
                "method": "api",
                "connected_methods": ["api"],
                "oauth_connected": False,
                "api_connected": True,
            },
        ):
            response = app_module.auth_opencode_openai_oauth_connect()
        self.assertEqual(response["action"], "already_connected")
        self.assertEqual(response["method"], "api")

    def test_auth_opencode_connect_when_already_connected(self) -> None:
        with patch(
            "fin_agent.api.app.opencode_auth_integration.get_openai_oauth_status",
            return_value={
                "opencode_installed": True,
                "connected": True,
                "provider": "OpenAI",
                "method": "oauth",
            },
        ):
            response = app_module.auth_opencode_openai_oauth_connect()
        self.assertEqual(response["action"], "already_connected")

    def test_auth_opencode_status_raises_when_opencode_missing(self) -> None:
        with patch(
            "fin_agent.api.app.opencode_auth_integration.get_openai_oauth_status",
            return_value={
                "opencode_installed": False,
                "connected": False,
                "provider": "OpenAI",
                "method": "oauth",
                "error": "opencode not found",
            },
        ):
            with self.assertRaises(HTTPException) as exc:
                app_module.auth_opencode_openai_oauth_status()
        self.assertEqual(exc.exception.status_code, 500)
        self.assertIn("opencode not available", str(exc.exception.detail))


if __name__ == "__main__":
    unittest.main()
