"""Tests for dashboard profile reasoning payload validation."""

from __future__ import annotations

import unittest

from plugin.hermes_model_config import (
    REASONING_EFFORT_LEVELS,
    parse_profile_update_payload,
)


class TestDashboardProfileReasoning(unittest.TestCase):
    def test_empty_body_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_profile_update_payload({}, existing_model={"default": "gpt-5"})

    def test_invalid_reasoning_effort_lists_allowed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid reasoning_effort"):
            parse_profile_update_payload(
                {"reasoning_effort": "turbo"},
                existing_model={"default": "gpt-5", "provider": "openrouter"},
            )

    def test_model_and_reasoning_together(self) -> None:
        payload = parse_profile_update_payload(
            {
                "provider": "openrouter",
                "model": "anthropic/claude-sonnet-4.6",
                "reasoning_effort": "xhigh",
            },
            existing_model={},
        )
        self.assertEqual(payload["model"], "anthropic/claude-sonnet-4.6")
        self.assertEqual(payload["provider"], "openrouter")
        self.assertEqual(payload["reasoning_effort"], "xhigh")

    def test_all_levels_accepted(self) -> None:
        for level in REASONING_EFFORT_LEVELS:
            payload = parse_profile_update_payload(
                {"reasoning_effort": level},
                existing_model={"default": "gpt-5", "provider": "openrouter"},
            )
            self.assertEqual(payload["reasoning_effort"], level)


if __name__ == "__main__":
    unittest.main()
