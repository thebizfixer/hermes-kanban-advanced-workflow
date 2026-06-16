"""Resolve Hermes cron --deliver for lifecycle/completion notifications (platform-neutral)."""

from __future__ import annotations

import os
from pathlib import Path

_PLATFORM_HOME_ENV = {
    "telegram": "TELEGRAM_HOME_CHANNEL",
    "discord": "DISCORD_HOME_CHANNEL",
    "slack": "SLACK_HOME_CHANNEL",
    "signal": "SIGNAL_HOME_CHANNEL",
    "whatsapp": "WHATSAPP_HOME_CHANNEL",
}
_VALID_DELIVER = frozenset({*_PLATFORM_HOME_ENV.keys(), "all", "local"})


def _parse_notify_deliver_from_overlay(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("notify_deliver:"):
            val = stripped.split(":", 1)[1].strip().strip('"').strip("'").lower()
            return val if val in _VALID_DELIVER else None
    return None


def _parse_cron_default_deliver(hermes_home: Path) -> str | None:
    config_path = hermes_home / "config.yaml"
    if not config_path.is_file():
        return None
    in_cron = False
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("cron:"):
            in_cron = True
            continue
        if in_cron and not line[:1].isspace() and ":" in stripped:
            break
        if in_cron and stripped.startswith("default_deliver:"):
            val = stripped.split(":", 1)[1].strip().strip('"').strip("'").lower()
            return val if val in _VALID_DELIVER else None
    return None


def _configured_home_platforms() -> list[str]:
    configured: list[str] = []
    for slug, env_name in _PLATFORM_HOME_ENV.items():
        if os.environ.get(env_name, "").strip():
            configured.append(slug)
    return configured


def resolve_notify_deliver(
    project_root: Path | None = None,
    *,
    hermes_home: str | None = None,
) -> str:
    """Return deliver slug for lifecycle/completion crons.

    Precedence: overlay notify_deliver → cron.default_deliver → single home → all.
    """
    if project_root is not None:
        overlay = project_root / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
        if overlay.is_file():
            explicit = _parse_notify_deliver_from_overlay(
                overlay.read_text(encoding="utf-8")
            )
            if explicit and explicit != "local":
                return explicit

    home = Path(hermes_home or os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    default_deliver = _parse_cron_default_deliver(home)
    if default_deliver and default_deliver != "local":
        return default_deliver

    platforms = _configured_home_platforms()
    if len(platforms) == 1:
        return platforms[0]
    return "all"
