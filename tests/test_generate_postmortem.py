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


if __name__ == "__main__":
    unittest.main()
