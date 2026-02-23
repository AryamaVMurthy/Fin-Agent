from __future__ import annotations

import subprocess
import unittest


class RigorousE2EScriptTests(unittest.TestCase):
    def test_e2e_full_script_dry_run(self) -> None:
        proc = subprocess.run(
            ["bash", "scripts/e2e-full.sh", "--dry-run"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=f"stderr={proc.stderr}")
        self.assertIn("rigorous e2e dry-run", proc.stdout)
        self.assertIn("deterministic data imports", proc.stdout)
        self.assertIn("optional strict providers gate", proc.stdout)
        self.assertIn("optional playwright web visual gate", proc.stdout)


if __name__ == "__main__":
    unittest.main()
