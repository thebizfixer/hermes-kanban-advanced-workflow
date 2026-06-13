"""Unit tests for Hermes profile model config helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugin.hermes_model_config import (
    DEFAULT_REASONING_EFFORT,
    apply_reasoning_effort_to_profile,
    config_path_from_show,
    normalize_provider_id,
    normalize_reasoning_effort,
    parse_model_section,
    parse_profile_update_payload,
    profile_has_model_config,
    read_model_config_from_config_show,
    read_model_config_from_yaml,
    read_reasoning_effort_from_yaml,
    recommended_reasoning_effort_for_profile,
    seed_default_reasoning_effort_for_profile,
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

    def test_normalize_provider_id_nous_portal(self) -> None:
        self.assertEqual(normalize_provider_id("Nous Portal"), "nous")
        self.assertEqual(normalize_provider_id("nous"), "nous")

    def test_parse_model_section_normalizes_display_provider(self) -> None:
        cfg = parse_model_section(
            {"provider": "Nous Portal", "default": "stepfun/step-3.7-flash:free"}
        )
        self.assertEqual(cfg["provider"], "nous")

    def test_normalize_reasoning_effort(self) -> None:
        self.assertEqual(normalize_reasoning_effort("HIGH"), "high")
        self.assertIsNone(normalize_reasoning_effort("turbo"))

    def test_read_reasoning_effort_from_yaml_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                "agent:\n  reasoning_effort: high\n",
                encoding="utf-8",
            )
            info = read_reasoning_effort_from_yaml(path)
            self.assertEqual(info["reasoning_effort"], "high")
            self.assertTrue(info["reasoning_effort_configured"])
            self.assertEqual(info["reasoning_effort_source"], "agent")

    def test_read_reasoning_effort_from_yaml_legacy_thinking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                "model:\n  thinking: low\n",
                encoding="utf-8",
            )
            info = read_reasoning_effort_from_yaml(path)
            self.assertEqual(info["reasoning_effort"], "low")
            self.assertEqual(info["reasoning_effort_source"], "legacy_model_thinking")

    def test_read_reasoning_effort_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("model:\n  default: gpt-5\n", encoding="utf-8")
            info = read_reasoning_effort_from_yaml(path)
            self.assertEqual(info["reasoning_effort"], DEFAULT_REASONING_EFFORT)
            self.assertFalse(info["reasoning_effort_configured"])

    def test_recommended_reasoning_effort_for_profile(self) -> None:
        self.assertEqual(
            recommended_reasoning_effort_for_profile(
                "kanban-advanced-orchestrator",
                orchestrator_profile="kanban-advanced-orchestrator",
                worker_profile="kanban-advanced-worker",
            ),
            "high",
        )
        self.assertEqual(
            recommended_reasoning_effort_for_profile(
                "kanban-advanced-worker",
                orchestrator_profile="kanban-advanced-orchestrator",
                worker_profile="kanban-advanced-worker",
            ),
            "medium",
        )

    def test_parse_profile_update_payload_reasoning_only(self) -> None:
        payload = parse_profile_update_payload(
            {"reasoning_effort": "high"},
            existing_model={"default": "gpt-5", "provider": "openrouter"},
        )
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertNotIn("model", payload)

    def test_parse_profile_update_payload_requires_provider_for_new_model(self) -> None:
        with self.assertRaises(ValueError):
            parse_profile_update_payload({"model": "gpt-5"}, existing_model={})

    def test_apply_reasoning_effort_to_profile(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)

            class Result:
                returncode = 0
                stdout = ""
                stderr = ""

            return Result()

        ok, err = apply_reasoning_effort_to_profile(
            fake_run, "hermes", "kanban-advanced-worker", "medium"
        )
        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(
            calls[0],
            [
                "hermes",
                "-p",
                "kanban-advanced-worker",
                "config",
                "set",
                "agent.reasoning_effort",
                "medium",
            ],
        )

    def test_seed_default_reasoning_effort_for_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("model:\n  default: gpt-5\n", encoding="utf-8")
            show_stdout = f"Config: {path}\n"
            calls: list[list[str]] = []

            def fake_run(cmd, **kwargs):
                calls.append(cmd)

                class Result:
                    returncode = 0
                    stdout = show_stdout
                    stderr = ""

                return Result()

            seeded = seed_default_reasoning_effort_for_profile(
                fake_run,
                "hermes",
                "kanban-advanced-orchestrator",
                orchestrator_profile="kanban-advanced-orchestrator",
                worker_profile="kanban-advanced-worker",
            )
            self.assertEqual(seeded, "high")
            self.assertTrue(
                any("agent.reasoning_effort" in c for c in calls),
            )


if __name__ == "__main__":
    unittest.main()
