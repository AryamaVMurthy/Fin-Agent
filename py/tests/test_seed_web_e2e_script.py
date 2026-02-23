from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class SeedWebE2EScriptTests(unittest.TestCase):
    def test_seed_script_dry_run(self) -> None:
        proc = subprocess.run(
            ["bash", "scripts/seed-web-e2e.sh", "--dry-run"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("seed web e2e dry-run", proc.stdout)
        self.assertIn("/v1/code-strategy/backtest", proc.stdout)
        self.assertIn("/v1/live/activate", proc.stdout)

    def test_seed_script_populates_deterministic_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            api_port = _free_port()
            out_path = root / "seed-output.json"
            env = os.environ.copy()
            env["FIN_AGENT_HOME"] = str(root / ".finagent")
            env["PYTHONPATH"] = str(Path.cwd() / "py")
            env.pop("PYTHONHOME", None)

            api_proc = subprocess.Popen(
                [
                    str(Path.cwd() / ".venv312" / "bin" / "python"),
                    "-m",
                    "uvicorn",
                    "fin_agent.api.app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api_port),
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )

            try:
                base = f"http://127.0.0.1:{api_port}"
                for _ in range(80):
                    try:
                        with urllib.request.urlopen(f"{base}/health", timeout=5) as resp:
                            if int(resp.status) == 200:
                                break
                    except Exception:
                        pass
                    time.sleep(0.1)
                else:
                    self.fail("api not healthy in time")

                proc = subprocess.run(
                    [
                        "bash",
                        "scripts/seed-web-e2e.sh",
                        "--api-base",
                        base,
                        "--output-json",
                        str(out_path),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(proc.returncode, 0, msg=f"stdout={proc.stdout}\nstderr={proc.stderr}")
                self.assertTrue(out_path.exists())
                payload = json.loads(out_path.read_text(encoding="utf-8"))
                self.assertGreaterEqual(len(payload.get("backtest_run_ids", [])), 2)
                self.assertTrue(str(payload.get("live_strategy_version_id", "")).strip())
            finally:
                api_proc.terminate()
                api_proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
