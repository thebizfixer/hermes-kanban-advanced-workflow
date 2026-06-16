"""Tests for final_audit_sanity.py core logic."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from final_audit import (  # noqa: E402
    AuditContext,
    Violation,
    _path_cleared_by_prior_commit,
    fingerprint_from_missed_line,
    group_remediation_cards,
    load_violations_from_reports,
    mark_violations_escalated_in_reports,
    read_overlay_audit_settings,
    resolve_baseline_sha,
    run_tier1,
    verify_doc_tests,
    write_tier_report,
)


class TestFinalAuditSanity(unittest.TestCase):
    def test_resolve_baseline_sha_from_audit_card(self) -> None:
        body = "Audit-baseline-sha: abc123deadbeef\nType: audit"
        self.assertEqual(resolve_baseline_sha(body, Path(".")), "abc123deadbeef")

    def test_group_remediation_dedupe_by_files_union(self) -> None:
        violations = [
            Violation("tier1", "acceptance_miss", "docs/a.md", "miss1", remediates_task_id="t_1"),
            Violation("tier2", "doc_coverage_gap", "docs/a.md", "miss2", remediates_task_id="t_1"),
        ]
        groups = group_remediation_cards(violations)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["missed"]), 2)

    def test_empty_path_violations_do_not_merge(self) -> None:
        violations = [
            Violation("tier1", "plan_todo_drift", "", "todo A pending"),
            Violation("tier1", "plan_todo_drift", "", "todo B pending"),
        ]
        groups = group_remediation_cards(violations)
        self.assertEqual(len(groups), 2)

    def test_gave_up_fingerprint_roundtrip(self) -> None:
        line = "[tier1] acceptance_miss: detail one"
        fp = fingerprint_from_missed_line(line)
        self.assertIsNotNone(fp)
        v = Violation("tier1", "acceptance_miss", "a.py", "detail one")
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            write_tier_report(report_dir, "p1", "tier1", [v])
            mark_violations_escalated_in_reports(report_dir, "p1", {fp})  # type: ignore[arg-type]
            loaded = load_violations_from_reports(report_dir, "p1")
            self.assertEqual(loaded, [])

    def test_verify_doc_link_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "wiki" / "foo.md"
            doc.parent.mkdir(parents=True)
            doc.write_text("# Foo\nSee [bar](../README.md)\n", encoding="utf-8")
            (root / "README.md").write_text("# Root\n", encoding="utf-8")
            ok, err = verify_doc_tests("doc: link-check", str(root), ["wiki/foo.md"])
            self.assertTrue(ok, err)

    def test_tier1_unplanned_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts" / "new.py").write_text("x = 1\n", encoding="utf-8")
            plan = "**Files:** `scripts/existing.py`\n"
            ctx = AuditContext(
                plan_id="p1",
                repo_root=root,
                baseline="abc",
                plan_path=root / "plan.md",
                plan_text=plan,
                cards=[],
            )
            with patch("final_audit.git_changed_paths", return_value={"scripts/new.py"}):
                with patch("final_audit.file_has_diff", return_value=True):
                    violations = run_tier1(ctx)
            classes = [v.class_name for v in violations]
            self.assertIn("unplanned_change", classes)

    def test_tier1_plan_file_zero_diff_without_prior_commit(self) -> None:
        plan = "**Files:** `scripts/foo.py`\n"
        ctx = AuditContext(
            plan_id="p1",
            repo_root=Path("."),
            baseline="abc123",
            plan_path=Path("plan.md"),
            plan_text=plan,
            cards=[],
        )
        with patch("final_audit.git_changed_paths", return_value=set()):
            with patch("final_audit.file_has_diff", return_value=False):
                with patch("final_audit._path_cleared_by_prior_commit", return_value=None):
                    violations = run_tier1(ctx)
        classes = [v.class_name for v in violations]
        self.assertIn("plan_file_zero_diff", classes)

    def test_tier1_plan_file_zero_diff_cleared_by_prior_commit(self) -> None:
        plan = "**Files:** `scripts/foo.py`\n"
        card_body = (
            "plan_id: p1\n"
            "Files: scripts/foo.py\n"
            "Commit: feat: add foo\n"
            "Mode: modify-only\n"
            "```agent\nagent -p 'x'\n```"
        )
        cards = [{"task_id": "t_1", "body": card_body, "status": "done"}]
        ctx = AuditContext(
            plan_id="p1",
            repo_root=Path("."),
            baseline="abc123",
            plan_path=Path("plan.md"),
            plan_text=plan,
            cards=cards,
        )
        with patch("final_audit.git_changed_paths", return_value=set()):
            with patch("final_audit.file_has_diff", return_value=False):
                with patch("final_audit._path_cleared_by_prior_commit", return_value="deadbeef01"):
                    violations = run_tier1(ctx)
        classes = [v.class_name for v in violations]
        self.assertNotIn("plan_file_zero_diff", classes)

    def test_path_cleared_by_prior_commit_delegates_to_find_prior_commit(self) -> None:
        surfaces = {
            "t_1": {
                "files": ["scripts/foo.py"],
                "commit": "feat: add foo",
            }
        }
        root = Path(".")
        with patch("card_body.find_prior_commit", return_value="abc12345") as mock_find:
            sha = _path_cleared_by_prior_commit("scripts/foo.py", surfaces, "base000", root)
        self.assertEqual(sha, "abc12345")
        mock_find.assert_called_once()
        args, kwargs = mock_find.call_args
        self.assertEqual(args[0], "feat: add foo")
        self.assertEqual(args[1], ["scripts/foo.py"])
        self.assertEqual(args[2], str(root))
        self.assertEqual(kwargs.get("baseline"), "base000")

    def test_write_tier_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            v = Violation("tier1", "acceptance_miss", "a.py", "detail")
            path = write_tier_report(out, "plan-x", "tier1", [v])
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["violation_count"], 1)

    def test_read_overlay_max_rounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overlay = root / ".hermes" / "kanban-overrides"
            overlay.mkdir(parents=True)
            (overlay / "kanban-config.yaml").write_text(
                "final_audit_max_remediation_rounds: 5\n", encoding="utf-8"
            )
            _, max_rounds = read_overlay_audit_settings(root)
            self.assertEqual(max_rounds, 5)


if __name__ == "__main__":
    unittest.main()
