#!/usr/bin/env python3
"""Launcher: runs board_keeper.sh via bash with MSYS path so stdout is captured.
Workaround for https://github.com/NousResearch/hermes-agent/issues/23404"""
import os, sys, subprocess
script_dir = os.path.dirname(os.path.abspath(__file__))
script = os.path.join(script_dir, 'board_keeper.sh').replace('\\', '/')
if len(script) >= 2 and script[1] == ':':
    script = '/' + script[0].lower() + script[2:]
r = subprocess.run(f'bash "{script}"', shell=True, capture_output=True, text=True, timeout=60)
if r.stdout:
    print(r.stdout, end='')
if r.stderr:
    print(r.stderr, end='', file=sys.stderr)
sys.exit(r.returncode)
