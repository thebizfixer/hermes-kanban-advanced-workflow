"""Resolve Hermes cron --deliver for lifecycle/completion notifications (platform-neutral)."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from hermes_notify_deliver import resolve_notify_deliver  # noqa: E402

__all__ = ["resolve_notify_deliver"]
