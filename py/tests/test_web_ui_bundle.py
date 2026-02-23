from __future__ import annotations

import unittest
from pathlib import Path


class WebUiBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2]
        self.index_html = (self.root / "apps" / "fin-agent-web" / "dist" / "index.html").read_text(encoding="utf-8")
        self.app_js = (self.root / "apps" / "fin-agent-web" / "dist" / "assets" / "app.js").read_text(encoding="utf-8")

    def test_dist_bundle_has_chat_timeline_and_action_cards(self) -> None:
        self.assertIn('id="chat-panel"', self.index_html)
        self.assertIn('id="timeline-panel"', self.index_html)
        self.assertIn('id="action-cards"', self.index_html)

    def test_dist_bundle_has_workspace_sections(self) -> None:
        self.assertIn('id="workspace-backtests"', self.index_html)
        self.assertIn('id="workspace-tuning"', self.index_html)
        self.assertIn('id="workspace-live"', self.index_html)
        self.assertIn('id="workspace-diagnostics"', self.index_html)

    def test_app_bundle_calls_required_chat_and_workspace_endpoints(self) -> None:
        required = [
            "/v1/chat/respond",
            "/v1/chat/sessions",
            "/v1/chat/sessions/",
            "/v1/backtests/runs",
            "/v1/tuning/runs",
            "/v1/live/states",
            "/v1/providers/health",
            "/v1/diagnostics/readiness",
            "/v1/audit/events",
        ]
        for endpoint in required:
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, self.app_js)


if __name__ == "__main__":
    unittest.main()
