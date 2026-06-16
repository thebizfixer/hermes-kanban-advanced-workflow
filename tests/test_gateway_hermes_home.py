"""Tests for gateway HERMES_HOME resolution."""

from __future__ import annotations

import unittest

from plugin.hermes_gateway_home import is_profile_scoped_hermes_home, resolve_gateway_hermes_home


class TestGatewayHermesHome(unittest.TestCase):
    def test_profile_scoped_resolves_to_main(self) -> None:
        home = "/home/user/.hermes/profiles/kanban-advanced-orchestrator"
        self.assertEqual(resolve_gateway_hermes_home(home), "/home/user/.hermes")
        self.assertTrue(is_profile_scoped_hermes_home(home))

    def test_main_home_unchanged(self) -> None:
        home = "/home/user/.hermes"
        self.assertEqual(resolve_gateway_hermes_home(home), "/home/user/.hermes")
        self.assertFalse(is_profile_scoped_hermes_home(home))

    def test_windows_path_normalization(self) -> None:
        home = r"C:\Users\me\.hermes\profiles\orch"
        self.assertEqual(resolve_gateway_hermes_home(home), "C:/Users/me/.hermes")


if __name__ == "__main__":
    unittest.main()
