"""Read and apply Hermes profile model config from config.yaml (canonical provider ids)."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

RunFn = Callable[..., subprocess.CompletedProcess]


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
            out["provider"] = text
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


def read_model_config_from_yaml(path: Path) -> dict[str, str]:
    """Load provider/default/base_url from a profile config.yaml."""
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return parse_model_section(data.get("model"))


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
        cfg["provider"] = provider_match.group(1)
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


def apply_model_config_to_profile(
    run: RunFn,
    hermes_bin: str,
    profile: str,
    cfg: dict[str, str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 15,
) -> bool:
    """Write model.default/provider/base_url via `hermes config set`."""
    if not cfg.get("default"):
        return False
    kwargs: dict[str, Any] = {"timeout": timeout}
    if env is not None:
        kwargs["env"] = env

    def _set(key: str, value: str) -> None:
        run([hermes_bin, "-p", profile, "config", "set", key, value], **kwargs)

    _set("model.default", cfg["default"])
    if cfg.get("provider"):
        _set("model.provider", cfg["provider"])
    if cfg.get("base_url"):
        _set("model.base_url", cfg["base_url"])
    return True


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
    apply_model_config_to_profile(
        run, hermes_bin, profile, source, env=env, timeout=timeout
    )
    return source
