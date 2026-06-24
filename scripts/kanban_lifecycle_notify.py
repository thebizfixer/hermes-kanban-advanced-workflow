#!/usr/bin/env python3
"""Launcher: runs kanban_lifecycle_notify.sh via Git Bash with Windows paths.
Locates the repo root for config/plan_id resolution.
Workaround for https://github.com/NousResearch/hermes-agent/issues/23404"""
import os, sys, subprocess
from pathlib import Path

GIT_BASH = None
for candidate in [
    "C:/Program Files/Git/usr/bin/bash.exe",
    "C:/Git/usr/bin/bash.exe",
    os.path.expandvars("%ProgramFiles%/Git/usr/bin/bash.exe"),
]:
    if os.path.isfile(candidate.replace("/", os.sep)):
        GIT_BASH = candidate.replace("/", os.sep)
        break
if not GIT_BASH:
    GIT_BASH = "bash"

script_dir = os.path.dirname(os.path.abspath(__file__))
script = os.path.join(script_dir, 'kanban_lifecycle_notify.sh').replace('\\', '/')
args = ' '.join(sys.argv[1:])

# Find repo root: check env var, then search for lifecycle_plan_id marker
repo_root = os.environ.get("HERMES_KANBAN_REPO_ROOT", "")
if not repo_root:
    for start in [Path(os.getcwd()), Path.home()]:
        try:
            for p in [start] + list(start.parents)[:6]:
                marker = p / '.hermes' / 'kanban' / 'logs' / 'lifecycle_plan_id'
                if marker.is_file():
                    repo_root = str(p.resolve())
                    break
        except Exception:
            pass
        if repo_root:
            break
# Fallback: try git rev-parse
if not repo_root:
    for d in [os.getcwd(), str(Path.home() / 'Projects' / 'hermes-kanban-advanced-workflow')]:
        try:
            r = subprocess.run(['git', '-C', d, 'rev-parse', '--show-toplevel'],
                             capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                repo_root = r.stdout.strip().replace('\\', '/')
                break
        except Exception:
            pass

git_usr_bin = os.path.dirname(GIT_BASH).replace('\\', '/') if GIT_BASH != "bash" else ""
env = os.environ.copy()
if git_usr_bin:
    env['PATH'] = git_usr_bin + os.pathsep + env.get('PATH', '')

r = subprocess.run(f'"{GIT_BASH}" "{script}" {args}', shell=True,
                   capture_output=True, text=True, timeout=60, env=env,
                   cwd=repo_root or None)
if r.stdout:
    print(r.stdout, end='')
if r.stderr:
    print(r.stderr, end='', file=sys.stderr)
sys.exit(r.returncode)
