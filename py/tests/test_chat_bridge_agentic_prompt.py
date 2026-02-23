from __future__ import annotations

import unittest
from pathlib import Path


class ChatBridgeAgenticPromptTests(unittest.TestCase):
    def test_default_system_prompt_enforces_code_strategy_path(self) -> None:
        root = Path(__file__).resolve().parents[2]
        bridge_file = root / "apps" / "fin-agent" / "src" / "index.mjs"
        text = bridge_file.read_text(encoding="utf-8")

        self.assertIn("natural-language strategy conversion must be fully agentic", text)
        self.assertIn("do NOT use hardcoded/manual NL-to-intent mapping endpoints", text)
        self.assertIn("code_strategy_validate", text)
        self.assertIn("preflight_custom_code", text)
        self.assertIn("code_strategy_run_sandbox", text)
        self.assertIn("code_strategy_backtest", text)


if __name__ == "__main__":
    unittest.main()
