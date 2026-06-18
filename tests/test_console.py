"""Tests for scripts/lib/console.py and ASCII-safe gate output."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import console  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "plans" / "anchors_sample.plan.md"


class TestConsole(unittest.TestCase):
    def test_labels_are_ascii(self) -> None:
        for line in (
            console.pass_line("ok"),
            console.warn_line("stale"),
            console.fail_line("missing"),
            console.status_line("PASS", "done"),
        ):
            line.encode("ascii")

    def test_supports_color_without_tty(self) -> None:
        self.assertFalse(console.supports_color())


class TestVerifyAnchorsAscii(unittest.TestCase):
    def test_cp1252_stdout_on_fail_path(self) -> None:
        script = ROOT / "scripts" / "verify_anchors.py"
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "cp1252"
        proc = subprocess.run(
            [sys.executable, str(script), "--plan", str(FIXTURE), "--profile", "advisory"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="cp1252",
            errors="strict",
            env=env,
        )
        self.assertIn("Anchor Verification", proc.stdout)
        self.assertIn("FAIL:", proc.stdout)
        self.assertNotIn("\u2717", proc.stdout)

    def test_json_counts_for_wrappers(self) -> None:
        script = ROOT / "scripts" / "verify_anchors.py"
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                "--plan",
                str(FIXTURE),
                "--profile",
                "advisory",
                "--json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, 0)
        import json

        data = json.loads(proc.stdout)
        self.assertEqual(data["failures"], 1)
        self.assertEqual(data["warnings"], 0)


if __name__ == "__main__":
    unittest.main()
