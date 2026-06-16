"""Tests for kanban_decompose reliability."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import kanban_decompose as decompose  # noqa: E402
from lib import plan_parse as pp  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "plans"


class TestKanbanDecomposeImports(unittest.TestCase):
    def test_extract_id_uses_re(self) -> None:
        self.assertEqual(decompose.extract_id("Created t_a1b2c3d4 ok"), "t_a1b2c3d4")

    def test_parse_create_task_id_json(self) -> None:
        payload = json.dumps({"id": "t_abcd1234", "title": "x"})
        self.assertEqual(decompose.parse_create_task_id(payload), "t_abcd1234")

    def test_create_card_timeout_scales_with_body(self) -> None:
        small = decompose.create_card_timeout_seconds("x" * 100)
        large = decompose.create_card_timeout_seconds("x" * 20000)
        self.assertGreater(large, small)


class TestDecomposeNineCardRegression(unittest.TestCase):
    def test_parse_nine_impl_cards_with_stress_blocks(self) -> None:
        plan = FIXTURES / "decompose_nine_card_regression.plan.md"
        parsed = pp.parse_plan(str(plan))
        self.assertEqual(parsed["plan_id"], "decompose-nine-regression")
        impl = [c for c in parsed["cards"] if c["type"] == "code-gen"]
        self.assertEqual(len(impl), 9)
        keys = {c["key"] for c in impl}
        self.assertEqual(keys, {f"card{n}" for n in range(1, 10)})

        card3 = next(c for c in impl if c["key"] == "card3")
        self.assertIn("Forbidden:", card3["body"])
        self.assertIsNotNone(card3["agent_body"])

        card7 = next(c for c in impl if c["key"] == "card7")
        self.assertIn("rebase", card7["body"].lower())
        self.assertIn("```agent", card7["body"])

        card5 = next(c for c in impl if c["key"] == "card5")
        card9 = next(c for c in impl if c["key"] == "card9")
        self.assertEqual(card5.get("ordinal_parent"), "card3")
        self.assertEqual(card9.get("ordinal_parent"), "card7")

    def test_verify_links_card5_card9_parents(self) -> None:
        plan = FIXTURES / "decompose_nine_card_regression.plan.md"
        parsed = pp.parse_plan(str(plan))
        impl = [c for c in parsed["cards"] if c["type"] == "code-gen"]
        card_ids = {c["key"]: f"t_{i:08d}" for i, c in enumerate(impl, start=1)}
        card_ids["gate"] = "t_gate0001"
        errors = decompose.verify_links(card_ids, impl)
        self.assertEqual(errors, [])

    def test_create_card_uses_json_flag(self) -> None:
        card = {
            "key": "card1",
            "title": "Test",
            "type": "code-gen",
            "assignee": "worker",
            "plan_id": "p1",
            "body": "plan_id: p1\n```agent\nagent -p test\n```",
        }
        with mock.patch("kanban_decompose.subprocess.run") as run_mock:
            run_mock.return_value = mock.Mock(
                returncode=0,
                stdout='{"id": "t_json0001"}',
                stderr="",
            )
            tid = decompose.create_card(card, dry_run=False, block_after=False)
            self.assertEqual(tid, "t_json0001")
            cmd = run_mock.call_args[0][0]
            self.assertIn("--json", cmd)


if __name__ == "__main__":
    unittest.main()
