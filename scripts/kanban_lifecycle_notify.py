#!/usr/bin/env python3
"""Launcher: runs kanban_lifecycle_notify.sh via bash with MSYS path so stdout is captured.
Workaround for https://github.com/NousResearch/hermes-agent/issues/23404"""
import os, sys, subprocess
script_dir = os.path.dirname(os.path.abspath(__file__))
script = os.path.join(script_dir, 'kanban_lifecycle_notify.sh').replace('\\', '/')
# Convert C:/Users/... -> /c/Users/... for MSYS2 bash
if len(script) >= 2 and script[1] == ':':
    script = '/' + script[0].lower() + script[2:]
r = subprocess.run(f'bash "{script}"', shell=True, capture_output=True, text=True, timeout=60)
if r.stdout:
    print(r.stdout, end='')
if r.stderr:
    print(r.stderr, end='', file=sys.stderr)
sys.exit(r.returncode)
