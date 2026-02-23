from __future__ import annotations

import re
import unittest
from pathlib import Path


class AgenticToolSurfaceTests(unittest.TestCase):
    def test_opencode_tool_surface_is_code_strategy_first(self) -> None:
        root = Path(__file__).resolve().parents[2]
        tool_file = root / ".opencode" / "tools" / "finagent-tools.ts"
        text = tool_file.read_text(encoding="utf-8")

        self.assertIn('"code_strategy_validate"', text)
        self.assertIn('"code_strategy_save"', text)
        self.assertIn('"code_strategy_run_sandbox"', text)
        self.assertIn('"code_strategy_backtest"', text)
        self.assertIn('"code_strategy_analyze"', text)
        self.assertIn('"preflight_custom_code"', text)

        self.assertNotIn('"strategy.from-intent"', text)
        self.assertNotIn('"backtest.run"', text)
        self.assertNotIn('"tuning.search-space.derive"', text)
        self.assertNotIn('"tuning.run"', text)
        self.assertNotIn('"analysis_deep_dive"', text)

    def test_custom_tool_names_follow_openai_name_pattern(self) -> None:
        root = Path(__file__).resolve().parents[2]
        tool_file = root / ".opencode" / "tools" / "finagent-tools.ts"
        text = tool_file.read_text(encoding="utf-8")

        names = re.findall(r'^\s+"([a-zA-Z0-9_.-]+)"\s*:\s*tool\(', text, flags=re.MULTILINE)
        self.assertGreater(len(names), 0)
        for name in names:
            self.assertRegex(name, r"^[a-zA-Z0-9_-]+$")
            self.assertNotIn(".", name)


if __name__ == "__main__":
    unittest.main()
