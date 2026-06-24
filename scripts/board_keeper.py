#!/usr/bin/env python3
"""Launcher: exec's board_keeper.sh with POSIX paths so bash doesn't mangle backslashes.
Workaround for https://github.com/NousResearch/hermes-agent/issues/23404"""
import os, sys
script_dir = os.path.dirname(os.path.abspath(__file__))
script = os.path.join(script_dir, 'board_keeper.sh').replace('\\', '/')
os.execvp('bash', ['bash', script] + sys.argv[1:])
