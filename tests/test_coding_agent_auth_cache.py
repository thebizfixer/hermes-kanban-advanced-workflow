"""Tests for preflight coding-agent auth cache."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from plugin.coding_agent_auth_cache import (
    is_preflight_cache_fresh,
    preflight_cache_path,
    write_preflight_cache,
)


class TestPreflightAuthCache(unittest.TestCase):
    def test_write_and_read_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_preflight_cache("agent", root, source="test")
            path = preflight_cache_path(root)
            self.assertTrue(path.is_file())
            self.assertTrue(is_preflight_cache_fresh("agent", root))
            self.assertFalse(is_preflight_cache_fresh("claude", root))

    def test_stale_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = preflight_cache_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "timestamp": "2020-01-01T00:00:00+00:00",
                        "coding_agent_binary": "agent",
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(is_preflight_cache_fresh("agent", root))


if __name__ == "__main__":
    unittest.main()
