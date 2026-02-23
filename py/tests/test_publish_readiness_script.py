from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class PublishReadinessScriptTests(unittest.TestCase):
    def test_publish_readiness_dry_run(self) -> None:
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            ["bash", "scripts/publish-readiness.sh", "--dry-run"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("publish readiness dry-run", proc.stdout)
        self.assertIn("npm pack --dry-run", proc.stdout)
        self.assertIn("smoke e2e run", proc.stdout)

    def test_publish_readiness_can_skip_heavy_or_external_checks(self) -> None:
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            [
                "bash",
                "scripts/publish-readiness.sh",
                "--allow-dirty",
                "--skip-tests",
                "--skip-smoke",
                "--skip-auth",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("publish-readiness: READY", proc.stdout)


if __name__ == "__main__":
    unittest.main()
