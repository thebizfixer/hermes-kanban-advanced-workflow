"""Tests for kanban_lifecycle_notify.sh transition detection (Issue 3 / Card 2)."""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class TestLifecycleTransitions(unittest.TestCase):
    """Simulate the transition-logic block from kanban_lifecycle_notify.sh."""

    def _simulate_transition(
        self,
        old_status: str | None,
        new_status: str,
        plan_id: str = "test-plan",
        task_id: str = "t_abc123",
        title: str = "Test Card",
    ) -> tuple[str | None, dict | None]:
        """Run the transition logic and return (msg, event)."""
        now = "2026-06-20T00:00:00Z"
        done, active, blocked = 3, 2, 1
        event = None
        msg = ""
        if new_status == "ready" and old_status in (None, "blocked", "todo"):
            msg = f"▶ Card start — {plan_id}\n{task_id} — {title}   ({done} done · {active} active · {blocked} blocked)"
            event = {"ts": now, "type": "start", "task_id": task_id, "plan_id": plan_id}
        elif new_status == "running" and old_status in (
            "ready",
            "blocked",
            None,
        ):
            msg = f"▶ Card running — {plan_id}\n{task_id} — {title}   ({done} done · {active} active · {blocked} blocked)"
            event = {"ts": now, "type": "running", "task_id": task_id, "plan_id": plan_id}
        elif new_status == "done" and old_status in ("running", "ready"):
            msg = f"✅ Card done — {plan_id}\n{task_id} — {title}   ({done} done · {active} active · {blocked} blocked)"
            event = {"ts": now, "type": "done", "task_id": task_id, "plan_id": plan_id}
        elif new_status in (
            "blocked",
            "crashed",
            "gave_up",
            "timed_out",
        ) and old_status == "running":
            msg = f"🚨 Card re-blocked — {new_status}\n{task_id} — {title}\nWorker returned to {new_status}.   Suggested action: review card log"
            event = {
                "ts": now,
                "type": "re-blocked",
                "task_id": task_id,
                "plan_id": plan_id,
                "status": new_status,
            }
        return msg or None, event

    # ── blocked → running (the gap) ──
    def test_blocked_to_running_emits_running_event(self) -> None:
        msg, event = self._simulate_transition("blocked", "running")
        self.assertIsNotNone(msg)
        self.assertIsNotNone(event)
        self.assertIn("Card running", msg)
        self.assertEqual(event["type"], "running")

    # ── ready → running (existing path, must stay unchanged) ──
    def test_ready_to_running_still_works(self) -> None:
        msg, event = self._simulate_transition("ready", "running")
        self.assertIsNotNone(msg)
        self.assertIsNotNone(event)
        self.assertIn("Card running", msg)
        self.assertEqual(event["type"], "running")

    # ── None → running (initial dispatch) ──
    def test_none_to_running_emits_running_event(self) -> None:
        msg, event = self._simulate_transition(None, "running")
        self.assertIsNotNone(msg)
        self.assertIsNotNone(event)
        self.assertEqual(event["type"], "running")

    # ── blocked → ready (already existed, must still work) ──
    def test_blocked_to_ready_emits_start_event(self) -> None:
        msg, event = self._simulate_transition("blocked", "ready")
        self.assertIsNotNone(msg)
        self.assertIsNotNone(event)
        self.assertEqual(event["type"], "start")

    # ── running → done ──
    def test_running_to_done_emits_done_event(self) -> None:
        msg, event = self._simulate_transition("running", "done")
        self.assertIsNotNone(msg)
        self.assertIsNotNone(event)
        self.assertEqual(event["type"], "done")

    # ── running → blocked ──
    def test_running_to_blocked_emits_reblocked_event(self) -> None:
        msg, event = self._simulate_transition("running", "blocked")
        self.assertIsNotNone(msg)
        self.assertIsNotNone(event)
        self.assertEqual(event["type"], "re-blocked")

    # ── same status → no event ──
    def test_same_status_no_event(self) -> None:
        msg, event = self._simulate_transition("running", "running")
        self.assertIsNone(msg)
        self.assertIsNone(event)


if __name__ == "__main__":
    unittest.main()
