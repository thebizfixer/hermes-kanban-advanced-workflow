"""ASCII-safe console output for gate scripts (Windows cp1252, Git Bash, POSIX)."""

from __future__ import annotations

import os
import sys


def supports_color() -> bool:
    """True when ANSI color is likely to render (TTY + terminal hint)."""
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        return bool(
            os.environ.get("WT_SESSION")
            or os.environ.get("MSYSTEM")
            or os.environ.get("ANSICON")
            or os.environ.get("TERM")
        )
    term = os.environ.get("TERM", "")
    return bool(term) and term != "dumb"


def _color(code: str, text: str) -> str:
    if supports_color():
        return f"\033[{code}m{text}\033[0m"
    return text


def pass_line(msg: str) -> str:
    return _color("32", f"  PASS: {msg}")


def warn_line(msg: str) -> str:
    return _color("33", f"  WARN: {msg}")


def fail_line(msg: str) -> str:
    return _color("31", f"  FAIL: {msg}")


def status_line(label: str, msg: str) -> str:
    """Summary line: BLOCKED / PASS / WARN without Unicode symbols."""
    return _color("31" if label == "BLOCKED" else "33" if "WARN" in label else "32", f"{label}: {msg}")
