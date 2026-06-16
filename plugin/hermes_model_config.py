"""Read and apply Hermes profile model config from config.yaml (canonical provider ids)."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

RunFn = Callable[..., subprocess.CompletedProcess]

REASONING_EFFORT_LEVELS: tuple[str, ...] = (
    "none",
    "low",
    "minimal",
    "medium",
    "high",
    "xhigh",
)

DEFAULT_REASONING_EFFORT = "medium"

# Display names from model pickers / `hermes config show` that are not valid provider IDs.
_PROVIDER_DISPLAY_ALIASES: dict[str, str] = {
    "nous portal": "nous",
    "nous research": "nous",
    "open router": "openrouter",
    "openrouter": "openrouter",
    "anthropic": "anthropic",
    "openai": "openai",
    "deepseek": "deepseek",
    "google": "google",
    "groq": "groq",
    "fireworks": "fireworks",
    "together": "together",
    "mistral": "mistral",
    "xai": "xai",
    "stepfun": "stepfun",
}


def normalize_provider_id(value: str) -> str:
    """Map provider display names to canonical Hermes provider IDs."""
    text = (value or "").strip()
    if not text:
        return text
    alias = _PROVIDER_DISPLAY_ALIASES.get(text.lower())
    if alias:
        return alias
    if " " in text:
        slug = text.lower().replace(" portal", "").strip().replace(" ", "")
        if slug in _PROVIDER_DISPLAY_ALIASES.values():
            return slug
        compact = text.lower().replace(" ", "")
        if compact in _PROVIDER_DISPLAY_ALIASES.values():
            return compact
    return text


def parse_model_section(model: Any) -> dict[str, str]:
    """Normalize the model block from a profile config.yaml."""
    if model is None:
        return {}
    if isinstance(model, str):
        value = model.strip()
        return {"default": value} if value else {}
    if not isinstance(model, dict):
        return {}
    out: dict[str, str] = {}
    provider = model.get("provider")
    if provider is not None:
        text = str(provider).strip()
        if text and text != "None":
            out["provider"] = normalize_provider_id(text)
    default = model.get("default")
    if default is None:
        default = model.get("model")
    if default is not None:
        text = str(default).strip()
        if text and text != "None":
            out["default"] = text
    base_url = model.get("base_url")
    if base_url is not None:
        text = str(base_url).strip()
        if text:
            out["base_url"] = text
    return out


def _load_config_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_model_config_from_yaml(path: Path) -> dict[str, str]:
    """Load provider/default/base_url from a profile config.yaml."""
    return parse_model_section(_load_config_yaml(path).get("model"))


def normalize_reasoning_effort(value: str | None) -> str | None:
    """Return a canonical reasoning level or None when invalid."""
    text = (value or "").strip().lower()
    if not text:
        return None
    if text in REASONING_EFFORT_LEVELS:
        return text
    return None


def read_reasoning_effort_from_yaml(path: Path) -> dict[str, Any]:
    """Read reasoning effort from profile config.yaml (agent.reasoning_effort preferred)."""
    data = _load_config_yaml(path)
    agent = data.get("agent")
    if isinstance(agent, dict) and agent.get("reasoning_effort") is not None:
        level = normalize_reasoning_effort(str(agent.get("reasoning_effort")))
        if level:
            return {
                "reasoning_effort": level,
                "reasoning_effort_configured": True,
                "reasoning_effort_source": "agent",
            }

    model = data.get("model")
    if isinstance(model, dict) and model.get("thinking") is not None:
        level = normalize_reasoning_effort(str(model.get("thinking")))
        if level:
            return {
                "reasoning_effort": level,
                "reasoning_effort_configured": True,
                "reasoning_effort_source": "legacy_model_thinking",
            }

    return {
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
        "reasoning_effort_configured": False,
        "reasoning_effort_source": "default",
    }


def read_reasoning_effort_from_config_show(stdout: str) -> dict[str, Any]:
    """Prefer on-disk config.yaml; fall back to Hermes default."""
    path = config_path_from_show(stdout)
    if path is not None:
        return read_reasoning_effort_from_yaml(path)
    return {
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
        "reasoning_effort_configured": False,
        "reasoning_effort_source": "default",
    }


def recommended_reasoning_effort_for_profile(
    profile: str,
    *,
    orchestrator_profile: str,
    worker_profile: str,
) -> str:
    if profile == orchestrator_profile:
        return "high"
    if profile == worker_profile:
        return "medium"
    return DEFAULT_REASONING_EFFORT


def parse_profile_update_payload(
    body: dict[str, Any] | None,
    *,
    existing_model: dict[str, str],
) -> dict[str, Any]:
    """Normalize a dashboard profile update body. Raises ValueError on invalid input."""
    if not body or not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")

    model_raw = body.get("model")
    provider_raw = body.get("provider")
    reasoning_raw = body.get("reasoning_effort")

    has_model = model_raw is not None and str(model_raw).strip()
    has_reasoning = reasoning_raw is not None and str(reasoning_raw).strip()

    if not has_model and not has_reasoning:
        raise ValueError("At least one of model or reasoning_effort is required")

    out: dict[str, Any] = {}
    if has_model:
        out["model"] = str(model_raw).strip()
        if provider_raw is not None and str(provider_raw).strip():
            out["provider"] = normalize_provider_id(str(provider_raw))
        elif existing_model.get("provider"):
            out["provider"] = existing_model["provider"]
        else:
            raise ValueError(
                "provider is required when setting model on a profile without an existing provider"
            )
    if has_reasoning:
        level = normalize_reasoning_effort(str(reasoning_raw))
        if not level:
            allowed = ", ".join(REASONING_EFFORT_LEVELS)
            raise ValueError(f"Invalid reasoning_effort; allowed: {allowed}")
        out["reasoning_effort"] = level
    return out


def config_path_from_show(stdout: str) -> Path | None:
    """Extract config.yaml path from `hermes config show` output."""
    match = re.search(r"Config:\s*(.+)", stdout)
    if not match:
        return None
    candidate = Path(match.group(1).strip()).expanduser()
    return candidate if candidate.is_file() else None


def read_model_config_from_config_show(stdout: str) -> dict[str, str]:
    """Prefer config.yaml on disk; fall back to parsing `config show` text."""
    path = config_path_from_show(stdout)
    if path is not None:
        cfg = read_model_config_from_yaml(path)
        if profile_has_model_config(cfg) or cfg.get("provider"):
            return cfg
    cfg: dict[str, str] = {}
    model_match = re.search(r"Model:\s*\{[^}]*'default':\s*'([^']+)'", stdout)
    if model_match and model_match.group(1) and model_match.group(1) != "None":
        cfg["default"] = model_match.group(1)
    provider_match = re.search(r"'provider':\s*'([^']+)'", stdout)
    if provider_match:
        cfg["provider"] = normalize_provider_id(provider_match.group(1))
    base_url_match = re.search(r"'base_url':\s*'([^']*)'", stdout)
    if base_url_match and base_url_match.group(1):
        cfg["base_url"] = base_url_match.group(1)
    return cfg


def read_active_model_config(
    run: RunFn,
    hermes_bin: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict[str, str]:
    """Read model config from the active Hermes profile's config.yaml."""
    try:
        kwargs: dict[str, Any] = {"timeout": timeout}
        if env is not None:
            kwargs["env"] = env
        result = run([hermes_bin, "config", "show"], **kwargs)
        if result.returncode != 0:
            return {}
        path = config_path_from_show(result.stdout)
        if path is None:
            return {}
        return read_model_config_from_yaml(path)
    except Exception:
        return {}


