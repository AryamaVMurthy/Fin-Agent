from __future__ import annotations

import subprocess
import tarfile
import unittest
from pathlib import Path


class ReleasePackagingTests(unittest.TestCase):
    def test_release_script_dry_run(self) -> None:
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            ["bash", "scripts/release-tui.sh", "--dry-run", "--version", "test-v1"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("release dry-run", proc.stdout)
        self.assertIn("fin-agent-tui-test-v1", proc.stdout)

    def test_release_archive_contains_license_cli_and_publish_runbook(self) -> None:
        root = Path(__file__).resolve().parents[2]
        version = "test-v2"
        proc = subprocess.run(
            ["bash", "scripts/release-tui.sh", "--version", version],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        archive = root / "dist" / f"fin-agent-tui-{version}.tar.gz"
        self.assertTrue(archive.exists(), msg=f"missing archive {archive}")
        with tarfile.open(archive, "r:gz") as tf:
            names = set(tf.getnames())
        self.assertIn(f"fin-agent-tui-{version}/LICENSE", names)
        self.assertIn(f"fin-agent-tui-{version}/apps/fin-agent/src/cli.mjs", names)
        self.assertIn(f"fin-agent-tui-{version}/apps/fin-agent-web/dist/index.html", names)
        self.assertIn(f"fin-agent-tui-{version}/apps/fin-agent-web/dist/assets/app.js", names)
        self.assertIn(f"fin-agent-tui-{version}/docs/runbooks/publish-stage1.md", names)


if __name__ == "__main__":
    unittest.main()
