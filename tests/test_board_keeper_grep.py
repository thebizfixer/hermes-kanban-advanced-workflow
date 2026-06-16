"""Regression: board_keeper empty grep must not abort under pipefail."""

from __future__ import annotations

import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("bash"), "bash required")
class TestBoardKeeperGrepPipefail(unittest.TestCase):
    def test_empty_grep_with_or_true_succeeds_under_pipefail(self) -> None:
        script = r"""
set -euo pipefail
BLOCKED_IDS=$(printf 'no blocked lines\n' | grep '⊘' | awk '{print $2}' || true)
echo "ok:${BLOCKED_IDS}"
"""
        proc = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ok:", proc.stdout)


if __name__ == "__main__":
    unittest.main()