def profile_has_model_config(cfg: dict[str, str]) -> bool:
    return bool(cfg.get("default"))


def _hermes_profile_config_set(
    run: RunFn,
    hermes_bin: str,
    profile: str,
    key: str,
    value: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 15,
) -> tuple[bool, str]:
    kwargs: dict[str, Any] = {"timeout": timeout}
    if env is not None:
        kwargs["env"] = env
    result = run(
        [hermes_bin, "-p", profile, "config", "set", key, value],
        **kwargs,
    )
    if result.returncode != 0:
        text = (result.stderr or result.stdout or "").strip()
        return False, text or f"hermes config set {key} failed"
    return True, ""


def apply_model_config_to_profile(
    run: RunFn,
    hermes_bin: str,
    profile: str,
    cfg: dict[str, str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 15,
) -> tuple[bool, str]:
    """Write model.default/provider/base_url via `hermes config set`."""
    if not cfg.get("default"):
        return False, "model.default is required"
    kwargs: dict[str, Any] = {"env": env, "timeout": timeout}
    for key, value in (
        ("model.default", cfg["default"]),
        *(
            [("model.provider", normalize_provider_id(cfg["provider"]))]
            if cfg.get("provider")
            else []
        ),
        *([("model.base_url", cfg["base_url"])] if cfg.get("base_url") else []),
    ):
        ok, err = _hermes_profile_config_set(
            run, hermes_bin, profile, key, value, **kwargs
        )
        if not ok:
            return False, err
    return True, ""


def apply_reasoning_effort_to_profile(
    run: RunFn,
    hermes_bin: str,
    profile: str,
    level: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 15,
) -> tuple[bool, str]:
    """Write agent.reasoning_effort via `hermes -p <profile> config set`."""
    normalized = normalize_reasoning_effort(level)
    if not normalized:
        allowed = ", ".join(REASONING_EFFORT_LEVELS)
        return False, f"Invalid reasoning_effort; allowed: {allowed}"
    return _hermes_profile_config_set(
        run,
        hermes_bin,
        profile,
        "agent.reasoning_effort",
        normalized,
        env=env,
        timeout=timeout,
    )


def seed_default_reasoning_effort_for_profile(
    run: RunFn,
    hermes_bin: str,
    profile: str,
    *,
    orchestrator_profile: str,
    worker_profile: str,
    env: dict[str, str] | None = None,
    timeout: int = 15,
    log: Callable[[str], None] | None = None,
) -> str | None:
    """Seed role-default reasoning when agent.reasoning_effort is absent. Returns level if set."""
    try:
        kwargs: dict[str, Any] = {"timeout": timeout}
        if env is not None:
            kwargs["env"] = env
        result = run([hermes_bin, "-p", profile, "config", "show"], **kwargs)
        if result.returncode != 0:
            return None
        path = config_path_from_show(result.stdout)
        if path is None:
            return None
        info = read_reasoning_effort_from_yaml(path)
        if info.get("reasoning_effort_configured"):
            return None
        level = recommended_reasoning_effort_for_profile(
            profile,
            orchestrator_profile=orchestrator_profile,
            worker_profile=worker_profile,
        )
        ok, err = apply_reasoning_effort_to_profile(
            run,
            hermes_bin,
            profile,
            level,
            env=env,
            timeout=timeout,
        )
        if not ok:
            if log:
                log(f"   !  {profile}: reasoning_effort seed failed — {err}")
            return None
        if log:
            log(f"   OK {profile}: reasoning_effort = {level} (default)")
        return level
    except Exception as exc:
        if log:
            log(f"   !  {profile}: reasoning_effort seed skipped — {exc}")
        return None


def copy_active_model_to_profile(
    run: RunFn,
    hermes_bin: str,
    profile: str,
    *,
    env: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict[str, str]:
    """Copy model settings from the active profile config.yaml to a dispatch profile."""
    source = read_active_model_config(
        run, hermes_bin, env=env, timeout=timeout
    )
    if not profile_has_model_config(source):
        return {}
    ok, _err = apply_model_config_to_profile(
        run, hermes_bin, profile, source, env=env, timeout=timeout
    )
    if not ok:
        return {}
    return source
