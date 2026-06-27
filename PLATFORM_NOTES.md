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

## Coding CLI command names on PATH

Multiple AI coding CLIs may register the same command (e.g. `agent` for Cursor and Grok). Prefer **unambiguous** install commands (`cursor-agent`, `grok`) on PATH before `hermes kanban-advanced init` or dashboard **Bootstrap**. The kanban-advanced plugin lists only commands currently on PATH and warns on contested shared names — it does not repair symlinks or PATH order for you.

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

Worktrees are stored in `<repo>/.worktrees/<task-id>` per the Hermes Agent
convention (`kanban_db.py:5394`). The decomposer (`kanban_decompose.py`) passes
`--workspace worktree` (no explicit path) — Hermes resolves the path to
`.worktrees/<task-id>` using the board's `default_workdir`.

**Prerequisite:** The kanban board must have `default_workdir` set to the repo root:
```bash
hermes kanban boards edit <board> --default-workdir "E:/Projects/<repo>"
```

**Cleanup:** Three scripts handle stale worktree removal:
- `pre_dispatch_gate.sh` sweeps `.worktrees/wt-*` before each decomposition
- `board_keeper.sh` uses `git worktree list --porcelain` for detection
- `git_safe_cleanup.sh` defaults `WORKTREE_PATTERN` to `.worktrees/`

All three use a three-tier removal: `git worktree remove` → `git worktree remove --force`
→ `rm -rf` + `git worktree prune`.

Legacy worktrees under system temp (`/tmp/wt-*`, `%TEMP%/wt-*`) are swept as a
belt-and-suspenders fallback using `$KANBAN_TEMP`.

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

### Troubleshooting common failures

#### Git worktree "already registered" error

**Symptom:** After prior decompositions, workers fail with:
`git worktree add failed: already registered worktree`

**Root cause:** Git's internal worktree metadata (`$GIT_DIR/worktrees/`) persists even
after the worktree directory is deleted. The default `gc.worktreePruneExpire` is 3
months — registrations from minutes ago are never pruned.

**Fix:** Run `git worktree prune --expire=now` before `git worktree add -f`.
The `-f` flag overrides the safeguard for "path already assigned but missing" per the
[git-worktree docs](https://git-scm.com/docs/git-worktree). `worktree_setup.sh` applies
this automatically.

#### Cron jobs active but cards not promoting

**Symptom:** Auto-unblock cron shows as active in `hermes cron list` but cards stay
`blocked` after gate completion.

**Root cause:** Lock contention from dual gateway instances can skip cron ticks.
This commonly happens after a gateway restart when the old process hasn't fully
exited before the new one starts.

**Fix:** Verify a single gateway with `hermes gateway status`. Force a diagnostic
tick with `hermes cron run {job_id}`. See the
[Hermes cron troubleshooting docs](https://hermes-agent.nousresearch.com/docs/guides/cron-troubleshooting#check-3-lock-contention).

#### Debugging silent cron runs

**Symptom:** Cron with `deliver=local` + `no_agent=true` produces zero output —
no way to know if it ran or what it did.

**Fix:** Check `$HERMES_HOME/kanban/logs/auto_unblock.log` for timestamped run
summaries (written by `auto_unblock.sh` L93–95). Format:
`[ISO timestamp] unblocked=N skipped=N errors=N stagger=S max_unblock=M`

Use `tail -5 $HERMES_HOME/kanban/logs/auto_unblock.log` to verify recent activity,
or `kanban_cron_monitor_log_fallback.sh` for automated monitoring.

### Cross-platform scripting (bash)

All `.sh` scripts in `scripts/` must run on Linux, macOS, and Windows (Git Bash).
Windows paths use backslashes (`C:\Users\...`) which bash interprets as escape
sequences. Apply these conventions:

1. **Path normalization at entry:** `${VAR//\\//}` converts backslashes to forward
   slashes. Safe no-op on Linux/macOS (no backslashes to replace). Apply to
   `HERMES_HOME`, `BUNDLE_PATH`, and `REPO_ROOT` at the top of every script.

2. **Python one-liners:** Never interpolate paths with `${VAR}` into Python strings.
   Use `os.environ.get('VAR')` or `os.path.join()`. Example:
   ```bash
   # BROKEN on Windows (\\U becomes unicode escape):
   python3 -c "open('${HERMES_HOME}/kanban.db')"
   # FIXED:
   python3 -c "import os; open(os.path.join(os.environ['HERMES_HOME'], 'kanban.db'))"
   ```

3. **`test -x`:** Not supported on Windows (no executable bit). Use `test -f` or
   `python3 -c "import os; os.access(path, os.X_OK)"`.

4. **YAML config:** Never store Windows backslash paths in YAML (cron `workdir`,
   overlay `bundle_path`). The YAML parser interprets `\U`, `\A` as escape sequences.
   Use forward slashes (`C:/Users/...`) in all config files.

5. **`source` guards for cron scripts:** Scripts invoked by cron (`auto_unblock.sh`,
   `board_keeper.sh`, `kanban_lifecycle_notify.sh`) must not die on missing lib files.
   Guard with `2>/dev/null || true`.

6. **Gate script (`PREFLIGHT_SKIP_CODING_AGENT_CLI`):** `kanban_handoff.py` sets
   `PREFLIGHT_SKIP_CODING_AGENT_CLI=1` unconditionally when invoking the pre-dispatch
   gate (L453–455). This skips the coding-agent CLI smoke check which often hangs in
   non-interactive contexts on Windows. Manual gate invocation may need it set
   explicitly.

7. **Import paths:** Use `from lib.card_body` (not `from card_body`) in Python scripts.
   The decomposer adds `scripts/` to `sys.path` but not `scripts/lib/`.

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
- **Python gate stdout (Windows cp1252):** `verify_anchors.py`, `audit_anchors.py`,
  and other planning gates print **ASCII-only** status labels (`PASS:` / `WARN:` /
  `FAIL:`) so native PowerShell and legacy consoles do not raise
  `UnicodeEncodeError`. Prefer `--json` when bash wrappers need counts.
  `plan_parse.py suggest-anchors` shells out to **`rg`** (ripgrep) — available in
  Hermes PortableGit / Git Bash on Windows; returns no suggestions when `rg` is absent.
