# Filesystem coherence detection

Canonical patterns for **cross-mount** and **dual-clone** issues (E011, preflight FS checks).

## Path-prefix blocklist (preflight)

Reject worktrees when repo root or `HERMES_HOME` spans mount boundaries. See `preflight-env-knobs.md` for `PREFLIGHT_ALLOWED_FS_TYPES`.

## `df -T` FS type check

```bash
df -T "$REPO_ROOT" "$HERMES_HOME" 2>/dev/null | awk 'NR>1 {print $1, $2}'
```

Mismatching device or exotic FS (e.g. `fuse` across WSL/Windows) → WARN or FAIL per overlay.

## Dual-clone / stale worktree

```bash
git worktree list
git worktree prune -n   # dry-run prunable entries
```

Remove prunable entries from abandoned clones before decomposition.

## Single coherent filesystem

See `single-coherent-filesystem.md` for commit-cadence incident patterns. **Fix:** one canonical clone + one `HERMES_HOME`; relocate repo off cross-mount paths.
