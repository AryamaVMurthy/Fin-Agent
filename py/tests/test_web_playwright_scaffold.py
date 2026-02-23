from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class WebPlaywrightScaffoldTests(unittest.TestCase):
    def test_playwright_runner_script_dry_run(self) -> None:
        proc = subprocess.run(
            ["bash", "scripts/e2e-web-playwright.sh", "--dry-run"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("web playwright e2e dry-run", proc.stdout)
        self.assertIn("chat journey specs", proc.stdout)
        self.assertIn("workspace journey specs", proc.stdout)
        self.assertIn("robustness specs", proc.stdout)
        self.assertIn("chat_warmup=1", proc.stdout)
        self.assertIn("optional real chat warmup request", proc.stdout)

    def test_playwright_config_and_spec_files_exist(self) -> None:
        root = Path(__file__).resolve().parents[2]
        config_path = root / "apps" / "fin-agent-web" / "e2e" / "playwright.config.mjs"
        chat_spec = root / "apps" / "fin-agent-web" / "e2e" / "tests" / "chat.spec.mjs"
        workspaces_spec = root / "apps" / "fin-agent-web" / "e2e" / "tests" / "workspaces.spec.mjs"
        robustness_spec = root / "apps" / "fin-agent-web" / "e2e" / "tests" / "robustness.spec.mjs"

        self.assertTrue(config_path.exists(), msg=f"missing {config_path}")
        self.assertTrue(chat_spec.exists(), msg=f"missing {chat_spec}")
        self.assertTrue(workspaces_spec.exists(), msg=f"missing {workspaces_spec}")
        self.assertTrue(robustness_spec.exists(), msg=f"missing {robustness_spec}")

        config_text = config_path.read_text(encoding="utf-8")
        self.assertIn("chromium", config_text)
        self.assertIn("trace", config_text)
        self.assertIn("baseURL", config_text)


if __name__ == "__main__":
    unittest.main()
