"""CLI integration tests for final_audit_sanity.py (mocked hermes/git)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import final_audit_sanity as fas  # noqa: E402
from final_audit import Violation, write_tier_report  # noqa: E402


class TestFinalAuditSanityCli(unittest.TestCase):
    def _seed_plan(self, root: Path, plan_id: str) -> None:
        plans = root / ".agent" / "plans"
        plans.mkdir(parents=True)
        (plans / f"{plan_id}.plan.md").write_text(
            f"plan_id: {plan_id}\n\n**Files:** `README.md`\n",
            encoding="utf-8",
        )

    def _write_tier_reports(self, root: Path, plan_id: str) -> None:
        report_dir = root / ".hermes" / "kanban" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        v = Violation("tier1", "acceptance_miss", "a.py", "missing acceptance")
        write_tier_report(report_dir, plan_id, "tier1", [v])

    def test_exit_0_clean_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "clean-plan"
            self._seed_plan(root, plan_id)
            audit_body = "plan_id: clean-plan\nType: audit\nAudit-round: 0\n"
            cards = [{"task_id": "t_audit", "body": audit_body, "status": "ready"}]

            with patch.object(fas, "_project_root", return_value=root):
                with patch.object(fas, "_load_cards_from_db", return_value=cards):
                    with patch.object(fas, "run_tier1", return_value=[]):
                        with patch.object(fas, "run_tier2", return_value=[]):
                            with patch.object(fas, "git_changed_paths", return_value=set()):
                                rc = fas.main(["--plan-id", plan_id, "--repo-root", str(root)])
            self.assertEqual(rc, 0)

    def test_exit_1_violations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "dirty-plan"
            self._seed_plan(root, plan_id)
            audit_body = "plan_id: dirty-plan\nType: audit\n"
            cards = [{"task_id": "t_audit", "body": audit_body, "status": "ready"}]
            fail = Violation("tier1", "acceptance_miss", "a.py", "detail")

            with patch.object(fas, "_project_root", return_value=root):
                with patch.object(fas, "_load_cards_from_db", return_value=cards):
                    with patch.object(fas, "run_tier1", return_value=[fail]):
                        with patch.object(fas, "run_tier2", return_value=[]):
                            with patch.object(fas, "git_changed_paths", return_value=set()):
                                rc = fas.main(["--plan-id", plan_id, "--repo-root", str(root)])
            self.assertEqual(rc, 1)

    def test_exit_2_missing_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(fas, "_project_root", return_value=root):
                with patch.object(fas, "_load_cards_from_db", return_value=[]):
                    rc = fas.main(["--plan-id", "missing", "--repo-root", str(root)])
            self.assertEqual(rc, 2)

    def test_spawn_max_rounds_escalates_and_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "max-rounds"
            self._seed_plan(root, plan_id)
            overlay = root / ".hermes" / "kanban-overrides"
            overlay.mkdir(parents=True)
            (overlay / "kanban-config.yaml").write_text(
                "final_audit_max_remediation_rounds: 1\n", encoding="utf-8"
            )
            audit_body = "plan_id: max-rounds\nType: audit\nAudit-round: 1\n"
            cards = [{"task_id": "t_audit", "body": audit_body, "status": "ready"}]
            self._write_tier_reports(root, plan_id)
            blocked: list[str] = []
            escalated: list[tuple[str, str]] = []

            def fake_escalation(scripts_dir, task_id, reason, repo_root):  # noqa: ANN001
                escalated.append((task_id, reason))

            def fake_block(audit_id, summary, dry_run):  # noqa: ANN001
                blocked.append(audit_id)

            with patch.object(fas, "_project_root", return_value=root):
                with patch.object(fas, "_load_cards_from_db", return_value=cards):
                    with patch.object(fas, "_gave_up_remediation_children", return_value=[]):
                        with patch.object(fas, "run_escalation_tracker", side_effect=fake_escalation):
                            with patch.object(fas, "_block_audit_card", side_effect=fake_block):
                                rc = fas.main(
                                    [
                                        "--plan-id",
                                        plan_id,
                                        "--repo-root",
                                        str(root),
                                        "--spawn-remediation",
                                    ]
                                )
            self.assertEqual(rc, 1)
            self.assertEqual(blocked, ["t_audit"])
            self.assertTrue(escalated)
            self.assertIn("t_audit", escalated[0][0])

    def test_gave_up_marks_escalated_and_filters_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_id = "gave-up-plan"
            self._seed_plan(root, plan_id)
            report_dir = root / ".hermes" / "kanban" / "reports"
            report_dir.mkdir(parents=True)
            v = Violation("tier1", "acceptance_miss", "a.py", "detail one")
            write_tier_report(report_dir, plan_id, "tier1", [v])
            gave_up_body = (
                "plan_id: gave-up-plan\nType: remediation\nMissed:\n"
                "- [tier1] acceptance_miss: detail one\n"
            )
            audit_body = "plan_id: gave-up-plan\nType: audit\nAudit-round: 0\n"
            cards = [{"task_id": "t_audit", "body": audit_body, "status": "ready"}]
            spawned: list[str] = []

            def fake_spawn(title, body, assignee, parent_id):  # noqa: ANN001
                spawned.append(title)
                return "t_rem"

            with patch.object(fas, "_project_root", return_value=root):
                with patch.object(fas, "_load_cards_from_db", return_value=cards):
                    with patch.object(
                        fas,
                        "_gave_up_remediation_children",
                        return_value=[{"task_id": "t_gu", "body": gave_up_body, "status": "gave_up"}],
                    ):
                        with patch.object(fas, "run_escalation_tracker"):
                            with patch.object(fas, "_spawn_card", side_effect=fake_spawn):
                                with patch.object(fas, "_update_audit_round"):
                                    rc = fas.main(
                                        [
                                            "--plan-id",
                                            plan_id,
                                            "--repo-root",
                                            str(root),
                                            "--spawn-remediation",
                                        ]
                                    )
            self.assertEqual(rc, 0)
            self.assertEqual(spawned, [])
            tier1 = json.loads((report_dir / f"{plan_id}_audit_tier1.json").read_text(encoding="utf-8"))
            self.assertEqual(tier1["violations"][0].get("status"), "escalated")


if __name__ == "__main__":
    unittest.main()
