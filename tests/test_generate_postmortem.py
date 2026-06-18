"""Tests for generate_postmortem.py plan scoping."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_postmortem as pm  # noqa: E402


class TestGeneratePostmortem(unittest.TestCase):
    def test_load_task_history_uses_plan_memory_task_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mem_dir = root / ".hermes" / "kanban" / "memory"
            mem_dir.mkdir(parents=True)
            (mem_dir / "my-plan.json").write_text(
                json.dumps({"task_ids": ["t_a", "t_b"]}),
                encoding="utf-8",
            )
            db = root / "kanban.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE tasks (id TEXT, title TEXT, status TEXT, body TEXT, plan_id TEXT)"
            )
            conn.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?)",
                ("t_a", "A", "done", "plan_id: my-plan", "my-plan"),
            )
            conn.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?)",
                ("t_b", "B", "done", "plan_id: my-plan", "my-plan"),
            )
            conn.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?)",
                ("t_other", "Other", "done", "plan_id: other-plan mentions my-plan", "other-plan"),
            )
            conn.commit()
            conn.close()

            tasks, notes = pm.load_task_history(db, "my-plan", root)
            ids = {t.task_id for t in tasks}
            self.assertEqual(ids, {"t_a", "t_b"})
            self.assertTrue(any("plan memory" in n for n in notes))

    def test_load_task_history_treats_archived_as_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mem_dir = root / ".hermes" / "kanban" / "memory"
            mem_dir.mkdir(parents=True)
            (mem_dir / "my-plan.json").write_text(
                json.dumps({"task_ids": ["t_a", "t_b"]}),
                encoding="utf-8",
            )
            db = root / "kanban.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE tasks (id TEXT, title TEXT, status TEXT, body TEXT, plan_id TEXT)"
            )
            conn.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?)",
                ("t_a", "A", "archived", "plan_id: my-plan", "my-plan"),
            )
            conn.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?)",
                ("t_b", "B", "done", "plan_id: my-plan", "my-plan"),
            )
            conn.commit()
            conn.close()

            tasks, notes = pm.load_task_history(db, "my-plan", root)
            self.assertEqual(len(tasks), 2)
            kpi = pm.build_kpi_json(
                plan_id="my-plan",
                tasks=tasks,
                token_entries=[],
                intervention_count=0,
                intervention_log=[],
                scope_violations=[],
            )
            self.assertEqual(kpi["total_tasks"], 2)
            self.assertEqual(kpi["success_rate"], 100.0)
            self.assertTrue(any("archived" in n.lower() for n in notes))

    def test_build_kpi_json_writes_expected_keys(self) -> None:
        task = pm.TaskRecord(
            task_id="t_rem",
            body="Type: remediation\nRemediates: t_parent\nMissed: call site X",
            status="done",
        )
        kpi = pm.build_kpi_json(
            plan_id="p1",
            tasks=[task],
            token_entries=[],
            intervention_count=0,
            intervention_log=[],
            scope_violations=[],
        )
        self.assertEqual(kpi["plan_id"], "p1")
        self.assertIn("completeness", kpi)
        self.assertEqual(kpi["completeness"]["violation_count"], 1)
        self.assertEqual(kpi["completeness"]["orchestrator_catch_count"], 1)
        self.assertIn("auth_escalation_count", kpi)

    def test_build_kpi_json_null_uncaught_when_tier_json_absent(self) -> None:
        kpi = pm.build_kpi_json(
            plan_id="p1",
            tasks=[],
            token_entries=[],
            intervention_count=0,
            intervention_log=[],
            scope_violations=[],
            repo_root=Path("/nonexistent"),
        )
        self.assertIsNone(kpi["completeness"]["uncaught_violation_count"])
        self.assertIn("audit_tier_notes", kpi)

    def test_build_kpi_json_with_tier_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / ".hermes" / "kanban" / "reports"
            reports.mkdir(parents=True)
            (reports / "p1_audit_tier1.json").write_text(
                json.dumps({"violations": [{"class": "acceptance_miss"}]}),
                encoding="utf-8",
            )
            (reports / "p1_audit_tier2.json").write_text(
                json.dumps({"violations": []}),
                encoding="utf-8",
            )
            kpi = pm.build_kpi_json(
                plan_id="p1",
                tasks=[],
                token_entries=[],
                intervention_count=0,
                intervention_log=[],
                scope_violations=[],
                repo_root=root,
            )
            self.assertEqual(kpi["plan_scope_gaps"], 1)
            self.assertEqual(kpi["doc_coverage_gaps"], 0)
            self.assertIsNotNone(kpi["completeness"]["uncaught_violation_count"])

    def test_build_kpi_json_audit_round_from_audit_card(self) -> None:
        audit = pm.TaskRecord(
            task_id="t_audit",
            body="plan_id: p1\nType: audit\nAudit-round: 2\n",
            status="done",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / ".hermes" / "kanban" / "reports"
            reports.mkdir(parents=True)
            (reports / "p1_audit_tier1.json").write_text(
                json.dumps({"violations": [], "audit_round": 0}),
                encoding="utf-8",
            )
            (reports / "p1_audit_tier2.json").write_text(
                json.dumps({"violations": []}),
                encoding="utf-8",
            )
            kpi = pm.build_kpi_json(
                plan_id="p1",
                tasks=[audit],
                token_entries=[],
                intervention_count=0,
                intervention_log=[],
                scope_violations=[],
                repo_root=root,
            )
            self.assertEqual(kpi["final_audit_rounds"], 2)

    def test_build_report_includes_final_audit_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / ".hermes" / "kanban" / "reports"
            reports.mkdir(parents=True)
            (reports / "p1_audit_tier1.json").write_text(
                json.dumps({"violations": []}),
                encoding="utf-8",
            )
            (reports / "p1_audit_tier2.json").write_text(
                json.dumps({"violations": []}),
                encoding="utf-8",
            )
            audit = pm.TaskRecord(
                task_id="t_audit",
                body="plan_id: p1\nType: audit\nAudit-round: 1\n",
                status="done",
            )
            with patch.object(pm, "_project_root", return_value=root):
                report = pm.build_report(
                    plan_id="p1",
                    tasks=[audit],
                    token_entries=[],
                    intervention_count=0,
                    intervention_log=[],
                    scope_violations=[],
                    source_notes=[],
                )
            self.assertIn("### Final audit", report)
            self.assertIn("**Final audit rounds:** 1", report)
            self.assertIn("**Uncaught violations (goal 0):** 0", report)

    def test_write_kpi_json_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            kpi = {"plan_id": "p1", "success_rate": 100.0}
            dest = pm.write_kpi_json(kpi, out, "p1")
            self.assertTrue(dest.is_file())
            self.assertIn("p1_kpi.json", dest.name)
            history = out / "kpi_history.jsonl"
            self.assertTrue(history.is_file())

    def test_build_report_includes_operator_section(self) -> None:
        report = pm.build_report(
            plan_id="p1",
            tasks=[],
            token_entries=[],
            intervention_count=0,
            intervention_log=[],
            scope_violations=[],
            source_notes=["scoped via plan memory task_ids"],
        )
        self.assertIn("## 9. Operator Ground Truth", report)
        self.assertIn("Data confidence", report)

    def test_wall_clock_caps_at_audit_completion(self) -> None:
        from datetime import datetime, timedelta, timezone

        t0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        t_end = t0 + timedelta(hours=2)
        t_late = t0 + timedelta(hours=6)
        impl = pm.TaskRecord(
            task_id="t_impl",
            title="Card 1",
            status="done",
            body="plan_id: p1\n",
            created_at=t0,
            updated_at=t_end,
        )
        audit = pm.TaskRecord(
            task_id="t_audit",
            title="Final audit — p1",
            status="done",
            body="plan_id: p1\nType: audit\n",
            created_at=t0 + timedelta(minutes=30),
            updated_at=t_end,
        )
        handoff = pm.TaskRecord(
            task_id="t_handoff",
            title="Decompose: p1",
            status="ready",
            body="Type: orchestrator-handoff\nplan_id: p1\n",
            created_at=t0,
            updated_at=t_late,
        )
        hours = pm._wall_clock_hours([impl, audit, handoff])
        self.assertAlmostEqual(hours or 0, 2.0, places=1)

    def test_build_kpi_json_accepts_corrections(self) -> None:
        kpi = pm.build_kpi_json(
            plan_id="p1",
            tasks=[],
            token_entries=[],
            intervention_count=0,
            intervention_log=[],
            scope_violations=[],
            kpi_corrections={
                "wall_clock_hours_corrected": 2.5,
                "_source": "operator review",
            },
        )
        self.assertEqual(kpi["wall_clock_hours_corrected"], 2.5)
        self.assertEqual(kpi["correction_source"], "operator review")

    def test_build_kpi_json_excludes_foreign_token_rows(self) -> None:
        entries = [
            {"plan_id": "other-plan", "task_id": "t_x", "cursor": {"total": 9000}},
            {"plan_id": "p1", "task_id": "t_a", "cursor": {"total": 100}},
        ]
        kpi = pm.build_kpi_json(
            plan_id="p1",
            tasks=[],
            token_entries=entries,
            intervention_count=0,
            intervention_log=[],
            scope_violations=[],
        )
        self.assertEqual(kpi["token_totals"]["cursor"], 100)

    def test_merge_tasks_with_tokens_skips_empty_plan_id(self) -> None:
        tasks = [
            pm.TaskRecord(task_id="t_a", body="plan_id: p1", status="done"),
        ]
        entries = [
            {"plan_id": "", "task_id": "t_foreign", "cursor": {"total_tokens": 50}},
            {"plan_id": "p1", "task_id": "t_b", "cursor": {"total_tokens": 10}},
        ]
        merged = pm._merge_tasks_with_tokens(tasks, entries, "p1")
        ids = {t.task_id for t in merged}
        self.assertIn("t_a", ids)
        self.assertIn("t_b", ids)
        self.assertNotIn("t_foreign", ids)

    def test_build_report_does_not_count_blocked_as_failed_when_done(self) -> None:
        done = pm.TaskRecord(task_id="t_ok", body="plan_id: p1", status="done")
        blocked = pm.TaskRecord(task_id="t_blk", body="plan_id: p1", status="blocked")
        report = pm.build_report(
            plan_id="p1",
            tasks=[done, blocked],
            token_entries=[],
            intervention_count=0,
            intervention_log=[],
            scope_violations=[],
            source_notes=[],
        )
        self.assertIn("**Completed:** 1", report)
        self.assertIn("**Failed / blocked:** 1", report)


if __name__ == "__main__":
    unittest.main()
