"""kanban-advanced plugin — root proxy for Hermes plugin loader."""
import sys
from pathlib import Path

# Dual-path compatibility: ensure 'plugin' resolves both under the
# hermes_plugins namespace (v0.17.0+) and when imported from a dev checkout.
_plugin_dir = str(Path(__file__).resolve().parent)
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from .plugin import register

__all__ = ["register"]
