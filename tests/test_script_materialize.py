"""Tests for HERMES_HOME script materialization."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugin.script_materialize import materialize_hermes_scripts


class TestScriptMaterialize(unittest.TestCase):
    def test_materialize_hermes_scripts_copies_lib(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts_src = root / "src" / "scripts"
            lib_src = scripts_src / "lib"
            lib_src.mkdir(parents=True)
            (scripts_src / "coding_agent_invoke.sh").write_text("#!/bin/bash\n", encoding="utf-8")
            (lib_src / "coding_agent_env.sh").write_text(
                "ensure_coding_agent_home() { :; }\n", encoding="utf-8"
            )
            (lib_src / "resolve_notify_deliver.sh").write_text("#!/bin/bash\n", encoding="utf-8")
            (lib_src / "hermes_notify_deliver.py").write_text(
                "def resolve_notify_deliver():\n    return 'all'\n", encoding="utf-8"
            )

            scripts_dst = root / "dst" / "scripts"
            lines = materialize_hermes_scripts(scripts_src, scripts_dst)

            self.assertTrue((scripts_dst / "coding_agent_invoke.sh").exists())
            self.assertTrue((scripts_dst / "lib" / "coding_agent_env.sh").exists())
            self.assertTrue((scripts_dst / "lib" / "resolve_notify_deliver.sh").exists())
            self.assertTrue((scripts_dst / "lib" / "hermes_notify_deliver.py").exists())
            self.assertTrue(any("lib/coding_agent_env.sh" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
