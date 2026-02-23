from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.observability.context import reset_trace_id, set_trace_id
from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


class ObservabilityTests(unittest.TestCase):
    def test_append_audit_event_injects_trace_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir))
            sqlite_store.init_db(paths)
            token = set_trace_id("trace-test-123")
            try:
                sqlite_store.append_audit_event(paths, "test.event", {"value": 1})
            finally:
                reset_trace_id(token)
            events = sqlite_store.list_audit_events(paths, event_type="test.event")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["payload"]["trace_id"], "trace-test-123")

    def test_structured_log_writer_emits_jsonl_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir))
            with patch.object(app_module, "_runtime_paths", return_value=paths):
                token = set_trace_id("trace-log-xyz")
                try:
                    app_module._write_structured_log("request.start", {"path": "/health"})
                finally:
                    reset_trace_id(token)
            log_path = paths.logs_dir / "structured.log"
            self.assertTrue(log_path.exists())
            rows = log_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(rows), 1)
            obj = json.loads(rows[0])
            self.assertEqual(obj["event_type"], "request.start")
            self.assertEqual(obj["trace_id"], "trace-log-xyz")

    def test_audit_events_endpoint_returns_filtered_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir))
            sqlite_store.init_db(paths)
            sqlite_store.append_audit_event(paths, "event.a", {"x": 1})
            sqlite_store.append_audit_event(paths, "event.b", {"x": 2})
            with patch.object(app_module, "_runtime_paths", return_value=paths):
                response = app_module.audit_events(event_type="event.a", limit=10)
            self.assertEqual(response["count"], 1)
            self.assertEqual(response["events"][0]["event_type"], "event.a")


if __name__ == "__main__":
    unittest.main()
