from __future__ import annotations

import base64
import subprocess
import unittest
from pathlib import Path


class OperatorScriptsTests(unittest.TestCase):
    def test_gen_encryption_key_prints_valid_fernet_key(self) -> None:
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            ["bash", "scripts/gen-encryption-key.sh", "--print"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        key = proc.stdout.strip()
        decoded = base64.urlsafe_b64decode(key.encode("utf-8"))
        self.assertEqual(len(decoded), 32)

    def test_e2e_smoke_script_dry_run(self) -> None:
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.run(
            ["bash", "scripts/e2e-smoke.sh", "--dry-run"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("smoke dry-run", proc.stdout)
        self.assertIn("/v1/screener/run", proc.stdout)


if __name__ == "__main__":
    unittest.main()
