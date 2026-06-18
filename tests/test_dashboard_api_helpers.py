"""Unit tests for dashboard API helpers."""

from __future__ import annotations

import unittest

try:
    from dashboard.plugin_api import _coerce_max_turns
except ImportError:  # pragma: no cover - optional deps in minimal CI
    _coerce_max_turns = None  # type: ignore[assignment,misc]


@unittest.skipIf(_coerce_max_turns is None, "dashboard.plugin_api not importable")
class TestCoerceMaxTurns(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(_coerce_max_turns(None), 180)
        self.assertEqual(_coerce_max_turns(True), 180)

    def test_int_and_string(self) -> None:
        self.assertEqual(_coerce_max_turns(200), 200)
        self.assertEqual(_coerce_max_turns("240"), 240)

    def test_invalid_falls_back(self) -> None:
        self.assertEqual(_coerce_max_turns("nope"), 180)


if __name__ == "__main__":
    unittest.main()
