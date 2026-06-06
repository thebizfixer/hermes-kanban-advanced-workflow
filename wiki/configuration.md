# Configuration Reference

> **For the agent:** When a user asks "what does this config variable do?" or "how do I configure X?", answer from this page.

Config lives at `.hermes/kanban-overrides/kanban-config.yaml`. Created automatically by `hermes kanban-advanced init`. To create manually:
```bash
cp hermes-kanban-advanced-workflow/kanban-config.example.yaml .hermes/kanban-overrides/kanban-config.yaml
```

## Required variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `working_branch` | Integration branch; orchestrator merges completed sections here | `<branch-name>` (e.g. `main`) |
| `trigger_branch` | CI/CD trigger branch; only operator merges here manually | `production` |
| `feature_branch_prefix` | Prefix for per-section worktree branches | `wt/` |
| `required_secrets` | Comma-separated env vars checked by preflight | `MONGODB_URI,SECRET_KEY` |
| `preflight_api_url` | Health endpoint for API reachability check | `http://127.0.0.1:8000/healthz` |
| `skills_output_path` | Skill output directory (for advanced configuration) | `.hermes/skills/devops` |

## Optional variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `KANBAN_POLICY_PROFILE` | Card body policy enforcement level | `balanced` |
| `PREFLIGHT_PROFILES` | Profiles to validate in preflight §5 | `worker,orchestrator` |
| `PREFLIGHT_MEMORY_MIN_MB` | Blocking memory floor | `1024` |
| `PREFLIGHT_MEMORY_WARN_MB` | Degraded memory threshold | `2048` |
| `PREFLIGHT_SKIP_API` | Skip API health check | unset |
| `PREFLIGHT_SKIP_FS_CHECK` | Skip filesystem coherence check | unset |

## Policy profiles

Set via `KANBAN_POLICY_PROFILE` env var or `--profile` flag on `kanban_card_policy.py`:

| Profile | Missing Files: | Missing agent -p | Eval chain fail |
|---------|---------------|-------------------|-----------------|
| `advisory` | Warn | Warn | Warn |
| `balanced` | Block | Block | Block |
| `strict` | Block + notify | Block + notify | Block + notify |

## Profile config

Every profile used as a card assignee must have `config.yaml` with:
```yaml
model:
  default: <model-name>
  provider: <provider-name>
```

Preflight §5 checks this. Missing config → PR001 error, blocking.

### Thinking / reasoning effort

Set the reasoning effort per profile based on its role:

| Profile | Thinking | Rationale |
|---------|----------|-----------|
| **orchestrator** | `high` | Plans, audits, reconciles — needs depth over speed |
| **worker** | `medium` | Supervises agents, runs eval chain — balance of speed and accuracy |
| **Coding agent** | `low` / off | Code generation — speed over depth; the worker verifies output |

Configure in each profile's `config.yaml`:
```yaml
# orchestrator profile
model:
  default: <model-name>
  provider: <provider-name>
  thinking: high

# worker profile
model:
  default: <model-name>
  provider: <provider-name>
  thinking: medium

# coding agent (passed via agent -p --thinking or equivalent)
# agent -p "..." --thinking low
```

If the coding agent CLI doesn't support a `--thinking` flag, set it via the model configuration or use a model optimized for speed rather than deep reasoning.

**For parallel fan-out with multiple providers, see [[provider-strategy]].**

## Filesystem

The repo must live on a native filesystem (ext4, xfs, apfs, NTFS-native). WSL DrvFs (`/mnt/c/`), NFS, FUSE, and CIFS are **blocked** by preflight check 0. Clone to a native path if needed.

## Override via patches

For project-specific changes to skill files, add `.patch` files in `.hermes/kanban-overrides/patches/`. `provision.sh` applies them after variable substitution. Example:
```
.hermes/kanban-overrides/patches/kanban-advanced:kanban-preflight.patch
.hermes/kanban-overrides/patches/kanban-advanced:kanban-worker.patch
```

Patch format: standard unified diff (`diff -u old new`).

## Hermes v0.15.x kanban config keys

Hermes Agent v0.15.0 added several kanban config keys under the `kanban:` section of `config.yaml`. These are managed by `hermes config` (not `kanban-config.yaml`):

| Key | Default | Purpose |
|-----|---------|---------|
| `kanban.auto_decompose` | `true` | Auto-decompose triage tasks into child trees. **Set to `false` when using manual decomposition** (kanban-advanced does its own decomposition). |
| `kanban.auto_decompose_per_tick` | `3` | Max triage tasks to decompose per dispatcher tick. Throttles aux LLM calls. |
| `kanban.orchestrator_profile` | `""` | Profile that handles triage decomposition. Falls back to default profile. Set to your orchestrator profile name. |
| `kanban.default_assignee` | `""` | Fallback assignee when decomposer can't match a profile. |
| `kanban.dispatch_stale_timeout_seconds` | `14400` | Stale detection: running tasks without heartbeat for this many seconds are auto-reclaimed. `0` disables. |
| `kanban.failure_limit` | `2` | Auto-block after N consecutive non-success attempts (spawn_failed, timed_out, crashed). Built-in circuit-breaker. |
| `kanban.worker_log_rotate_bytes` | `2097152` | Worker log rotation size (2 MiB default). |
| `kanban.worker_log_backup_count` | `1` | Number of rotated worker log backups to keep. |

### New auxiliary tasks (v0.15.0)

Hermes v0.15.0 added two new auxiliary tasks that need model configuration:

| Aux task | Purpose | Config path |
|----------|---------|-------------|
| `kanban_decomposer` | Decomposes triage tasks into child task graphs | `auxiliary.kanban_decomposer.*` |
| `profile_describer` | Generates profile descriptions for the dashboard | `auxiliary.profile_describer.*` |

**For custom providers:** Both default to `provider: auto` / `model: ""`, which won't resolve against custom providers. Configure explicitly:
```bash
hermes config set auxiliary.kanban_decomposer.provider "custom:<provider-name>"
hermes config set auxiliary.kanban_decomposer.model "<model-name>"
hermes config set auxiliary.profile_describer.provider "custom:<provider-name>"
hermes config set auxiliary.profile_describer.model "<model-name>"
```

### Removed: `auxiliary.session_search`

As of v0.15.0, `session_search` no longer uses an auxiliary LLM (PR #27590). Any existing `auxiliary.session_search` block in `config.yaml` is dead config — harmless but should be cleaned up. Run `hermes config migrate` and then remove the stale block.
