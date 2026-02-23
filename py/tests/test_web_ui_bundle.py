from __future__ import annotations

import unittest
from pathlib import Path


class WebUiBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2]
        dist_dir = self.root / "apps" / "fin-agent-web" / "dist"
        self.index_html = (dist_dir / "index.html").read_text(encoding="utf-8")
        assets_dir = dist_dir / "assets"
        js_assets = sorted(assets_dir.glob("*.js"))
        self.assertGreater(len(js_assets), 0, "expected at least one compiled JS asset in dist/assets")
        self.app_js = js_assets[0].read_text(encoding="utf-8")

    def test_dist_bundle_has_root_and_compiled_asset_references(self) -> None:
        self.assertIn('id="root"', self.index_html)
        self.assertIn('/app/assets/index-', self.index_html)
        self.assertIn('.js', self.index_html)
        self.assertIn('.css', self.index_html)

    def test_app_bundle_contains_expected_stage1_scaffold_text(self) -> None:
        self.assertIn("Fin-Agent Stage 1", self.app_js)
        self.assertIn("Chat-centric strategy workspace powered by OpenCode + Fin-Agent tools.", self.app_js)
        self.assertIn("Web UI scaffold ready", self.app_js)


if __name__ == "__main__":
    unittest.main()
