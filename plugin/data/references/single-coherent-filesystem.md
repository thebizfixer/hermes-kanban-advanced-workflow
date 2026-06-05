# Single Coherent Filesystem — Why It Matters for Long-Running Agents

## The problem

Long-running multi-agent kanban workflows are uniquely vulnerable to a class of failures that do not appear in short, single-agent tasks: **cross-mount filesystem boundary corruption**.

When an agent's working copy sits on a translated or network-mounted path — such as:
- WSL DrvFs mounts (`/mnt/c/`, `/mnt/e/`)
- macFUSE, SSHFS, or NFS mounts
- Symlinks that cross OS translation boundaries

...the filesystem appears to work fine for individual file reads and writes. The failure mode is subtle: some operations (SQLite journals, mmap, `fsync`, `posixpath.realpath` resolution) behave differently or fail silently across the mount boundary.

### What goes wrong in practice

| Operation | Failure mode on cross-mount paths |
|-----------|----------------------------------|
| SQLite state databases (`kanban.db`, `state.db`) | Journal files may not be visible cross-mount; transactions can appear committed but not durable |
| `posixpath.realpath()` | Can raise `OSError` or return an incorrect path when the real path crosses the mount boundary |
| `git commit` inside a worktree | May succeed in the working copy but produce a dangling commit not visible from the host |
| Agent backup operations | Crash mid-backup with `FileNotFoundError` on paths that exist on the host but not from inside the mount |
| File write + read-back | Write appears to succeed; read immediately after returns stale content (page cache not flushed across mount) |

### Incident pattern

A long-running kanban workflow runs fine for sections 1–3. During section 4 (or during an automatic checkpoint/backup), a cross-mount path resolution fails with a Python traceback. The agent process crashes. The gateway timeout triggers. On restart, sections 1–3 appear committed, but section 4 was in progress and its state database (`kanban.db`) is partially written — the restart sees the section as incomplete and reruns it, producing duplicate or conflicting work.

## The rule

**The agent's working copy must live on a single native filesystem.**

- On Linux/WSL: the working copy must be on the native ext4 (or similar) filesystem — not under `/mnt/`. Clone into `~/projects/` or similar.
- On macOS: the working copy should be on APFS, not a macFUSE or network share.
- On Windows-native (without WSL): the standard NTFS drive path is fine.

**Verify before every board:**

```bash
pwd
# Must NOT start with /mnt/ (WSL), or contain FUSE/NFS indicators
df -P . | tail -1 | awk '{print $1, $6}'
# Filesystem type must be local native (ext4, xfs, apfs, ntfs)
# Fail if type is 9p (WSL DrvFs), nfs, fuse, cifs, smbfs
```

This check is built into `kanban-preflight` § Filesystem coherence check (check 0). It runs before decomposition. A `fail` result blocks the board from starting.

### Configuration overrides

| Env var | Purpose | Default |
|---|---|---|
| `PREFLIGHT_ALLOWED_FS_TYPES` | Comma-separated whitelist of allowed filesystem types (overrides default blocklist) | (unset — uses default blocklist: `9p nfs nfs4 fuse fuseblk cifs smbfs sshfs`) |
| `PREFLIGHT_SKIP_FS_CHECK` | Emergency override — set to `1` to skip filesystem coherence check entirely | (unset) |

Example for containerized workers where `overlay` is the native FS:
```bash
export PREFLIGHT_ALLOWED_FS_TYPES=ext4,overlay,fuse
```

## The commit cadence rule

Even on a healthy filesystem, runtime crashes and gateway timeouts lose work. The mitigation is simple: **push after every section**.

The orchestrator pushes the integration branch (`${working_branch}`) after merging each section's worktree branch. A crash during section N+1 loses at most section N+1's partial work. Sections 1–N are safely in the remote and will not be re-done on restart.

**Without per-section pushes:** a gateway timeout during section 4 of 10 loses sections 3–4 (or more, if the orchestrator batched merges). All of that work reruns on the next board start.

**With per-section pushes:** a gateway timeout during section 4 loses at most the in-progress section 4. The orchestrator can resume at section 4 after restart.

### What "per-section" means

After the orchestrator confirms a section's worktree branch has been merged into `${working_branch}`:

```bash
git checkout ${working_branch}
git merge --no-ff wt/<section-card-name>
git push origin ${working_branch}
```

This push must happen before the orchestrator creates the next section's card.

## Two-layer defense

| Layer | Defense | Scope |
|-------|---------|-------|
| Filesystem coherence | Working copy on native FS; preflight blocks cross-mount | Prevents silent corruption |
| Commit cadence | Push after each section | Limits crash/timeout loss to one section |

Neither layer substitutes for the other. A native filesystem without per-section pushes still loses work on crashes. Per-section pushes on a cross-mount filesystem still silently corrupts state.

## Recovery

If the working copy is already on a cross-mount path when a board is in progress:

1. Stop the board. Block all running tasks.
2. `git push` any commits that are only local (do not `push --force`).
3. Clone a fresh copy to a native filesystem path.
4. Continue the board from the clone. The remote has the safely pushed sections.

Do not attempt to move an in-progress working copy. Clone fresh and resume.
