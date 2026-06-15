"""Tests for kanban_handoff bundle and cards_yaml resolution."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import kanban_handoff as handoff  # noqa: E402


class TestKanbanHandoff(unittest.TestCase):
    def test_resolve_bundle_root_finds_repo_checkout(self) -> None:
        project_root = ROOT
        overlay = {"bundle_path": "hermes-kanban-advanced-workflow"}
        bundle = handoff._resolve_bundle_root(project_root, overlay)
        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertTrue((bundle / "scripts" / "coding_agent_invoke.sh").is_file())

    def test_discover_cards_yaml_in_plan_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / ".hermes" / "kanban" / "memory"
            memory.mkdir(parents=True)
            yaml_path = memory / "test-plan.yaml"
            yaml_path.write_text("cards: []\n", encoding="utf-8")
            plan = root / ".agent" / "plans" / "test-plan.plan.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("---\nplan_id: test-plan\n---\n", encoding="utf-8")
            found = handoff._discover_cards_yaml("test-plan", plan, root, {})
            self.assertEqual(found, yaml_path.resolve())

    def test_parse_gate_failed_checks(self) -> None:
        out = (
            "[GATE] plan on main ... FAIL\n"
            "[GATE] attestation ... FAIL\n"
            "[GATE] Result: 2 failures, 0 warnings\n"
        )
        failed = handoff._parse_gate_failed_checks(out, "")
        self.assertEqual(failed, ["plan on main", "attestation"])

    def test_parse_gate_result(self) -> None:
        out = "[GATE] Result: 0 failures, 2 warnings\n[GATE] PASSED"
        parsed = handoff._parse_gate_result(out, "")
        self.assertEqual(parsed, (0, 2))

    def test_gate_timeout_hint_on_timeout_message(self) -> None:
        self.assertIn("PREFLIGHT_SKIP_CODING_AGENT_CLI", handoff._gate_timeout_hint("timed out"))

    def test_gate_timeout_hint_on_coding_agent_failure(self) -> None:
        self.assertIn(
            "PREFLIGHT_SKIP_CODING_AGENT_CLI",
            handoff._gate_timeout_hint("coding_agent_cli smoke failed"),
        )

    def test_gate_timeout_hint_absent_for_unrelated(self) -> None:
        self.assertEqual(handoff._gate_timeout_hint("attestation missing"), "")

    def test_cards_for_plan_matches_body(self) -> None:
        cards = [
            {"id": "t_abc12345", "status": "done", "title": "Gate", "body": "plan_id: foo\n"},
            {"id": "t_def67890", "status": "ready", "title": "Other", "body": "plan_id: bar\n"},
        ]
        original = handoff._list_cards
        handoff._list_cards = lambda: cards  # type: ignore[method-assign]
        try:
            matched = handoff._cards_for_plan("foo")
            self.assertEqual(len(matched), 1)
            self.assertEqual(matched[0]["id"], "t_abc12345")
        finally:
            handoff._list_cards = original  # type: ignore[method-assign]

    def test_board_cleanliness_blocks_running(self) -> None:
        cards = [
            {"id": "t_run12345", "status": "running", "title": "Card", "body": "plan_id: p1\n"},
        ]
        original = handoff._list_cards
        handoff._list_cards = lambda: cards  # type: ignore[method-assign]
        try:
            ok, msg, archived = handoff._check_board_cleanliness("p1", force=False)
            self.assertFalse(ok)
            self.assertIn("running", msg.lower())
            self.assertEqual(archived, [])
        finally:
            handoff._list_cards = original  # type: ignore[method-assign]

    def test_board_cleanliness_prompts_archive_when_done(self) -> None:
        cards = [
            {"id": "t_done1234", "status": "done", "title": "Old", "body": "plan_id: p2\n"},
        ]
        original = handoff._list_cards
        handoff._list_cards = lambda: cards  # type: ignore[method-assign]
        try:
            ok, msg, archived = handoff._check_board_cleanliness("p2", force=False)
            self.assertFalse(ok)
            self.assertIn("Confirm with the operator", msg)
            self.assertIn("hermes kanban archive", msg)
        finally:
            handoff._list_cards = original  # type: ignore[method-assign]

    @unittest.skipUnless(os.name == "nt", "MSYS path conversion is Windows-specific")
    def test_bash_path_windows_drive(self) -> None:
        path = handoff.Path("E:/Projects/foo/scripts/pre_dispatch_gate.sh")
        self.assertEqual(
            handoff._bash_path(path),
            "/e/Projects/foo/scripts/pre_dispatch_gate.sh",
        )


if __name__ == "__main__":
    unittest.main()
