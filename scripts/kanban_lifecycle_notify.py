#!/usr/bin/env python3
"""Launcher: runs kanban_lifecycle_notify.sh via Git Bash with Windows paths.
Locates the repo root (required for config/plan_id resolution).
Workaround for https://github.com/NousResearch/hermes-agent/issues/23404"""
import os, sys, subprocess
from pathlib import Path

GIT_BASH = "C:/Program Files/Git/usr/bin/bash.exe"
script_dir = os.path.dirname(os.path.abspath(__file__))
script = os.path.join(script_dir, 'kanban_lifecycle_notify.sh').replace('\\', '/')

# Find repo root: look for plan memory marker up from known locations
repo_root = None
for start in [Path(os.getcwd()), Path.home()]:
    try:
        for p in [start] + list(start.parents)[:6]:
            marker = p / '.hermes' / 'kanban' / 'memory'
            if marker.is_dir() and any(marker.glob('*.json')):
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

args = ' '.join(sys.argv[1:])
# Ensure MSYS coreutils (dirname, etc.) are on PATH when running bare bash.exe
env = os.environ.copy()
git_usr_bin = os.path.dirname(GIT_BASH).replace('\\', '/')  # C:/Program Files/Git/usr/bin
env['PATH'] = git_usr_bin + os.pathsep + env.get('PATH', '')
# Pass board scope if set (for multi-board isolation)
if os.environ.get('HERMES_KANBAN_BOARD'):
    env['KANBAN_BOARD'] = os.environ['HERMES_KANBAN_BOARD']
# Forward --board flag from CLI args to shell script
board_flag = ""
for i, arg in enumerate(sys.argv[1:]):
    if arg == "--board" and i + 1 < len(sys.argv) - 1:
        board_flag = f"--board {sys.argv[i + 2]}"
        break
if board_flag:
    args = f"{args} {board_flag}"
r = subprocess.run(f'"{GIT_BASH}" "{script}" {args}', shell=True,
                   capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=repo_root, env=env)
if r.stdout:
    print(r.stdout, end='')
if r.stderr:
    print(r.stderr, end='', file=sys.stderr)
sys.exit(r.returncode)
