"""Tests for plugin/file_text.py legacy encoding repair."""

from __future__ import annotations

import unittest

from plugin.file_text import read_utf8_text, repair_legacy_text_bytes


class TestFileText(unittest.TestCase):
    def test_repair_lone_section_byte(self) -> None:
        raw = b"see `plan-file-format.md` \xa7 Declared anchors"
        fixed = repair_legacy_text_bytes(raw)
        self.assertEqual(fixed.decode("utf-8"), "see `plan-file-format.md` \u00a7 Declared anchors")

    def test_repair_mojibake_section(self) -> None:
        raw = b"orchestrator` \xc3\x82\xc2\xa7 Step 0c"
        fixed = repair_legacy_text_bytes(raw)
        self.assertIn("\u00a7 Step 0c", fixed.decode("utf-8"))

    def test_read_utf8_text_roundtrip(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.md"
            path.write_text("hello", encoding="utf-8")
            self.assertEqual(read_utf8_text(path), "hello")


if __name__ == "__main__":
    unittest.main()
