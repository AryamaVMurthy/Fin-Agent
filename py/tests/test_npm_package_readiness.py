from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


class NpmPackageReadinessTests(unittest.TestCase):
    def test_wrapper_package_has_publish_metadata(self) -> None:
        root = Path(__file__).resolve().parents[2]
        payload = json.loads((root / "apps" / "fin-agent" / "package.json").read_text(encoding="utf-8"))
        self.assertFalse(payload.get("private", True))
        self.assertEqual(payload.get("type"), "module")
        self.assertIn("bin", payload)
        self.assertIn("fin-agent", payload["bin"])
        self.assertEqual(payload["bin"]["fin-agent"], "src/cli.mjs")
        self.assertIn("files", payload)
        self.assertIn("src", payload["files"])
        self.assertEqual(payload.get("license"), "MIT")

    def test_cli_help_lists_supported_commands(self) -> None:
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            ["node", "apps/fin-agent/src/cli.mjs", "--help"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("fin-agent", proc.stdout)
        self.assertIn("wrapper", proc.stdout)
        self.assertIn("doctor", proc.stdout)
        self.assertIn("rigorous", proc.stdout)

    def test_npm_pack_dry_run_contains_cli_and_wrapper_entry(self) -> None:
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            ["npm", "pack", "--dry-run", "--json"],
            cwd=root / "apps" / "fin-agent",
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        parsed = json.loads(proc.stdout)
        self.assertIsInstance(parsed, list)
        self.assertGreaterEqual(len(parsed), 1)
        files = {entry["path"] for entry in parsed[0]["files"]}
        self.assertIn("src/cli.mjs", files)
        self.assertIn("src/index.mjs", files)


if __name__ == "__main__":
    unittest.main()
