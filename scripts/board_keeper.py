#!/usr/bin/env python3
"""Launcher: runs board_keeper.sh — platform-neutral (Windows Git Bash, Unix direct)."""
import os
import sys
import subprocess
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_NAME = "board_keeper.sh"


def _find_repo_root() -> str:
    """Walk up from SCRIPT_DIR or CWD to find the repo root.

    Prefers the kanban config overlay (only in project roots) over bare .git
    detection — the plugin is its own git repo, and .hermes/kanban exists at
    both user-home and project level (false positive).
    """
    for start in [Path(SCRIPT_DIR), Path.cwd()]:
        for p in [start] + list(start.parents)[:6]:
            # Primary: kanban config overlay — only exists in project roots
            if (p / ".hermes" / "kanban-overrides" / "kanban-config.yaml").is_file():
                return str(p.resolve())
            # Secondary: .git in a directory that also has .hermes/
            # (excludes the plugin repo, which has .git but not .hermes/)
            if (p / ".git").is_dir() and (p / ".hermes").is_dir():
                return str(p.resolve())
    return str(Path.cwd())


env = os.environ.copy()
# Pass board scope through both env var names
for v in ("KANBAN_BOARD", "HERMES_KANBAN_BOARD"):
    if os.environ.get(v):
        env["KANBAN_BOARD"] = os.environ[v]
        break

script = os.path.join(SCRIPT_DIR, SCRIPT_NAME)
cwd = _find_repo_root()
env["REPO_ROOT"] = cwd

if sys.platform == "win32":
    # ── Windows: Git Bash ──
    GIT_BASH = None
    for candidate in [
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Git\usr\bin\bash.exe",
        os.path.expandvars(r"%ProgramFiles%\Git\usr\bin\bash.exe"),
    ]:
        if os.path.isfile(candidate):
            GIT_BASH = candidate
            break
    if not GIT_BASH:
        print("[launcher] Git Bash not found — install Git for Windows", file=sys.stderr)
        sys.exit(1)
    git_usr_bin = os.path.dirname(GIT_BASH)
    env["PATH"] = git_usr_bin + os.pathsep + env.get("PATH", "")
    cmd = [GIT_BASH, script] + sys.argv[1:]
else:
    # ── Unix (Linux / macOS / WSL): run .sh directly ──
    cmd = ["/bin/bash", script] + sys.argv[1:]

r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   timeout=60, cwd=cwd, env=env)
if r.stdout:
    print(r.stdout, end="")
if r.stderr:
    print(r.stderr, end="", file=sys.stderr)
sys.exit(r.returncode)
