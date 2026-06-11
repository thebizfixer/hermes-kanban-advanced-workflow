# Configuration Reference

> **For the agent:** When a user asks "what does this config variable do?" or "how do I configure X?", answer from this page.

Config lives at `.hermes/kanban-overrides/kanban-config.yaml`. Created automatically by `hermes kanban-advanced init`. To create manually:
```bash
cp hermes-kanban-advanced-workflow/kanban-config.example.yaml .hermes/kanban-overrides/kanban-config.yaml
```

## Required variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `working_branch` | Integration branch; orchestrator merges completed sections here | Detected from git upstream / `origin/HEAD` at init, or set explicitly |
| `coding_agent_binary` | Headless CLI coding agent binary on PATH (set during init) | `agent` (Cursor CLI), `claude`, `codex`, etc. |
| `coding_agent_model` | Model ID for the coding CLI (`auto` = CLI default) | `auto` |
| `feature_branch_prefix` | Prefix for per-section worktree branches | `wt/` |
| `required_secrets` | Comma-separated env vars checked by preflight | `MONGODB_URI,SECRET_KEY` |
| `preflight_api_url` | Health endpoint for API reachability check | `http://127.0.0.1:8000/healthz` |
| `skills_output_path` | Skill output directory (for advanced configuration) | `.hermes/skills/devops` |

## Optional variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `trigger_branch` | Protected branch agents must not push to (E009 when set) | unset — leave blank to disable |
| `policy_profile` | Governance enforcement in `kanban-config.yaml` (`advisory` \| `balanced` \| `strict`) | `balanced` |
| `KANBAN_POLICY_PROFILE` | Runtime mirror of `policy_profile` (written to `.env` at init) | `balanced` |
| `worker_profile` | Hermes profile for implementation cards | `kanban-advanced-worker` |
| `orchestrator_profile` | Hermes profile for gate/audit/orchestration cards | `kanban-advanced-orchestrator` |
| `preflight_profiles` | Profiles validated in preflight §5 | `kanban-advanced-worker,kanban-advanced-orchestrator` |
| `PREFLIGHT_PROFILES` | Env override for preflight §5 (legacy) | same as `preflight_profiles` |
| `PREFLIGHT_MEMORY_MIN_MB` | Blocking memory floor | `1024` |
| `PREFLIGHT_MEMORY_WARN_MB` | Degraded memory threshold | `2048` |
| `PREFLIGHT_SKIP_API` | Skip API health check | unset |
| `PREFLIGHT_SKIP_FS_CHECK` | Skip filesystem coherence check | unset |

## Coding agent resolution

The `coding_agent_binary` flows through three layers to the worker:

1. **Init (step 1c)** — user picks binary from supported agents table → written to `kanban-config.yaml` and `.env` as `KANBAN_CODING_AGENT`
2. **Init (step 1c-ii)** — user picks model (`auto` or a CLI-specific ID; Cursor: `agent --list-models`) → `coding_agent_model` in YAML and `KANBAN_CODING_AGENT_MODEL` in `.env`
3. **Worker environment** — `.env` is sourced at session start → both env vars available
4. **Worker dispatch** — builds `[KANBAN_CODING_AGENT, "-p", prompt, ...]` and adds `--model` when `KANBAN_CODING_AGENT_MODEL` is not `auto`

To change binary or model: use dashboard **Coding Agent** (binary + model row) and **Save**, edit `kanban-config.yaml` / `.env`, or re-run `hermes kanban-advanced init` (preserves existing values unless you override interactively).

## Re-init and branch preservation

`hermes kanban-advanced init` and dashboard **Bootstrap** refresh dispatch profiles (SOUL.md, role-only skills, verification), materialized shared skills, and cron scripts. See [[bootstrap]]. They **do not** reset `working_branch` or `trigger_branch` when `kanban-config.yaml` already exists — values are read from the overlay unless you pass explicit overrides:

```bash
hermes kanban-advanced init --project-root .                    # keeps existing branches
hermes kanban-advanced init --project-root . --working-branch staging  # override integration branch
```

To change branches on an initialized project, prefer dashboard **Save** or edit `kanban-config.yaml` directly. **Working branch** defaults to git upstream / `origin/HEAD` / local `HEAD`, then `main`. **Trigger branch** is optional — leave blank to skip deploy-branch protection.

Optional keys you added manually (e.g. `feature_branch_prefix`, `gateway_timeout_seconds`) are preserved across re-init.

## Project root for dashboard / API

The dashboard settings API resolves which repo owns `.hermes/kanban-overrides/kanban-config.yaml`. Resolution order:

1. `KANBAN_PROJECT_ROOT` or `HERMES_PROJECT_ROOT` (absolute path to your app repo)
2. `HERMES_KANBAN_CONFIG` (absolute path to the overlay file)
3. Walk up from the gateway cwd — **prefers** directories with an existing overlay over bare `.git` / `.env` markers

Set `KANBAN_PROJECT_ROOT` when you run multiple clones or when the gateway cwd might be the plugin bundle instead of your application.

## Policy profiles (single governance knob)

Set at **init** (CLI `hermes kanban-advanced init`, dashboard **Governance profile** dropdown) or edit `policy_profile` in `kanban-config.yaml`. Init writes `KANBAN_POLICY_PROFILE` to `.env` as a runtime mirror. **Source of truth:** `kanban-config.yaml` — resolution order is config → `.env` → `balanced`. Re-run init or click dashboard **Save** to resync `.env` after hand-editing config.

| Profile | Card body policy | Evaluation chain | Board / plan gates |
|---------|------------------|------------------|-------------------|
| `advisory` | Warn, allow dispatch | Warn, allow complete | Failures downgraded to warnings |
| `balanced` (default) | Block | Block | Warnings pass with review |
| `strict` | Block + log intervention | Block + log intervention | Warnings treated as blocking |

Per-run override: `KANBAN_POLICY_PROFILE=strict` or `--profile strict` on `kanban_card_policy.py` / `validate_board.sh` / `verify_optimization.sh`.

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
| **kanban-advanced-orchestrator** | `high` | Plans, audits, reconciles — needs depth over speed |
| **kanban-advanced-worker** | `medium` | Supervises agents, runs eval chain — balance of speed and accuracy |
| **Coding agent** | `low` / off | Code generation — speed over depth; the worker verifies output |

Dispatch profiles are created by init with `--no-skills` (no Hermes bundled skills). SOUL and role skills: [[bootstrap]].

Configure in each profile's `config.yaml`:
```yaml
# kanban-advanced-orchestrator
model:
  default: <model-name>
  provider: <provider-name>
  thinking: high

# kanban-advanced-worker
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
