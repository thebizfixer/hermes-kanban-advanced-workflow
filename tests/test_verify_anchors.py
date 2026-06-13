"""Tests for verify_anchors.py."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "plans" / "anchors_sample.plan.md"


class TestVerifyAnchors(unittest.TestCase):
    def test_runs_without_anchor_lines_when_no_repo_file(self) -> None:
        script = ROOT / "scripts" / "verify_anchors.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--plan", str(FIXTURE), "--profile", "advisory"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertIn("Anchor Verification", proc.stdout)
        self.assertIn("anchor", proc.stdout.lower())


if __name__ == "__main__":
    unittest.main()
