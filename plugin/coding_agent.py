"""Coding-agent CLI adapters — model listing, smoke tests, status."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from plugin.coding_agent_env import (
    AUTH_PROFILES,
    audit_coding_agent_prerequisites,
    describe_prerequisite_issues,
    ensure_coding_agent_runtime_env,
    is_home_unbound_error,
    normalize_auth_profile_key,
)

CODING_AGENT_MODEL_AUTO = "auto"
SMOKE_PROMPT = "say ok"
SMOKE_TIMEOUT_SECONDS = 180
AUTH_PROBE_TIMEOUT_SECONDS = 15
CODING_AGENT_AUTH_LOCK_STALE_SECONDS = int(
    os.environ.get("CODING_AGENT_AUTH_LOCK_STALE_SECONDS", "600")
)
CODING_AGENT_AUTH_LOCK_WAIT_PROBE = 5
CODING_AGENT_AUTH_LOCK_WAIT_DISPATCH = int(
    os.environ.get("CODING_AGENT_AUTH_LOCK_WAIT_SECONDS", "120")
)

CONFLICT_MESSAGE = (
    "symlink conflict: two or more binaries are configured with the same command"
)
CONFLICT_HINT = (
    "Install your preferred CLI's unambiguous command (e.g. cursor-agent or grok), "
    "update Binary on PATH, and Save. See docs/reference/coding-agents.md."
)
INIT_PREAMBLE = (
    "Binaries currently on PATH (install your chosen CLI first, "
    "then pick its command here):"
)
CONTESTED_AGENT_LABEL = (
    "agent (shared name — multiple CLIs use this; prefer cursor-agent or grok)"
)

# product_key -> (display_name, preferred_commands, contested_commands)
PRODUCT_REGISTRY: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "cursor": ("Cursor CLI", ("cursor-agent",), ("agent",)),
    "claude": ("Claude Code", ("claude",), ()),
    "codex": ("OpenAI Codex", ("codex",), ()),
    "grok": ("grok-cli", ("grok",), ("agent",)),
    "aider": ("Aider", ("aider",), ()),
    "gemini": ("Gemini CLI", ("gemini",), ()),
}


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
    if binary in ("cursor-agent", "agent"):
        return ADAPTERS["agent"]
    return ADAPTERS.get(binary) or CodingAgentAdapter(
        binary=binary,
        display_name=binary,
        invocation="print",
        model_flag="--model",
        list_models_argv=None,
        default_models=((CODING_AGENT_MODEL_AUTO, "Default (CLI auto)"),),
    )


def is_cursor_binary(binary: str) -> bool:
    """True for cursor-agent and agent (Cursor CLI)."""
    return resolve_adapter(binary).binary == "agent"


def is_contested_binary_name(name: str) -> bool:
    """True when multiple supported products claim the same command name."""
    claimants = 0
    for _key, (_display, preferred, contested) in PRODUCT_REGISTRY.items():
        if name in preferred or name in contested:
            claimants += 1
    return claimants > 1


def get_available_coding_binaries() -> list[dict[str, str | bool]]:
    """Supported commands currently on PATH for init/dashboard pickers."""
    results: list[dict[str, str | bool]] = []
    seen: set[str] = set()

    for product_key, (display_name, preferred, contested_cmds) in PRODUCT_REGISTRY.items():
        for command in (*preferred, *contested_cmds):
            if command in seen or not binary_on_path(command):
                continue
            seen.add(command)
            if is_contested_binary_name(command):
                results.append(
                    {
                        "command": command,
                        "label": CONTESTED_AGENT_LABEL,
                        "product_key": "",
                        "contested": True,
                    }
                )
            else:
                results.append(
                    {
                        "command": command,
                        "label": f"{command} ({display_name})",
                        "product_key": product_key,
                        "contested": False,
                    }
                )
    return results


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


def _coding_agent_auth_lock_path() -> Path:
    hermes_home = os.environ.get("HERMES_HOME", "").strip()
    base = Path(hermes_home) if hermes_home else Path.home() / ".hermes"
    lock_dir = base / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / "coding-agent-auth.lock"


def _clear_stale_coding_agent_auth_lock(lockfile: Path) -> None:
    if not lockfile.exists():
        return
    try:
        age = time.time() - lockfile.stat().st_mtime
        if age > CODING_AGENT_AUTH_LOCK_STALE_SECONDS:
            lockfile.unlink(missing_ok=True)
    except OSError:
        pass


def _resolve_auth_lock_wait(timeout: int, *, lock_wait_seconds: int | None) -> int:
    if lock_wait_seconds is not None:
        return lock_wait_seconds
    if timeout <= AUTH_PROBE_TIMEOUT_SECONDS:
        return CODING_AGENT_AUTH_LOCK_WAIT_PROBE
    return CODING_AGENT_AUTH_LOCK_WAIT_DISPATCH


def _run_binary_command(
    cmd: list[str],
    run: Callable[..., object],
    *,
    timeout: int,
    use_auth_lock: bool = False,
    lock_wait_seconds: int | None = None,
):
    if not cmd:
        raise ValueError("empty command")
    executable = resolve_binary_executable(cmd[0])
    if not executable:
        raise FileNotFoundError(cmd[0])
    argv = [executable, *cmd[1:]]
    wait = _resolve_auth_lock_wait(timeout, lock_wait_seconds=lock_wait_seconds)
    if use_auth_lock and sys.platform != "win32":
        try:
            import fcntl

            lockfile = _coding_agent_auth_lock_path()
            _clear_stale_coding_agent_auth_lock(lockfile)
            with open(lockfile, "a+", encoding="utf-8") as lockfh:
                fcntl.flock(lockfh.fileno(), fcntl.LOCK_EX)
                return run(argv, timeout=timeout)
        except ImportError:
            pass
    if use_auth_lock and shutil.which("flock"):
        lockfile = _coding_agent_auth_lock_path()
        _clear_stale_coding_agent_auth_lock(lockfile)
        return run(["flock", "-w", str(wait), str(lockfile), *argv], timeout=timeout)
    return run(argv, timeout=timeout)


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
        elif binary in ("agent", "cursor-agent"):
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
        "authentication required",
        "authentication",
        "not logged in",
        "login required",
        "sign in",
        "api key",
        "invalid model",
        "model not found",
        "unknown model",
        "workspace trust required",
    )
    if (is_cursor_binary(binary) or binary == "claude") and json_attempt:
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
    if is_home_unbound_error(stdout, stderr):
        return False
    if any(token in combined for token in auth_fail_tokens):
        return False
    return None


def _cursor_status_suggests_logged_in(
    binary: str = "agent",
    run: Callable[..., object] | None = None,
) -> bool:
    """Cursor status can show OAuth present while headless execution still fails."""
    if not is_cursor_binary(binary):
        return False
    status_cmds: list[str] = []
    for cmd_name in (binary, "cursor-agent", "agent"):
        if cmd_name not in status_cmds and binary_on_path(cmd_name):
            status_cmds.append(cmd_name)
    if not status_cmds:
        return False
    for cmd_name in status_cmds:
        try:
            if run is not None:
                result = run([cmd_name, "status"], timeout=10)
                stdout = getattr(result, "stdout", "") or ""
                stderr = getattr(result, "stderr", "") or ""
            else:
                completed = subprocess.run(
                    [cmd_name, "status"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                stdout = completed.stdout or ""
                stderr = completed.stderr or ""
            combined = f"{stdout}\n{stderr}".lower()
            if any(
                token in combined
                for token in ("logged in", "authenticated", "auth.json")
            ):
                return True
        except Exception:
            continue
    return False


def describe_smoke_failure(
    binary: str,
    *,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
    run: Callable[..., object] | None = None,
) -> str:
    combined = f"{stdout}\n{stderr}".lower()
    if is_home_unbound_error(stdout, stderr):
        return (
            f"{binary}: HOME is unset in the worker/gateway environment — "
            "coding CLIs cannot load OAuth credentials. Fix: set HOME in project "
            ".env (init/Save), gateway systemd Environment=HOME=..., or source "
            "scripts/lib/coding_agent_env.sh before smoke"
        )
    if timed_out:
        base = (
            f"{binary}: smoke timed out — headless execution did not complete"
        )
        if is_cursor_binary(binary):
            base += (
                " (expired Cursor OAuth often hangs instead of returning "
                "'Authentication required')"
            )
        else:
            return base
    elif "workspace trust required" in combined:
        return (
            f"{binary}: workspace trust required — pass --trust on headless "
            "calls from worktrees (coding_agent_invoke.sh does this)"
        )
    elif any(
        token in combined
        for token in (
            "authentication required",
            "authentication",
            "unauthorized",
            "not logged in",
            "login required",
            "sign in",
        )
    ):
        base = f"{binary}: authentication failed for headless execution"
    else:
        snippet = (stderr or stdout).strip().splitlines()
        tail = snippet[-1] if snippet else "no output"
        base = f"{binary}: smoke failed ({tail})"

    profile = AUTH_PROFILES.get(normalize_auth_profile_key(binary))
    if profile:
        if profile.login_hint:
            base += f". Fix: {profile.login_hint}"
        if profile.notes:
            base += f" ({profile.notes})"
    if is_cursor_binary(binary) and _cursor_status_suggests_logged_in(binary, run):
        if not is_home_unbound_error(stdout, stderr):
            base += (
                "; agent status looks logged in — if HOME is set, token may be "
                "expired: agent login, then delete .hermes/kanban/preflight_cache.json"
            )
    return base


def smoke_test_coding_agent(
    binary: str,
    model: str | None,
    run: Callable[..., object],
    *,
    timeout: int = SMOKE_TIMEOUT_SECONDS,
    fast: bool = False,
) -> bool | None:
    if not binary_on_path(binary):
        return None
    adapter = resolve_adapter(binary)
    if adapter.binary not in ADAPTERS and not shutil.which(binary):
        return None
    try:
        if is_cursor_binary(binary):
            probe_timeout = min(timeout, AUTH_PROBE_TIMEOUT_SECONDS)
            plain_argv = build_smoke_argv(binary, model, json_output=False)
            try:
                probe = _run_binary_command(
                    plain_argv, run, timeout=probe_timeout, use_auth_lock=True
                )
                probe_ok = _interpret_smoke_result(
                    binary,
                    returncode=getattr(probe, "returncode", 1),
                    stdout=getattr(probe, "stdout", "") or "",
                    stderr=getattr(probe, "stderr", "") or "",
                    json_attempt=False,
                )
                if fast:
                    if probe_ok is True:
                        return True
                    return False
                if probe_ok is False:
                    return False
            except subprocess.TimeoutExpired:
                return False

        if fast:
            argv = build_smoke_argv(
                binary,
                model,
                json_output=is_cursor_binary(binary)
                or binary in {"claude", "codex", "gemini"},
            )
            fast_timeout = min(timeout, AUTH_PROBE_TIMEOUT_SECONDS)
            result = _run_binary_command(
                argv,
                run,
                timeout=fast_timeout,
                use_auth_lock=is_cursor_binary(binary),
            )
            return _interpret_smoke_result(
                binary,
                returncode=getattr(result, "returncode", 1),
                stdout=getattr(result, "stdout", "") or "",
                stderr=getattr(result, "stderr", "") or "",
                json_attempt="--output-format" in argv,
            )

        json_argv = build_smoke_argv(binary, model, json_output=True)
        result = _run_binary_command(
            json_argv,
            run,
            timeout=timeout,
            use_auth_lock=is_cursor_binary(binary),
        )
        returncode = getattr(result, "returncode", 1)
        stdout = getattr(result, "stdout", "") or ""
        stderr = getattr(result, "stderr", "") or ""
        json_attempt = (
            is_cursor_binary(binary) or binary == "claude"
        ) and "--output-format" in json_argv
        interpreted = _interpret_smoke_result(
            binary,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            json_attempt=json_attempt,
        )
        if interpreted is not None:
            return interpreted
        if is_cursor_binary(binary) and (
            _agent_smoke_json_unsupported(stdout, stderr) or returncode != 0
        ):
            plain = _run_binary_command(
                build_smoke_argv(binary, model, json_output=False),
                run,
                timeout=timeout,
                use_auth_lock=True,
            )
            return _interpret_smoke_result(
                binary,
                returncode=getattr(plain, "returncode", 1),
                stdout=getattr(plain, "stdout", "") or "",
                stderr=getattr(plain, "stderr", "") or "",
                json_attempt=False,
            )
        return interpreted
    except subprocess.TimeoutExpired:
        return False
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
