# Cron Launcher Pattern (Windows)

Complete `.py` launcher template for running bash cron scripts on Windows.
Workaround for [Hermes core #23404](https://github.com/NousResearch/hermes-agent/issues/23404).

## Template

```python
#!/usr/bin/env python3
"""Launcher: runs <script>.sh via Git Bash with Windows paths.
Workaround for https://github.com/NousResearch/hermes-agent/issues/23404"""
import os, sys, subprocess

# Detect Git Bash — try common locations, fall back to PATH
GIT_BASH = None
for candidate in [
    "C:/Program Files/Git/usr/bin/bash.exe",
    "C:/Git/usr/bin/bash.exe",
]:
    if os.path.isfile(candidate.replace("/", os.sep)):
        GIT_BASH = candidate
        break
if not GIT_BASH:
    GIT_BASH = "bash"  # fallback to PATH

script_dir = os.path.dirname(os.path.abspath(__file__))
script = os.path.join(script_dir, '<script>.sh').replace('\\', '/')
args = ' '.join(sys.argv[1:])

# Ensure MSYS coreutils are on PATH when running bare bash.exe
git_usr_bin = os.path.dirname(GIT_BASH).replace('\\', '/') if GIT_BASH != "bash" else ""
env = os.environ.copy()
if git_usr_bin:
    env['PATH'] = git_usr_bin + os.pathsep + env.get('PATH', '')

r = subprocess.run(f'"{GIT_BASH}" "{script}" {args}', shell=True,
                   capture_output=True, text=True, timeout=60, env=env)
if r.stdout:
    print(r.stdout, end='')
if r.stderr:
    print(r.stderr, end='', file=sys.stderr)
sys.exit(r.returncode)
```

## Why each piece matters

| Pattern | Reason |
|---------|--------|
| `subprocess.run` (not `os.execvp`) | `execvp` kills Python → cron's stdout pipe breaks → output lost |
| Full Git Bash path with fallback detection | `bash` on PATH may resolve to WSL bash or WindowsApps alias, which don't understand Windows paths |
| Forward-slashed Windows paths (`C:/Users/...`) | Bash handles these natively; MSYS paths (`/c/Users/...`) only work inside git-bash sessions |
| `shell=True` | Required for MSYS2 bash to receive paths correctly when invoked from cmd.exe |
| `env` injection for `git_usr_bin` | When cron invokes bash.exe directly (not via a full Git Bash session), MSYS coreutils (`dirname`, `readlink`) are not on PATH |
| `capture_output=True` | Ensures stdout is captured and re-printed; cron runner reads Python's stdout |

## Cron job configuration

Cron jobs using these launchers must:
- Use `no_agent: true` and `deliver: local` (or `all` for lifecycle)
- Reference the `.py` script (e.g., `auto_unblock.py` not `auto_unblock.sh`)
- NOT use `--workdir` (YAML backslash mangling on Windows; scripts use `git rev-parse --show-toplevel` internally)
