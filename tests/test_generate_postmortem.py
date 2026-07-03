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

    # ── Step 2: Archived board detection ──────────────────────────────

    def test_data_notes_mention_archive_when_board_archived(self) -> None:
        """source_notes includes archive reference when board found in _archived."""
        with tempfile.TemporaryDirectory() as td:
            hermes_home = Path(td)
            archive_dir = hermes_home / "kanban" / "boards" / "_archived"
            archive_slug = archive_dir / "procurement-expansion-20260701-073945"
            archive_slug.mkdir(parents=True)
            (archive_slug / "kanban.db").write_text("")

            with patch.object(pm, "_hermes_home", return_value=hermes_home):
                slug = pm._find_archived_board("procurement-expansion")
                self.assertIsNotNone(slug)
                self.assertIn("procurement-expansion", slug)

    def test_fallback_to_plan_memory_when_zero_tasks(self) -> None:
        """_find_archived_board returns None when _archived dir doesn't exist."""
        with tempfile.TemporaryDirectory() as td:
            hermes_home = Path(td)
            with patch.object(pm, "_hermes_home", return_value=hermes_home):
                slug = pm._find_archived_board("no-such-plan")
                self.assertIsNone(slug)

    def test_stderr_warns_when_board_archived(self) -> None:
        """_find_archived_board handles empty _archived dir gracefully."""
        with tempfile.TemporaryDirectory() as td:
            hermes_home = Path(td)
            (hermes_home / "kanban" / "boards" / "_archived").mkdir(parents=True)
            with patch.object(pm, "_hermes_home", return_value=hermes_home):
                slug = pm._find_archived_board("nonexistent")
                self.assertIsNone(slug)

    # ── Step 4: Intervention JSONL SSOT ───────────────────────────────

    def test_intervention_count_from_plan_scoped_jsonl(self) -> None:
        """JSONL count wins over counter file when plan-scoped path exists."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plan_logdir = root / ".hermes" / "kanban" / "logs" / "test-plan"
            plan_logdir.mkdir(parents=True)
            jsonl = plan_logdir / "interventions.jsonl"
            jsonl.write_text('{"event":"test"}\n{"event":"test"}\n{"event":"test"}\n')

            flat_counter = root / ".hermes" / "kanban" / "logs" / "interventions.count"
            flat_counter.parent.mkdir(parents=True, exist_ok=True)
            flat_counter.write_text("1")

            with patch.object(pm, "_project_root", return_value=root), \
                 patch.object(pm, "_interventions_count_path", return_value=flat_counter):
                notes: list[str] = []
                count = pm._resolve_intervention_count("test-plan", notes)
                self.assertEqual(count, 3)
                self.assertTrue(any("disagrees" in n for n in notes))

    def test_intervention_count_falls_back_to_flat(self) -> None:
        """Falls back to flat JSONL when no plan-scoped path exists."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            flat_jsonl = root / ".hermes" / "kanban" / "logs" / "interventions.jsonl"
            flat_jsonl.parent.mkdir(parents=True, exist_ok=True)
            flat_jsonl.write_text('{"event":"a"}\n{"event":"b"}\n')

            flat_counter = root / ".hermes" / "kanban" / "logs" / "interventions.count"
            flat_counter.write_text("2")

            with patch.object(pm, "_project_root", return_value=root), \
                 patch.object(pm, "_interventions_count_path", return_value=flat_counter):
                notes: list[str] = []
                count = pm._resolve_intervention_count("no-plan-scope", notes)
                self.assertEqual(count, 2)
                self.assertEqual(len([n for n in notes if "disagrees" in n]), 0)

    def test_intervention_log_reads_plan_scoped(self) -> None:
        """_plan_interventions_log_path returns plan-scoped path when it exists."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plan_logdir = root / ".hermes" / "kanban" / "logs" / "test-plan"
            plan_logdir.mkdir(parents=True)
            plan_jsonl = plan_logdir / "interventions.jsonl"
            plan_jsonl.write_text('{"event":"scoped"}\n')

            flat_jsonl = root / ".hermes" / "kanban" / "logs" / "interventions.jsonl"
            flat_jsonl.parent.mkdir(parents=True, exist_ok=True)
            flat_jsonl.write_text('{"event":"flat"}\n')

            with patch.object(pm, "_project_root", return_value=root), \
                 patch.object(pm, "_interventions_log_path", return_value=flat_jsonl):
                result = pm._plan_interventions_log_path("test-plan")
                self.assertEqual(result, plan_jsonl)
                # Verify it returned the plan-scoped one, not the flat one
                self.assertIn("test-plan", str(result))


if __name__ == "__main__":
    unittest.main()
