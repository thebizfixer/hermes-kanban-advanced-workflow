#!/usr/bin/env python3
"""Launcher: runs board_keeper.sh via Git Bash with Windows paths.
Workaround for https://github.com/NousResearch/hermes-agent/issues/23404"""
import os, sys, subprocess

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
script = os.path.join(script_dir, 'board_keeper.sh').replace('\\', '/')
args = ' '.join(sys.argv[1:])

git_usr_bin = os.path.dirname(GIT_BASH).replace('\\', '/') if GIT_BASH != "bash" else ""
env = os.environ.copy()
if git_usr_bin:
    env['PATH'] = git_usr_bin + os.pathsep + env.get('PATH', '')

if os.environ.get('HERMES_KANBAN_BOARD'):
    env['KANBAN_BOARD'] = os.environ['HERMES_KANBAN_BOARD']

r = subprocess.run(f'"{GIT_BASH}" "{script}" {args}', shell=True,
                   capture_output=True, text=True, encoding="utf-8", timeout=60, env=env)
if r.stdout:
    print(r.stdout, end='')
if r.stderr:
    print(r.stderr, end='', file=sys.stderr)
sys.exit(r.returncode)
