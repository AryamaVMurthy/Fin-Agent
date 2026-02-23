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
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = int(r.getcode())
            data = json.loads(r.read().decode("utf-8"))
            return status, data
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            parsed = {"detail": detail}
        return int(exc.code), parsed
    except urllib.error.URLError as exc:
        return 0, {"detail": str(exc.reason)}


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        body_length = int(self.headers.get("content-length", "0"))
        if body_length > 0:
            _ = self.rfile.read(body_length)

        if self.path == "/session":
            self._write_json(200, {"id": "sess_fake_analysis"})
            return
        if self.path.startswith("/session/") and self.path.endswith("/message"):
            self._write_json(
                200,
                {
                    "id": "msg_fake_analysis",
                    "parts": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "summary": "Fake OpenCode analysis",
                                    "suggestions": [
                                        {
                                            "title": "Improve signal threshold",
                                            "evidence": "sharpe is below desired threshold",
                                            "expected_impact": "Increase risk-adjusted return.",
                                            "confidence": 0.77,
                                            "patch": "if momentum > 0.6: signals.append({...})",
                                        }
                                    ],
                                }
                            ),
                        }
                    ],
                },
            )
            return
        self._write_json(404, {"detail": f"unsupported path: {self.path}"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


class _FakeOpenCodeServer:
    def __init__(self, host: str, port: int) -> None:
        self._server = ThreadingHTTPServer((host, port), _FakeOpenCodeHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_FakeOpenCodeServer":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5.0)


CODE_A = """
def prepare(data_bundle, context):
    return {"variant": "a"}

def generate_signals(frame, state, context):
    return [{"symbol": "ABC", "signal": "buy", "strength": 0.65, "reason_code": "signal_buy_a"}]

def risk_rules(positions, context):
    return {"max_positions": 1}
"""


CODE_B = """
def prepare(data_bundle, context):
    return {"variant": "b"}

def generate_signals(frame, state, context):
    return [{"symbol": "ABC", "signal": "buy", "strength": 0.55, "reason_code": "signal_buy_b"}]

def risk_rules(positions, context):
    return {"max_positions": 1}
"""


class ApiE2ETests(unittest.TestCase):
    def test_stage1_e2e_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            csv_path = root / "prices.csv"
            fundamentals_path = root / "fundamentals.csv"
            actions_path = root / "actions.csv"
            ratings_path = root / "ratings.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "timestamp,symbol,open,high,low,close,volume",
                        "2025-01-01T00:00:00Z,ABC,100,101,99,100,1000",
                        "2025-01-02T00:00:00Z,ABC,100,102,99,101,1100",
                        "2025-01-03T00:00:00Z,ABC,101,104,100,103,1200",
                        "2025-01-04T00:00:00Z,ABC,103,105,102,104,1200",
                        "2025-01-05T00:00:00Z,ABC,104,106,103,105,1300",
                        "2025-01-06T00:00:00Z,ABC,105,107,104,106,1300",
                        "2025-01-07T00:00:00Z,ABC,106,106,100,101,1400",
                        "2025-01-08T00:00:00Z,ABC,101,103,99,100,1400",
                        "2025-01-09T00:00:00Z,ABC,100,102,98,99,1500",
                        "2025-01-10T00:00:00Z,ABC,99,101,97,98,1500",
                    ]
                ),
                encoding="utf-8",
            )
            fundamentals_path.write_text(
                "\n".join(
                    [
                        "symbol,published_at,pe_ratio,eps",
                        "ABC,2024-12-31T00:00:00Z,18.5,5.2",
                        "ABC,2025-01-08T00:00:00Z,19.1,5.3",
                    ]
                ),
                encoding="utf-8",
            )
            actions_path.write_text(
                "\n".join(
                    [
                        "symbol,effective_at,action_type,action_value",
                        "ABC,2025-01-05T00:00:00Z,dividend,2.0",
                    ]
                ),
                encoding="utf-8",
            )
            ratings_path.write_text(
                "\n".join(
                    [
                        "symbol,revised_at,agency,rating",
                        "ABC,2025-01-06T00:00:00Z,BankX,buy",
                    ]
                ),
                encoding="utf-8",
            )

            port = _free_port()
            opencode_port = _free_port()
            env = os.environ.copy()
            env["FIN_AGENT_HOME"] = str(root / ".finagent")
            env["OPENCODE_API"] = f"http://127.0.0.1:{opencode_port}"
            env.pop("PYTHONHOME", None)
            env.pop("PYTHONPATH", None)
            env["PYTHONPATH"] = str(Path.cwd() / "py")

            with _FakeOpenCodeServer("127.0.0.1", opencode_port):
                proc = subprocess.Popen(
                    [
                        str(Path.cwd() / ".venv312" / "bin" / "python"),
                        "-m",
                        "uvicorn",
                        "fin_agent.api.app:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    cwd=str(Path.cwd()),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                try:
                    base = f"http://127.0.0.1:{port}"
                    for _ in range(80):
                        status, _payload = _http_json("GET", f"{base}/health")
                        if status == 200:
                            break
                        time.sleep(0.1)
                    else:
                        raise AssertionError("API did not become healthy in time")

                    status, import_payload = _http_json("POST", f"{base}/v1/data/import", {"path": str(csv_path)})
                    self.assertEqual(status, 200)
                    self.assertGreater(import_payload["rows_inserted"], 0)
    
                    status, fundamentals_import = _http_json(
                        "POST",
                        f"{base}/v1/data/import/fundamentals",
                        {"path": str(fundamentals_path)},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(fundamentals_import["rows_inserted"], 2)
    
                    status, actions_import = _http_json(
                        "POST",
                        f"{base}/v1/data/import/corporate-actions",
                        {"path": str(actions_path)},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(actions_import["rows_inserted"], 1)
    
                    status, ratings_import = _http_json(
                        "POST",
                        f"{base}/v1/data/import/ratings",
                        {"path": str(ratings_path)},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(ratings_import["rows_inserted"], 1)
    
                    status, legacy = _http_json(
                        "POST",
                        f"{base}/v1/brainstorm/agent-decides/propose",
                        {"universe": ["ABC"], "start_date": "2025-01-01", "end_date": "2025-01-10"},
                    )
                    self.assertEqual(status, 410)
                    self.assertEqual(legacy["detail"]["error"], "legacy_endpoint_disabled")
    
                    status, world_preflight = _http_json(
                        "POST",
                        f"{base}/v1/preflight/custom-code",
                        {
                            "universe": ["ABC"],
                            "start_date": "2025-01-01",
                            "end_date": "2025-01-10",
                            "complexity_multiplier": 1.0,
                            "max_allowed_seconds": 120.0,
                        },
                    )
                    self.assertEqual(status, 200)
                    self.assertGreater(float(world_preflight["estimated_seconds"]), 0.0)
    
                    status, completeness = _http_json(
                        "POST",
                        f"{base}/v1/world-state/completeness",
                        {
                            "universe": ["ABC"],
                            "start_date": "2025-01-01",
                            "end_date": "2025-01-10",
                            "strict_mode": False,
                        },
                    )
                    self.assertEqual(status, 200)
                    self.assertIn("skipped_features", completeness)
    
                    status, pit = _http_json(
                        "POST",
                        f"{base}/v1/world-state/validate-pit",
                        {
                            "universe": ["ABC"],
                            "start_date": "2025-01-01",
                            "end_date": "2025-01-10",
                            "strict_mode": True,
                        },
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(pit["valid"])
    
                    status, validation = _http_json(
                        "POST",
                        f"{base}/v1/code-strategy/validate",
                        {"strategy_name": "Code E2E A", "source_code": CODE_A},
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(validation["validation"]["valid"])
    
                    status, sandbox = _http_json(
                        "POST",
                        f"{base}/v1/code-strategy/run-sandbox",
                        {"source_code": CODE_A, "timeout_seconds": 3, "memory_mb": 128, "cpu_seconds": 1},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(sandbox["status"], "completed")
    
                    status, run_one = _http_json(
                        "POST",
                        f"{base}/v1/code-strategy/backtest",
                        {
                            "strategy_name": "Code E2E A",
                            "source_code": CODE_A,
                            "universe": ["ABC"],
                            "start_date": "2025-01-01",
                            "end_date": "2025-01-10",
                            "initial_capital": 100000.0,
                        },
                    )
                    self.assertEqual(status, 200)
    
                    status, run_two = _http_json(
                        "POST",
                        f"{base}/v1/code-strategy/backtest",
                        {
                            "strategy_name": "Code E2E B",
                            "source_code": CODE_B,
                            "universe": ["ABC"],
                            "start_date": "2025-01-01",
                            "end_date": "2025-01-10",
                            "initial_capital": 100000.0,
                        },
                    )
                    self.assertEqual(status, 200)
                    run_one_id = run_one["run_id"]
                    run_two_id = run_two["run_id"]
                    strategy_version_id = run_two["strategy_version_id"]
    
                    status, compare = _http_json(
                        "POST",
                        f"{base}/v1/backtests/compare",
                        {"baseline_run_id": run_one_id, "candidate_run_id": run_two_id},
                    )
                    self.assertEqual(status, 200)
                    self.assertIn("metrics_delta", compare)
    
                    status, code_analysis = _http_json(
                        "POST",
                        f"{base}/v1/code-strategy/analyze",
                        {
                            "run_id": run_two_id,
                            "source_code": CODE_B,
                        },
                    )
                    self.assertEqual(status, 200)
                    self.assertIn("suggestions", code_analysis)
                    self.assertGreaterEqual(code_analysis["suggestion_count"], 1)
    
                    status, blotter = _http_json(
                        "POST",
                        f"{base}/v1/visualize/trade-blotter",
                        {"run_id": run_two_id},
                    )
                    self.assertEqual(status, 200)
                    self.assertIn("trade_blotter_path", blotter["artifacts"])
    
                    status, activate = _http_json(
                        "POST",
                        f"{base}/v1/live/activate",
                        {"strategy_version_id": strategy_version_id},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(activate["status"], "active")
    
                    status, live_feed = _http_json(
                        "GET",
                        f"{base}/v1/live/feed?strategy_version_id={strategy_version_id}&limit=10",
                    )
                    self.assertEqual(status, 200)
                    self.assertGreaterEqual(live_feed["count"], 1)
    
                    status, boundary = _http_json(
                        "GET",
                        f"{base}/v1/live/boundary-candidates?strategy_version_id={strategy_version_id}&top_k=5",
                    )
                    self.assertEqual(status, 200)
                    self.assertLessEqual(boundary["count"], 5)
    
                    status, boundary_viz = _http_json(
                        "POST",
                        f"{base}/v1/visualize/boundary",
                        {"strategy_version_id": strategy_version_id, "top_k": 5},
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(boundary_viz["boundary_chart_path"].endswith(".svg"))
    
                    status, report = _http_json(
                        "POST",
                        f"{base}/v1/backtests/tax/report",
                        {"run_id": run_two_id, "enabled": True},
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(report["enabled"])
    
                    status, paused = _http_json(
                        "POST",
                        f"{base}/v1/live/pause",
                        {"strategy_version_id": strategy_version_id},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(paused["status"], "paused")
    
                    status, stopped = _http_json(
                        "POST",
                        f"{base}/v1/live/stop",
                        {"strategy_version_id": strategy_version_id},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(stopped["status"], "stopped")
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)
                    if proc.stdout is not None:
                        proc.stdout.close()
                    if proc.stderr is not None:
                        proc.stderr.close()


if __name__ == "__main__":
    unittest.main()
