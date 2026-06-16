"""Resolve gateway-visible HERMES_HOME (main store vs profile-scoped)."""

from __future__ import annotations


def resolve_gateway_hermes_home(hermes_home: str) -> str:
    """Return main Hermes store when session is profile-scoped."""
    normalized = hermes_home.replace("\\", "/").rstrip("/")
    marker = "/profiles/"
    if marker in normalized:
        return normalized.split(marker, 1)[0]
    return normalized


def is_profile_scoped_hermes_home(hermes_home: str) -> bool:
    return "/profiles/" in hermes_home.replace("\\", "/")
