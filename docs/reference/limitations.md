# Known Limitations

This document catalogs limitations of the kanban-advanced plugin that operators
should plan around.  Items marked "Future" are candidates for a later release.

## 1. Worktree Disk Space

Multiple concurrent boards create N× worktrees in the system temp directory
(`/tmp` on Linux/macOS, `%TEMP%` on Windows).  Each worktree is a full checkout
of the repository's working tree.  Operators should budget at least
`repo_working_tree_size × max_concurrent_boards` of free space on the temp
partition.

The preflight check verifies ≥1GB free at startup.  P1.7 adds a per-card disk
check to board_keeper.  Future: per-plan disk budget based on plan file size.

## 2. Plan File Modified After Decomposition

If commits land on the working branch between decomposition and final audit,
the `Audit-baseline-sha` stamped in the audit card is stale.  The final audit
may report false-positive `plan_file_zero_diff` violations or miss real ones.

**Best practice:** Run kanban-advanced on a dedicated development branch.
The pre-dispatch gate already warns when the working branch has unpushed
commits ahead of origin.

## 3. Cross-Platform Worktree Paths

`/tmp` resolves differently across platforms:
- **Linux:** `/tmp` (typically tmpfs, may be small)
- **macOS:** `/private/tmp` (symlink to `/tmp`)
- **Windows:** `C:\Users\{user}\AppData\Local\Temp`
- **CI:** Often ephemeral — cleaned between pipeline runs

The `_is_dispatcher_absolute()` guard (kanban_decompose.py) handles path
validation for the Hermes dispatcher but doesn't guarantee the directory is
writable or persistent across reboots.

## 4. Git Hook Interference

Repository-level pre-commit hooks (Husky, lint-staged, custom) fire in every
worktree.  These hooks often assume `node_modules/` exists, but freshly
created worktrees haven't run `npm ci` yet.  The coding agent attempts to
commit, the hook fails, and the agent may retry until it gives up — leaving
the card blocked with "no commits."

**Workaround:** Configure `core.hooksPath` per-worktree using
`extensions.worktreeConfig`, or ensure the worktree bootstrap script installs
dependencies before handing the worktree to the agent.

## 5. Gateway Health Monitoring

The plugin verifies gateway health at preflight (blocking) and detects stuck
dispatchers via board_keeper.  However, there is no continuous gateway health
monitor during execution.  If the gateway crashes mid-run, wave progression
stops.

**Recommendation:** Use the dashboard tab for at-a-glance gateway status.
On Windows, the Hermes Desktop installer adds a startup item for auto-restart.
On Linux, run the gateway under systemd or a process supervisor.

## 6. Concurrent Handoff Prevention

Running `kanban_handoff.py` twice for the same `plan_id` is prevented by two
guards: (a) an app-level check for existing open handoff cards, and (b) a
Hermes-level `--idempotency-key` that deduplicates within the idempotency
window.  Stale keys from crashed handoffs expire after 24h (P3.12).
