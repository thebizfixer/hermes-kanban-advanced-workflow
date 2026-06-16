"""Runtime environment and auth prerequisites for coding-agent CLIs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodingAgentAuthProfile:
    display_name: str
    credential_paths: tuple[str, ...] = ()
    env_any: tuple[str, ...] = ()
    login_hint: str = ""
    notes: str = ""


# SSOT: vendor docs + headless/CI patterns (see plugin/data/references/coding-agent-auth.md)
AUTH_PROFILES: dict[str, CodingAgentAuthProfile] = {
    "agent": CodingAgentAuthProfile(
        display_name="Cursor CLI",
        credential_paths=("~/.config/cursor/auth.json",),
        login_hint="agent login",
        notes="OAuth in $HOME/.config/cursor; CURSOR_API_KEY does not authenticate the CLI.",
    ),
    "claude": CodingAgentAuthProfile(
        display_name="Claude Code",
        credential_paths=("~/.claude/.credentials.json",),
        env_any=(
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "CLAUDE_CODE_OAUTH_TOKEN",
        ),
        login_hint="claude login, or export ANTHROPIC_API_KEY, or claude setup-token",
        notes="Non-interactive: ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN (-p uses API key when set).",
    ),
    "codex": CodingAgentAuthProfile(
        display_name="OpenAI Codex",
        credential_paths=("~/.codex/auth.json",),
        env_any=("CODEX_API_KEY", "OPENAI_API_KEY"),
        login_hint="codex login --api-key $OPENAI_API_KEY, or export CODEX_API_KEY",
        notes="codex exec: CODEX_API_KEY for CI; ChatGPT OAuth uses ~/.codex/auth.json.",
    ),
    "grok": CodingAgentAuthProfile(
        display_name="grok-cli",
        env_any=("GROK_API_KEY",),
        login_hint="export GROK_API_KEY",
        notes="API key only for headless use.",
    ),
    "gemini": CodingAgentAuthProfile(
        display_name="Gemini CLI",
        env_any=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        login_hint="gemini auth login, or export GEMINI_API_KEY",
        notes="Headless uses cached Google login or API key.",
    ),
    "aider": CodingAgentAuthProfile(
        display_name="Aider",
        env_any=(
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
            "GEMINI_API_KEY",
        ),
        login_hint="configure provider API keys in .env or aider config",
        notes="Provider-specific; smoke test is authoritative when keys are in config files.",
    ),
}


def resolve_runtime_home(env: dict[str, str] | None = None) -> str:
    """Resolve HOME for credential paths (gateway/systemd may omit it)."""
    env = env or {}
    for key in ("HOME", "USERPROFILE"):
        value = (env.get(key) or "").strip()
        if value:
            return value
    try:
        return str(Path.home())
    except Exception:
        return ""


def ensure_coding_agent_runtime_env(
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return a copy of *env* with HOME/USERPROFILE set when resolvable."""
    merged = dict(os.environ if env is None else env)
    home = resolve_runtime_home(merged)
    if home:
        merged.setdefault("HOME", home)
        if os.name == "nt":
            merged.setdefault("USERPROFILE", home)
    return merged


def dispatch_runtime_env_updates(
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Keys to persist in project .env so gateway workers inherit HOME."""
    home = resolve_runtime_home(env or os.environ)
    if not home:
        return {}
    return {"HOME": home}


def _credential_file_exists(path: str, env: dict[str, str]) -> bool:
    home = env.get("HOME") or env.get("USERPROFILE") or ""
    expanded = Path(os.path.expanduser(path))
    if path.startswith("~/") and home:
        expanded = Path(home) / path[2:]
    return expanded.is_file()


def audit_coding_agent_prerequisites(
    binary: str,
    env: dict[str, str] | None = None,
) -> list[str]:
    """Fast-fail checks before smoke (does not replace execution smoke)."""
    runtime = ensure_coding_agent_runtime_env(env)
    issues: list[str] = []

    if not resolve_runtime_home(runtime):
        issues.append(
            "HOME is unset and could not be resolved — coding CLIs store OAuth "
            "under $HOME (gateway systemd units with SetLoginEnvironment=no "
            "must set Environment=HOME=... or persist HOME in project .env)"
        )

    profile = AUTH_PROFILES.get(binary)
    if not profile:
        return issues

    has_env = any((runtime.get(key) or "").strip() for key in profile.env_any)
    has_file = any(
        _credential_file_exists(path, runtime) for path in profile.credential_paths
    )

    if profile.env_any and not has_env and not has_file:
        env_list = ", ".join(profile.env_any)
        hint = profile.login_hint or "see vendor auth docs"
        issues.append(
            f"{profile.display_name}: no credential file and none of ({env_list}) "
            f"set — {hint}"
        )
    elif profile.credential_paths and not profile.env_any and not has_file:
        hint = profile.login_hint or "see vendor auth docs"
        issues.append(
            f"{profile.display_name}: credential file missing "
            f"({profile.credential_paths[0]}) — {hint}"
        )

    return issues


def is_home_unbound_error(stdout: str = "", stderr: str = "") -> bool:
    combined = f"{stdout}\n{stderr}"
    lower = combined.lower()
    return "home: unbound variable" in lower or (
        "unbound variable" in lower and "home" in lower
    )


def describe_prerequisite_issues(binary: str, issues: list[str]) -> str:
    if not issues:
        return ""
    joined = "; ".join(issues)
    profile = AUTH_PROFILES.get(binary)
    if profile and profile.notes:
        return f"{joined}. {profile.notes}"
    return joined
