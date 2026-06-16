"""Tests for cross_plan_memory.py."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import cross_plan_memory as cpm  # noqa: E402


class TestCrossPlanMemory(unittest.TestCase):
    def test_append_lessons_dedupes_and_writes_global(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lesson = {
                "plan_id": "p1",
                "failure_class": "auth_error",
                "subsystem": "coding_agent",
                "pattern": "oauth race",
            }
            added = cpm.append_lessons(root, [lesson])
            self.assertEqual(added, 1)
            gpath = cpm.global_path(root)
            self.assertTrue(gpath.is_file())
            data = json.loads(gpath.read_text(encoding="utf-8"))
            self.assertEqual(len(data["lessons"]), 1)

            added2 = cpm.append_lessons(root, [lesson])
            self.assertEqual(added2, 0)
            data2 = json.loads(gpath.read_text(encoding="utf-8"))
            self.assertEqual(data2["lessons"][0]["occurrences"], 2)

    def test_lessons_from_kpi_includes_completeness(self) -> None:
        kpi = {
            "plan_id": "p1",
            "auth_escalation_count": 1,
            "thrash_outliers": ["t_abc12345"],
            "subsystem_failures": {"auth_error": 2},
            "completeness": {
                "violations": [
                    {
                        "kind": "completeness_remediation",
                        "caught_by": "orchestrator",
                        "missed": "missing call site",
                    }
                ]
            },
        }
        lessons = cpm.lessons_from_kpi(kpi)
        self.assertGreaterEqual(len(lessons), 3)
        classes = {l["failure_class"] for l in lessons}
        self.assertIn("completeness_remediation", classes)
        self.assertIn("thrash", classes)

    def test_lessons_from_kpi_dict_thrash_outliers(self) -> None:
        kpi = {
            "plan_id": "p1",
            "thrash_outliers": [
                {"task_id": "t_abc12345", "reblock_count": 4, "event_count": 42},
            ],
        }
        lessons = cpm.lessons_from_kpi(kpi)
        thrash = [l for l in lessons if l["failure_class"] == "thrash"]
        self.assertEqual(len(thrash), 1)
        self.assertEqual(thrash[0]["pattern"], "t_abc12345")


if __name__ == "__main__":
    unittest.main()
