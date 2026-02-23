from __future__ import annotations

import json
import os
import socket
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator
from unittest.mock import patch

from fin_agent.integrations.opencode_agent import run_agent_json_task


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def fake_opencode_server(
    *,
    message_text: str,
    create_status: int = 200,
    message_status: int = 200,
) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("content-length", "0"))
            if length > 0:
                _ = self.rfile.read(length)

            if self.path == "/session":
                if create_status >= 400:
                    self._write_json(create_status, {"detail": "create failed"})
                else:
                    self._write_json(200, {"id": "sess_test"})
                return

            if self.path.startswith("/session/") and self.path.endswith("/message"):
                if message_status >= 400:
                    self._write_json(message_status, {"detail": "message failed"})
                else:
                    self._write_json(
                        200,
                        {
                            "id": "msg_test",
                            "parts": [{"type": "text", "text": message_text}],
                        },
                    )
                return

            self._write_json(404, {"detail": "not found"})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3.0)


class OpenCodeAgentIntegrationTests(unittest.TestCase):
    def test_run_agent_json_task_returns_object(self) -> None:
        with fake_opencode_server(message_text='{"summary":"ok","suggestions":[]}') as base:
            with patch.dict(os.environ, {"OPENCODE_API": base}, clear=False):
                payload = run_agent_json_task(
                    user_prompt="ping",
                    system_prompt="return json",
                    timeout_seconds=3.0,
                )
        self.assertEqual(payload["summary"], "ok")

    def test_run_agent_json_task_accepts_fenced_json(self) -> None:
        with fake_opencode_server(message_text='```json\n{"summary":"ok2","suggestions":[]}\n```') as base:
            with patch.dict(os.environ, {"OPENCODE_API": base}, clear=False):
                payload = run_agent_json_task(
                    user_prompt="ping",
                    system_prompt="return json",
                    timeout_seconds=3.0,
                )
        self.assertEqual(payload["summary"], "ok2")

    def test_run_agent_json_task_fails_for_non_json_output(self) -> None:
        with fake_opencode_server(message_text="plain text output") as base:
            with patch.dict(os.environ, {"OPENCODE_API": base}, clear=False):
                with self.assertRaises(ValueError) as ctx:
                    run_agent_json_task(
                        user_prompt="ping",
                        system_prompt="return json",
                        timeout_seconds=3.0,
                    )
        self.assertIn("missing JSON object", str(ctx.exception))

    def test_run_agent_json_task_fails_fast_when_session_create_fails(self) -> None:
        with fake_opencode_server(message_text='{"summary":"x"}', create_status=500) as base:
            with patch.dict(os.environ, {"OPENCODE_API": base}, clear=False):
                with self.assertRaises(ValueError) as ctx:
                    run_agent_json_task(
                        user_prompt="ping",
                        system_prompt="return json",
                        timeout_seconds=3.0,
                    )
        self.assertIn("session create failed", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
