"""Unit tests for Hermes profile model config helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugin.hermes_model_config import (
    config_path_from_show,
    parse_model_section,
    profile_has_model_config,
    read_model_config_from_config_show,
    read_model_config_from_yaml,
)


class TestHermesModelConfig(unittest.TestCase):
    def test_parse_model_section_dict(self) -> None:
        cfg = parse_model_section(
            {
                "provider": "openrouter",
                "default": "anthropic/claude-sonnet-4.6",
                "base_url": "",
            }
        )
        self.assertEqual(cfg["provider"], "openrouter")
        self.assertEqual(cfg["default"], "anthropic/claude-sonnet-4.6")
        self.assertNotIn("base_url", cfg)

    def test_parse_model_section_custom_provider(self) -> None:
        cfg = parse_model_section(
            {
                "provider": "custom:fireworks-endpoint",
                "default": "accounts/fireworks/models/llama-v3p1-70b-instruct",
            }
        )
        self.assertEqual(cfg["provider"], "custom:fireworks-endpoint")

    def test_read_model_config_from_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                "model:\n"
                "  provider: nous\n"
                "  default: anthropic/claude-opus-4.7\n",
                encoding="utf-8",
            )
            cfg = read_model_config_from_yaml(path)
            self.assertEqual(cfg["provider"], "nous")
            self.assertEqual(cfg["default"], "anthropic/claude-opus-4.7")

    def test_read_model_config_from_config_show_prefers_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                "model:\n"
                "  provider: openrouter\n"
                "  default: google/gemini-2.5-flash\n",
                encoding="utf-8",
            )
            stdout = (
                f"Config: {path}\n"
                "Model: {'default': 'Display Name Model', 'provider': 'OpenRouter'}\n"
            )
            cfg = read_model_config_from_config_show(stdout)
            self.assertEqual(cfg["provider"], "openrouter")
            self.assertEqual(cfg["default"], "google/gemini-2.5-flash")

    def test_config_path_from_show(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix="config.yaml", delete=False) as fh:
            fh.write("model: {}\n")
            path = Path(fh.name)
        try:
            stdout = f"Config: {path}\n"
            self.assertEqual(config_path_from_show(stdout), path)
        finally:
            path.unlink(missing_ok=True)

    def test_profile_has_model_config(self) -> None:
        self.assertTrue(profile_has_model_config({"default": "gpt-5.2"}))
        self.assertFalse(profile_has_model_config({"provider": "openrouter"}))


if __name__ == "__main__":
    unittest.main()
