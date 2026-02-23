from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


def _write_fake_opencode(bin_dir: Path) -> Path:
    script = bin_dir / "opencode"
    script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "auth" && "${2:-}" == "list" ]]; then
  echo "OpenAI oauth"
  exit 0
fi
if [[ "${1:-}" == "serve" ]]; then
  echo "fake-opencode-serve args:$*"
  echo "fake-opencode-serve xdg_config_home:${XDG_CONFIG_HOME:-}"
  exit 0
fi
echo "unexpected fake opencode args:$*" >&2
exit 1
""",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


class OpenCodeServeScriptTests(unittest.TestCase):
    def test_opencode_serve_uses_isolated_config_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            fake_bin = tmp_root / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            _write_fake_opencode(fake_bin)
            config_home = tmp_root / "isolated-config-home"

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            env["FIN_AGENT_OPENCODE_CONFIG_HOME"] = str(config_home)
            env.pop("FIN_AGENT_OPENCODE_USE_GLOBAL_CONFIG", None)

            proc = subprocess.run(
                ["bash", "scripts/opencode-serve.sh"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, msg=f"stdout={proc.stdout}\nstderr={proc.stderr}")
            self.assertIn("Using isolated OpenCode config", proc.stdout)
            self.assertIn(f"fake-opencode-serve xdg_config_home:{config_home}", proc.stdout)

            config_path = config_home / "opencode" / "opencode.json"
            self.assertTrue(config_path.exists(), msg=f"missing isolated config: {config_path}")
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(payload.get("model"), "openai/gpt-5.2-codex")
            self.assertIn("oh-my-opencode", payload.get("plugin", []))
            self.assertIn("opencode-beads", payload.get("plugin", []))

    def test_opencode_serve_can_use_global_config_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            fake_bin = tmp_root / "bin"
            fake_bin.mkdir(parents=True, exist_ok=True)
            _write_fake_opencode(fake_bin)
            config_home = tmp_root / "unused-isolated-config-home"

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
            env["FIN_AGENT_OPENCODE_CONFIG_HOME"] = str(config_home)
            env["FIN_AGENT_OPENCODE_USE_GLOBAL_CONFIG"] = "1"

            proc = subprocess.run(
                ["bash", "scripts/opencode-serve.sh"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, msg=f"stdout={proc.stdout}\nstderr={proc.stderr}")
            self.assertIn("Using global OpenCode config", proc.stdout)
            self.assertFalse((config_home / "opencode" / "opencode.json").exists())


if __name__ == "__main__":
    unittest.main()
