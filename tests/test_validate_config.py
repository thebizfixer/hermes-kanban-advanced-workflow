"""Tests for validate_config.py ui_stack block handling."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_config as vc  # noqa: E402


class TestValidateConfigUiStack(unittest.TestCase):
    def test_commented_ui_stack_in_example_passes(self) -> None:
        example = ROOT / "kanban-config.example.yaml"
        errors = vc._validate({}, {})
        errors.extend(
            vc._validate_ui_stack_block(
                example.read_text(encoding="utf-8"),
                __import__("json").loads(
                    (ROOT / "schema" / "kanban-config.schema.json").read_text(encoding="utf-8")
                ),
            )
        )
        self.assertEqual(errors, [])

    def test_active_ui_stack_missing_fields_fails(self) -> None:
        text = 'schema_version: "1.0.0"\nui_stack:\n  framework: react-next\n'
        schema = __import__("json").loads(
            (ROOT / "schema" / "kanban-config.schema.json").read_text(encoding="utf-8")
        )
        errors = vc._validate_ui_stack_block(text, schema)
        self.assertTrue(any("page_glob" in e for e in errors))

    def test_active_ui_stack_complete_passes(self) -> None:
        text = """schema_version: "1.0.0"
ui_stack:
  framework: react-next
  page_glob: "frontend/app/**/page.tsx"
"""
        schema = __import__("json").loads(
            (ROOT / "schema" / "kanban-config.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(vc._validate_ui_stack_block(text, schema), [])

    def test_cli_ok_on_example_yaml(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_config.py"), str(ROOT / "kanban-config.example.yaml")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
