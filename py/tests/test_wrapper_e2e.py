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
from typing import Any


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _http_json(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, method=method, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return int(r.getcode()), json.loads(r.read().decode("utf-8"))


class WrapperE2ETests(unittest.TestCase):
    def test_wrapper_proxies_v1_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            api_port = _free_port()
            wrapper_port = _free_port()

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

            wrapper_env = os.environ.copy()
            wrapper_env["FIN_AGENT_API"] = f"http://127.0.0.1:{api_port}"
            wrapper_env["PORT"] = str(wrapper_port)
            wrapper_proc = subprocess.Popen(
                ["node", "apps/fin-agent/src/index.mjs"],
                env=wrapper_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )

            try:
                base = f"http://127.0.0.1:{wrapper_port}"
                for _ in range(100):
                    try:
                        status, _ = _http_json("GET", f"{base}/health")
                        if status == 200:
                            break
                    except Exception:
                        pass
                    time.sleep(0.1)
                else:
                    self.fail("wrapper did not become healthy")

                status, validate = _http_json(
                    "POST",
                    f"{base}/v1/screener/formula/validate",
                    {"formula": "close > open"},
                )
                self.assertEqual(status, 200)
                self.assertTrue(validate["valid"])
            finally:
                wrapper_proc.terminate()
                api_proc.terminate()
                wrapper_proc.wait(timeout=10)
                api_proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
