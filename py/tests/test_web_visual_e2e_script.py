from __future__ import annotations

import subprocess
import unittest


class WebVisualE2EScriptTests(unittest.TestCase):
    def test_web_visual_script_dry_run(self) -> None:
        proc = subprocess.run(
            ["bash", "scripts/e2e-web-visual.sh", "--dry-run"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("web visual e2e dry-run", proc.stdout)
        self.assertIn("playwright-driven browser rendering gate", proc.stdout)
        self.assertIn("desktop screenshot", proc.stdout)
        self.assertIn("mobile screenshot", proc.stdout)


if __name__ == "__main__":
    unittest.main()
