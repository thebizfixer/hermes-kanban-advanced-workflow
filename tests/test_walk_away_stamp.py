"""Walk-away handoff stamp fixture — orchestrator reads stamp before overlay."""

from __future__ import annotations

import re
import unittest


HANDOFF_BODY_FIXTURE = """
Type: orchestrator-handoff
plan_id: example-plan
walk_away_mode: true
notify_lifecycle: true
notify_deliver_resolved: gateway
cron_provision: checked
pre_dispatch_gate: DEFERRED
"""


def read_stamp_field(body: str, field: str) -> str | None:
    m = re.search(rf"^{re.escape(field)}:\s*(.+)$", body, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else None


class TestWalkAwayStampFixture(unittest.TestCase):
    def test_handoff_stamps_walk_away_first(self) -> None:
        self.assertEqual(read_stamp_field(HANDOFF_BODY_FIXTURE, "walk_away_mode"), "true")
        self.assertEqual(read_stamp_field(HANDOFF_BODY_FIXTURE, "notify_lifecycle"), "true")

    def test_missing_stamp_falls_back_to_overlay(self) -> None:
        body = "Type: orchestrator-handoff\nplan_id: p1\n"
        self.assertIsNone(read_stamp_field(body, "walk_away_mode"))


if __name__ == "__main__":
    unittest.main()
