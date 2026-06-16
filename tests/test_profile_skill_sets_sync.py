"""provision.sh profile skill rosters must match config_overlay SSOT."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from plugin.config_overlay import PROFILE_SKILL_SETS_BY_ROLE

ROOT = Path(__file__).resolve().parents[1]
PROVISION = ROOT / "scripts" / "provision.sh"


def _parse_provision_skill_set(var_name: str) -> frozenset[str]:
    text = PROVISION.read_text(encoding="utf-8")
    pattern = rf'PROFILE_SKILL_SETS\["\${var_name}"\]="([^"]+)"'
    match = re.search(pattern, text)
    if not match:
        raise AssertionError(f"could not parse PROFILE_SKILL_SETS for ${var_name}")
    return frozenset(match.group(1).split())


class TestProfileSkillSetsSync(unittest.TestCase):
    def test_provision_worker_skills_match_overlay(self) -> None:
        self.assertEqual(
            _parse_provision_skill_set("WORKER_PROFILE_NAME"),
            PROFILE_SKILL_SETS_BY_ROLE["worker"],
        )

    def test_provision_orchestrator_skills_match_overlay(self) -> None:
        self.assertEqual(
            _parse_provision_skill_set("ORCH_PROFILE_NAME"),
            PROFILE_SKILL_SETS_BY_ROLE["orchestrator"],
        )


if __name__ == "__main__":
    unittest.main()
