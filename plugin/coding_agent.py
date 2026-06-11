"""Coding-agent CLI adapters — model listing, smoke tests, status."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

CODING_AGENT_MODEL_AUTO = "auto"
SMOKE_PROMPT = "say ok"
SMOKE_TIMEOUT_SECONDS = 90


@dataclass(frozen=True)
class CodingAgentAdapter:
    binary: str
    display_name: str
    invocation: str  # print | exec | message | grok | gemini
    model_flag: str | None
    list_models_argv: tuple[str, ...] | None
    default_models: tuple[tuple[str, str], ...]
    extra_smoke_argv: tuple[str, ...] = ()
    exec_argv: tuple[str, ...] = ()  # e.g. ("exec",) for codex
    dispatch_argv: tuple[str, ...] = ()  # extra flags for dispatch (e.g. codex sandbox)


ADAPTERS: dict[str, CodingAgentAdapter] = {
    "agent": CodingAgentAdapter(
        binary="agent",
        display_name="Cursor CLI",
        invocation="print",
        model_flag="--model",
        list_models_argv=("--list-models",),
        default_models=((CODING_AGENT_MODEL_AUTO, "Auto (CLI default)"),),
        extra_smoke_argv=("--output-format", "json", "--trust"),
    ),
    "claude": CodingAgentAdapter(
        binary="claude",
        display_name="Claude Code",
        invocation="print",
        model_flag="--model",
        list_models_argv=None,
        default_models=(
            (CODING_AGENT_MODEL_AUTO, "Default (account settings)"),
            ("sonnet", "Sonnet (latest alias)"),
            ("opus", "Opus (latest alias)"),
            ("haiku", "Haiku (latest alias)"),
        ),
        extra_smoke_argv=(
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
        ),
    ),
    "codex": CodingAgentAdapter(
        binary="codex",
        display_name="OpenAI Codex",
        invocation="exec",
        model_flag="--model",
        list_models_argv=None,
        default_models=(
            (CODING_AGENT_MODEL_AUTO, "Default (config / account)"),
            ("o4-mini", "o4-mini"),
            ("gpt-4.1", "gpt-4.1"),
        ),
        exec_argv=("exec",),
        extra_smoke_argv=("--json", "-a", "never"),
        dispatch_argv=("--sandbox", "workspace-write"),
    ),
    "grok": CodingAgentAdapter(
        binary="grok",
        display_name="grok-cli",
        invocation="grok",
        model_flag="--model",
        list_models_argv=None,
        default_models=(
            (CODING_AGENT_MODEL_AUTO, "Default (CLI auto)"),
        ),
        extra_smoke_argv=("--format", "json"),
    ),
    "aider": CodingAgentAdapter(
        binary="aider",
        display_name="Aider",
        invocation="message",
        model_flag="--model",
        list_models_argv=None,
        default_models=(
            (CODING_AGENT_MODEL_AUTO, "Default (aider config)"),
        ),
        extra_smoke_argv=("--yes-always", "--no-git"),
    ),
    "gemini": CodingAgentAdapter(
        binary="gemini",
        display_name="Gemini CLI",
        invocation="gemini",
        model_flag="--model",
        list_models_argv=None,
        default_models=(
            (CODING_AGENT_MODEL_AUTO, "Default (CLI auto)"),
            ("gemini-2.5-pro", "gemini-2.5-pro"),
            ("gemini-2.5-flash", "gemini-2.5-flash"),
        ),
        extra_smoke_argv=("--yolo", "--output-format", "json"),
    ),
}


def is_auto_model(model: str | None) -> bool:
    if model is None:
        return True
    stripped = model.strip()
    if not stripped:
        return True
    return stripped.lower() in {"auto", "default"}


def normalize_coding_agent_model(model: str | None) -> str:
    if is_auto_model(model):
        return CODING_AGENT_MODEL_AUTO
    return model.strip()


def resolve_adapter(binary: str) -> CodingAgentAdapter:
    return ADAPTERS.get(binary) or CodingAgentAdapter(
        binary=binary,
        display_name=binary,
        invocation="print",
        model_flag="--model",
        list_models_argv=None,
        default_models=((CODING_AGENT_MODEL_AUTO, "Default (CLI auto)"),),
    )


def resolve_binary_executable(binary: str) -> str | None:
    """Resolve a CLI name to an executable path (handles Windows .cmd/.ps1 shims)."""
    found = shutil.which(binary)
    if found:
        return found
    if os.name != "nt":
        return None
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not path_dir:
            continue
        for suffix in (".exe", ".cmd", ".bat", ".ps1"):
            candidate = Path(path_dir) / f"{binary}{suffix}"
            if candidate.is_file():
                return str(candidate)
    return None


def binary_on_path(binary: str) -> bool:
    return resolve_binary_executable(binary) is not None


def _run_binary_command(
    cmd: list[str],
    run: Callable[..., object],
    *,
    timeout: int,
):
    if not cmd:
        raise ValueError("empty command")
    executable = resolve_binary_executable(cmd[0])
    if not executable:
        raise FileNotFoundError(cmd[0])
    return run([executable, *cmd[1:]], timeout=timeout)


def parse_cursor_list_models(stdout: str) -> list[dict[str, str]]:
    models: list[dict[str, str]] = [
        {"id": CODING_AGENT_MODEL_AUTO, "label": "Auto (CLI default)"}
    ]
    seen = {CODING_AGENT_MODEL_AUTO}
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("Available models") or line.startswith("Tip:"):
            continue
        match = re.match(r"^(\S+)\s+-\s+(.+)$", line)
        if not match:
            continue
        model_id, label = match.group(1), match.group(2).strip()
        if model_id.lower() == "auto" or model_id in seen:
            continue
        seen.add(model_id)
        models.append({"id": model_id, "label": label})
    return models


def list_models_for_binary(
    binary: str,
    run: Callable[..., object],
) -> dict:
    adapter = resolve_adapter(binary)
    if not binary_on_path(binary):
        return {
            "binary": binary,
            "models": [],
            "error": "not_on_path",
            "supports_model_pick": False,
        }

    if adapter.list_models_argv:
        try:
            result = _run_binary_command(
                [binary, *adapter.list_models_argv], run, timeout=30
            )
            stdout = getattr(result, "stdout", "") or ""
            if getattr(result, "returncode", 1) == 0 and stdout.strip():
                models = parse_cursor_list_models(stdout)
                return {
                    "binary": binary,
                    "models": models,
                    "source": "cli",
                    "supports_model_pick": True,
                }
        except Exception:
            pass

    models = [{"id": mid, "label": lbl} for mid, lbl in adapter.default_models]
    return {
        "binary": binary,
        "models": models,
        "source": "defaults",
        "supports_model_pick": True,
    }


def _build_headless_argv(
    binary: str,
    prompt: str,
    model: str | None,
    *,
    mode: str = "smoke",
    json_output: bool = True,
) -> list[str]:
    adapter = resolve_adapter(binary)
    cmd = [binary]
    if adapter.invocation == "exec":
        cmd.extend(adapter.exec_argv)
        cmd.extend(adapter.extra_smoke_argv)
        if mode == "dispatch":
            cmd.extend(adapter.dispatch_argv)
        cmd.append(prompt)
    elif adapter.invocation == "message":
        cmd.extend(["--message", prompt])
        extra = list(adapter.extra_smoke_argv)
        if mode == "dispatch":
            extra = [flag for flag in extra if flag != "--no-git"]
        cmd.extend(extra)
    elif adapter.invocation == "grok":
        cmd.extend(["--prompt", prompt])
        if json_output:
            cmd.extend(adapter.extra_smoke_argv)
    elif adapter.invocation == "gemini":
        cmd.extend([*adapter.extra_smoke_argv, prompt])
    else:
        cmd.extend(["-p", prompt])
        if json_output:
            cmd.extend(adapter.extra_smoke_argv)
        elif binary == "agent":
            cmd.extend(("--trust",))
    if adapter.model_flag and not is_auto_model(model):
        cmd.extend([adapter.model_flag, normalize_coding_agent_model(model)])
    return cmd


def build_smoke_argv(
    binary: str, model: str | None, *, json_output: bool = True
) -> list[str]:
    return _build_headless_argv(
        binary,
        SMOKE_PROMPT,
        model,
        mode="smoke",
        json_output=json_output,
    )


def build_dispatch_argv(binary: str, prompt: str, model: str | None) -> list[str]:
    return _build_headless_argv(
        binary,
        prompt,
        model,
        mode="dispatch",
        json_output=True,
    )


def _agent_smoke_json_unsupported(stdout: str, stderr: str) -> bool:
    combined = f"{stdout}\n{stderr}".lower()
    return any(
        token in combined
        for token in (
            "output-format",
            "unknown option",
            "unrecognized",
            "not supported",
            "invalid option",
        )
    )


def _interpret_smoke_result(
    binary: str,
    *,
    returncode: int,
    stdout: str,
    stderr: str,
    json_attempt: bool = False,
) -> bool | None:
    combined = f"{stdout}\n{stderr}".lower()
    auth_fail_tokens = (
        "unauthorized",
        "authentication",
        "not logged in",
        "api key",
        "invalid model",
        "model not found",
        "unknown model",
        "workspace trust required",
    )
    if binary in {"agent", "claude"} and json_attempt:
        text = (stdout or "").strip()
        if text:
            try:
                payload = json.loads(text.splitlines()[-1])
                if isinstance(payload, dict) and "is_error" in payload:
                    return not bool(payload.get("is_error"))
            except json.JSONDecodeError:
                pass
    if returncode == 0:
        if binary in {"aider", "codex", "grok", "gemini"}:
            return True
        if (stdout or "").strip():
            return True
    if any(token in combined for token in auth_fail_tokens):
        return False
    return None


def smoke_test_coding_agent(
    binary: str,
    model: str | None,
    run: Callable[..., object],
    *,
    timeout: int = SMOKE_TIMEOUT_SECONDS,
) -> bool | None:
    if not binary_on_path(binary):
        return None
    adapter = resolve_adapter(binary)
    if adapter.binary not in ADAPTERS and not shutil.which(binary):
        return None
    try:
        json_argv = build_smoke_argv(binary, model, json_output=True)
        result = _run_binary_command(json_argv, run, timeout=timeout)
        returncode = getattr(result, "returncode", 1)
        stdout = getattr(result, "stdout", "") or ""
        stderr = getattr(result, "stderr", "") or ""
        json_attempt = binary in {"agent", "claude"} and "--output-format" in json_argv
        interpreted = _interpret_smoke_result(
            binary,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            json_attempt=json_attempt,
        )
        if interpreted is not None:
            return interpreted
        if binary == "agent" and (
            _agent_smoke_json_unsupported(stdout, stderr) or returncode != 0
        ):
            plain = _run_binary_command(
                build_smoke_argv(binary, model, json_output=False),
                run,
                timeout=timeout,
            )
            return _interpret_smoke_result(
                binary,
                returncode=getattr(plain, "returncode", 1),
                stdout=getattr(plain, "stdout", "") or "",
                stderr=getattr(plain, "stderr", "") or "",
                json_attempt=False,
            )
        return interpreted
    except Exception:
        return None


def model_display_label(model_id: str, models: list[dict[str, str]] | None = None) -> str:
    if is_auto_model(model_id):
        return "Auto (CLI default)"
    if models:
        for entry in models:
            if entry.get("id") == model_id:
                return str(entry.get("label") or model_id)
    return model_id


def interactive_pick_model(
    binary: str,
    run: Callable[..., object],
    *,
    default: str | None = None,
    force: bool = False,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[..., None] = print,
) -> str:
    """CLI helper: numbered model menu for init."""
    listing = list_models_for_binary(binary, run)
    models = listing.get("models") or [
        {"id": CODING_AGENT_MODEL_AUTO, "label": "Auto (CLI default)"}
    ]
    current = normalize_coding_agent_model(default)

    print_fn()
    print_fn("1c-ii. Coding agent model...")
    for idx, entry in enumerate(models[:40], start=1):
        marker = " (current)" if entry.get("id") == current else ""
        print_fn(f"    | {idx} | {entry.get('id')} | {entry.get('label')}{marker} |")
    if len(models) > 40:
        print_fn(f"    ... {len(models) - 40} more models omitted — type model id manually")

    if force:
        choice = "1"
    else:
        try:
            choice = input_fn(
                "    Model [#, model id, or Enter for auto/default]: "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            choice = ""

    picked = current
    if not choice:
        picked = CODING_AGENT_MODEL_AUTO
    elif choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(models):
            picked = str(models[index].get("id") or CODING_AGENT_MODEL_AUTO)
    else:
        picked = normalize_coding_agent_model(choice)

    label = model_display_label(picked, models)
    print_fn(f"   coding_agent_model: {picked} ({label})")

    if binary_on_path(binary):
        reachable = smoke_test_coding_agent(binary, picked, run)
        if reachable is True:
            print_fn(f"   OK coding CLI reachable ({label})")
        elif reachable is False:
            print_fn(f"   !  coding CLI auth/model check failed ({label})")
        else:
            print_fn(f"   !  coding CLI smoke inconclusive ({label})")
    else:
        print_fn(f"   !  Skipping smoke — '{binary}' not on PATH")

    return picked


def check_coding_agent_cli(
    binary: str,
    model: str | None,
    run: Callable[..., object],
    *,
    probe: bool = False,
    cache_get: Callable[[str, float], object | None] | None = None,
    cache_set: Callable[[str, object], None] | None = None,
    probe_ttl: float = 180.0,
) -> dict:
    normalized_model = normalize_coding_agent_model(model)
    on_path = binary_on_path(binary)
    adapter = resolve_adapter(binary)

    info: dict = {
        "binary": binary,
        "display_name": adapter.display_name,
        "on_path": on_path,
        "model": normalized_model,
        "model_configured": True,
        "model_reachable": None,
        "supports_model_pick": binary in ADAPTERS or on_path,
    }

    if not on_path:
        info["model_configured"] = False
        return info

    if probe:
        cache_key = f"coding_agent_smoke:{binary}:{normalized_model}"
        cached = cache_get(cache_key, probe_ttl) if cache_get else None
        if cached is not None:
            info["model_reachable"] = cached
        else:
            reachable = smoke_test_coding_agent(binary, normalized_model, run)
            info["model_reachable"] = reachable
            if cache_set is not None and reachable is not None:
                cache_set(cache_key, reachable)

    return info
