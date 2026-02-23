from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


def _http_text(method: str, url: str) -> tuple[int, str, str]:
    req = urllib.request.Request(url=url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            content_type = str(r.headers.get("content-type", ""))
            return int(r.getcode()), content_type, r.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        content_type = str(exc.headers.get("content-type", ""))
        return int(exc.code), content_type, exc.read().decode("utf-8", errors="replace")


class _OpencodeStubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, code: int, payload: dict[str, Any] | list[Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/global/health":
            self._send_json(200, {"healthy": True, "version": "stub-1"})
            return
        if self.path == "/session":
            self._send_json(200, [{"id": "sess-1", "title": "stub"}])
            return
        if self.path.startswith("/session/sess-1/message"):
            self._send_json(
                200,
                [
                    {
                        "info": {"id": "msg-1"},
                        "parts": [{"type": "text", "text": "hello from opencode stub"}],
                    }
                ],
            )
            return
        self._send_json(404, {"detail": f"unsupported path: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            self._send_json(400, {"detail": "invalid json"})
            return

        if self.path == "/session":
            self._send_json(200, {"id": "sess-1", "title": payload.get("title", "stub")})
            return
        if self.path == "/session/sess-1/message":
            self._send_json(
                200,
                {
                    "info": {"id": "msg-2"},
                    "parts": [{"type": "text", "text": "hello from opencode stub"}],
                    "echo": payload,
                },
            )
            return
        self._send_json(404, {"detail": f"unsupported path: {self.path}"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


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

    def test_wrapper_serves_web_app_static_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            api_port = _free_port()
            wrapper_port = _free_port()

            web_dist = root / "web-dist"
            assets_dir = web_dist / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            (web_dist / "index.html").write_text(
                "<!doctype html><html><body><div id='root'>fin-agent-web</div></body></html>",
                encoding="utf-8",
            )
            (assets_dir / "app.js").write_text("console.log('fin-agent-web');", encoding="utf-8")

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
            wrapper_env["FIN_AGENT_WEB_DIST"] = str(web_dist)
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

                status, ctype, html = _http_text("GET", f"{base}/app")
                self.assertEqual(status, 200)
                self.assertIn("text/html", ctype)
                self.assertIn("fin-agent-web", html)

                status, ctype, js = _http_text("GET", f"{base}/app/assets/app.js")
                self.assertEqual(status, 200)
                self.assertIn("javascript", ctype)
                self.assertIn("fin-agent-web", js)
            finally:
                wrapper_proc.terminate()
                api_proc.terminate()
                wrapper_proc.wait(timeout=10)
                api_proc.wait(timeout=10)

    def test_wrapper_chat_bridge_endpoints_use_opencode_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            api_port = _free_port()
            wrapper_port = _free_port()
            opencode_port = _free_port()

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

            opencode_server = ThreadingHTTPServer(("127.0.0.1", opencode_port), _OpencodeStubHandler)
            opencode_thread = threading.Thread(target=opencode_server.serve_forever, daemon=True)
            opencode_thread.start()

            wrapper_env = os.environ.copy()
            wrapper_env["FIN_AGENT_API"] = f"http://127.0.0.1:{api_port}"
            wrapper_env["OPENCODE_API"] = f"http://127.0.0.1:{opencode_port}"
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
                        status, payload = _http_json("GET", f"{base}/v1/chat/health")
                        if status == 200 and payload.get("healthy") is True:
                            break
                    except Exception:
                        pass
                    time.sleep(0.1)
                else:
                    self.fail("wrapper chat bridge did not become ready")

                status, sessions = _http_json("GET", f"{base}/v1/chat/sessions")
                self.assertEqual(status, 200)
                self.assertGreaterEqual(len(sessions["sessions"]), 1)
                self.assertEqual(sessions["sessions"][0]["id"], "sess-1")

                status, response = _http_json(
                    "POST",
                    f"{base}/v1/chat/respond",
                    {"message": "hello", "title": "New Session"},
                )
                self.assertEqual(status, 200)
                self.assertEqual(response["session_id"], "sess-1")
                self.assertTrue(response["created_session"])
                self.assertIn("hello from opencode stub", response["assistant_text"])

                status, messages = _http_json("GET", f"{base}/v1/chat/sessions/sess-1/messages?limit=5")
                self.assertEqual(status, 200)
                self.assertGreaterEqual(messages["count"], 1)
            finally:
                wrapper_proc.terminate()
                api_proc.terminate()
                opencode_server.shutdown()
                opencode_server.server_close()
                wrapper_proc.wait(timeout=10)
                api_proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
