from __future__ import annotations

import unittest
from pathlib import Path


class WorkflowFilesTests(unittest.TestCase):
    def test_ci_workflow_contains_publish_and_e2e_gates(self) -> None:
        root = Path(__file__).resolve().parents[2]
        text = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("publish-readiness.sh", text)
        self.assertIn("e2e-full.sh --skip-doctor", text)
        self.assertIn("release-tui.sh --dry-run", text)

    def test_release_workflow_contains_artifact_and_npm_publish(self) -> None:
        root = Path(__file__).resolve().parents[2]
        text = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("action-gh-release", text)
        self.assertIn("NPM_TOKEN", text)
        self.assertIn("npm publish --access public", text)
        self.assertIn("release-tui.sh --version", text)


if __name__ == "__main__":
    unittest.main()
