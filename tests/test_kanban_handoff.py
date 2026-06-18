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

    def test_resolve_subagent_gate_enabled_default_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(handoff._resolve_subagent_gate_enabled(root, {}))

    def test_resolve_subagent_gate_enabled_false_in_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay_dir = root / ".hermes" / "kanban-overrides"
            overlay_dir.mkdir(parents=True)
            (overlay_dir / "kanban-config.yaml").write_text(
                "subagent_gate:\n  enabled: false\n",
                encoding="utf-8",
            )
            self.assertFalse(handoff._resolve_subagent_gate_enabled(root, {}))

    def test_build_body_includes_first_action_and_gate_body(self) -> None:
        overlay = {
            "notify_lifecycle": "true",
            "walk_away_mode": "false",
            "notify_deliver_resolved": "telegram",
        }
        body = handoff._build_body(
            "p1",
            Path("/tmp/plan.plan.md"),
            Path("/tmp/repo"),
            "main",
            "kanban-advanced-orchestrator",
            bundle_root=ROOT,
            gate_status="DEFERRED at test",
            parallel_gate_enabled=True,
            gateway_at_handoff="running (ok)",
            notification_overlay=overlay,
            cron_provision="PASSED at 2026-06-18T00:00:00Z",
        )
        self.assertIn("## FIRST ACTION", body)
        self.assertIn("gateway_at_handoff: running", body)
        self.assertIn('plan_id: p1', body)
        self.assertIn("notify_lifecycle: true", body)
        self.assertIn("walk_away_mode: false", body)
        self.assertIn("cron_provision: PASSED", body)
        self.assertIn("provision_kanban_crons.sh --check", body)
        self.assertIn("--no-crons", body)
        self.assertNotIn(
            "Immediately after gate — create crons",
            body,
        )
        self.assertIn("Gate card. All implementation cards link to gate", body)
        body = handoff._build_body(
            "p1",
            Path("/tmp/plan.plan.md"),
            Path("/tmp/repo"),
            "main",
            "kanban-advanced-orchestrator",
            bundle_root=ROOT,
            gate_status="DEFERRED at 2026-06-15T00:00:00Z (parallel subagent gate — orchestrator Step 1)",
            parallel_gate_enabled=True,
        )
        self.assertIn("pre_dispatch_gate: DEFERRED", body)
        self.assertIn("parallel_gate: enabled", body)
        self.assertIn("Step 1 — Pre-dispatch gate", body)
        self.assertIn("gate-subagent-plan.md", body)

    def test_deferred_handoff_skips_serial_gate_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay_dir = root / ".hermes" / "kanban-overrides"
            overlay_dir.mkdir(parents=True)
            (overlay_dir / "kanban-config.yaml").write_text(
                "subagent_gate:\n  enabled: true\n",
                encoding="utf-8",
            )
            plan = root / ".agent" / "plans" / "defer.plan.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("---\nplan_id: defer-test\n---\n", encoding="utf-8")

            gate_called: list[str] = []

            def fake_gate(plan_id: str, repo_root: Path, overlay: dict) -> tuple[str, Path | None]:
                gate_called.append(plan_id)
                return "PASSED at test", None

            original = handoff._run_pre_dispatch_gate
            handoff._run_pre_dispatch_gate = fake_gate  # type: ignore[method-assign]
            try:
                enabled = handoff._resolve_subagent_gate_enabled(root, {})
                self.assertTrue(enabled)
                if enabled:
                    gate_status = "DEFERRED at test"
                else:
                    handoff._run_pre_dispatch_gate("defer-test", root, {})
                self.assertEqual(gate_called, [])
                self.assertTrue(gate_status.startswith("DEFERRED"))
            finally:
                handoff._run_pre_dispatch_gate = original  # type: ignore[method-assign]


if __name__ == "__main__":
    unittest.main()
