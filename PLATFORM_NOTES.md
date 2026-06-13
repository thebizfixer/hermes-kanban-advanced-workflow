# Platform Notes — Windows, macOS, Linux

The kanban-advanced plugin targets **Hermes Agent** which runs on Linux, macOS, and
Windows (native and WSL2). The `.sh` scripts in `scripts/` are written in **bash** and
require a POSIX-compatible shell environment; the `.py` scripts are cross-platform.

Upstream references:
- [Hermes Agent docs](https://hermes-agent.nousresearch.com/docs)
- [Windows Native Guide](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native)
- [Windows WSL2 Guide](https://hermes-agent.nousresearch.com/docs/user-guide/windows-wsl-quickstart)
- [Installation](https://hermes-agent.nousresearch.com/docs/getting-started/installation)
- [Desktop downloads (GitHub Releases)](https://github.com/NousResearch/hermes-agent/releases/latest)

## Windows (native)

Hermes Agent runs natively on Windows 10/11 — no WSL, Cygwin, or Docker required.
Install via the PowerShell one-liner or the Hermes Desktop GUI installer. Both share
the same install and data directories.

### Git Bash (PortableGit)

The Hermes installer provisions **PortableGit** — a self-contained Git-for-Windows
distribution that ships `bash.exe` and the full POSIX toolchain. Hermes sets
`HERMES_GIT_BASH_PATH` to locate bash deterministically.

All `.sh` scripts in `scripts/` run under that Git Bash without modification.
PortableGit provides:

- `/usr/bin/env bash` — shebang support
- `/dev/null` — null device
- Coreutils (`sha256sum`, `grep`, `sed`, `awk`, `mktemp`)
- `/tmp/` mapped to `%TEMP%`

On 32-bit Windows, Hermes falls back to MinGit (no bash) — terminal-tool and
agent-browser features won't work. Upgrade to 64-bit Windows for full support.

### Hermes Desktop

[Hermes Desktop](https://github.com/NousResearch/hermes-agent/releases/latest) is a
thin GUI installer (`.exe`). On first launch it calls `install.ps1` under the hood
to provision Python, Node, PortableGit, and other dependencies. The desktop app and
the PowerShell-installed `hermes` CLI share the same install and data directories —
switch between them freely.

### Hermes home directory

Per the [Windows Native Guide](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native):

- **Install code:** `%LOCALAPPDATA%\hermes\hermes-agent`
- **Data directory:** `%USERPROFILE%\.hermes` (config, profiles, skills, memory, cron)
- **Git:** `%LOCALAPPDATA%\hermes\git` (PortableGit)

The `scripts/lib/hermes_home.sh` helper resolves `$HERMES_HOME` in this order:

1. `$HERMES_HOME` — set explicitly by Hermes Agent itself
2. `$HERMES_STATE_DIR` — Hermes Agent v0.15+ state directory
3. `$HOME/.hermes` — Linux, macOS, WSL2, Git Bash
4. `%USERPROFILE%/.hermes` — Windows native (CMD, PowerShell, Hermes Desktop)
5. `$HOME/.hermes` — fallback (create if needed)

### Temp directory

Scripts use `$KANBAN_TEMP` when available, falling back through `$TMPDIR` → `$TEMP`
→ `/tmp`. On Windows native, `$TEMP` resolves to `C:\Users\<name>\AppData\Local\Temp`.
Git Bash also maps `/tmp` to this directory.

```bash
export KANBAN_TEMP="$TEMP"  # override if needed
```

### Worktree paths

Worktree paths in card bodies use absolute paths. On Windows:

```
--workspace "worktree:/tmp/wt-<plan>-<card>"         # Git Bash (maps /tmp → %TEMP%)
--workspace "worktree:C:/temp/wt-<plan>-<card>"       # Native Windows (CMD/PowerShell)
```

### Native Windows feature support

Per the Windows Native Guide, these features work natively on Windows:
CLI, gateway (Telegram/Discord/etc.), cron scheduler, TUI, browser tool,
MCP servers, skills, memory, voice mode.

The only WSL2-only feature is the dashboard's embedded terminal (`/chat` tab),
which requires a POSIX PTY.

### Python scripts

Python scripts (`token_tracker.py`, `kanban_evaluation_chain.py`, etc.) are
cross-platform. They use `os.environ` for path resolution and handle both forward
and backslash separators. Run with `python3` or `python` on any platform.

## WSL2

Fully supported. Install Hermes inside WSL2 using the standard Linux one-liner.
See the [WSL2 Guide](https://hermes-agent.nousresearch.com/docs/user-guide/windows-wsl-quickstart)
for setup, filesystem boundaries, and networking.

Clone the repo to a **native ext4 path** (e.g., `~/projects/`), not `/mnt/c/` or
`/mnt/e/`. Cross-mount DrvFS paths are blocked by `preflight.sh` (E011) due to
filesystem coherence issues. Native Windows and WSL2 installs coexist — native data
lives under `%USERPROFILE%\.hermes`, WSL2 data under `~/.hermes`.

## macOS

No special configuration needed. All scripts run natively under `zsh` or `bash`.
`$HOME/.hermes` is the default Hermes home. Hermes Desktop is available for macOS
via [GitHub Releases](https://github.com/NousResearch/hermes-agent/releases/latest).

## Linux

No special configuration needed. All scripts run natively under `bash`.
`$HOME/.hermes` is the default Hermes home.

## Known limitations

- **32-bit Windows:** PortableGit unavailable — falls back to MinGit (no bash).
  Terminal-tool and agent-browser features won't work.
- **Dashboard embedded terminal:** WSL2-only (requires POSIX PTY). All other
  features work on native Windows.
- **`sha256sum`:** Not available on macOS by default — `provision.sh` falls back
  to `shasum -a 256`. On Windows, PortableGit provides it.
- **`mktemp -d`:** Not available on native Windows CMD. Use Git Bash or PowerShell
  equivalent (`New-TemporaryDirectory`).
- **`/dev/null`:** Git Bash maps this. On native Windows CMD, use `NUL`.
- **`df -T` (filesystem type):** Not supported by macOS BSD `df`. `preflight.sh`
  falls back to `diskutil info` on macOS. If `diskutil` is also unavailable, the
  `filesystem_coherence` check degrades to a warning (non-blocking).
- **Memory detection (`/proc/meminfo`, `free`):** Linux-only. `preflight.sh` uses
  `vm_stat` + `sysctl hw.pagesize` on macOS for an equivalent available-memory
  estimate. On Windows, Git Bash provides `free`.
- **`grep -P` / PCRE:** Not supported by macOS BSD `grep`. Plan and CLI parsing
  use `scripts/lib/plan_parse.py` and `scripts/lib/cli_output_parse.py` (no
  `grep -oP` in governance scripts; enforced by `scripts/sanity_check.sh`).
