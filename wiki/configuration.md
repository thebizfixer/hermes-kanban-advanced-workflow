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
| `coding_agent_binary` | Headless CLI command on PATH (set during init step 1c from on-PATH list) | `cursor-agent`, `claude`, `codex`, `grok`, … — prefer unambiguous names over shared `agent`; see [coding agents](../docs/reference/coding-agents.md) § Binary name collisions |
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
| `notify_lifecycle` | Per-card start/running/done gateway messages after gate completes (`kanban-lifecycle-notify-5m` cron) | `true` |
| `notify_deliver` | Optional override for lifecycle/completion cron `--deliver` (`telegram`, `discord`, `all`, …). When omitted, `scripts/lib/resolve_notify_deliver.sh` resolves home channel | auto |
| `walk_away_mode` | Unattended post-execution after final audit + completion notify (`kanban_walk_away_post_exec.sh`) | `false` |
| `gateway_timeout_seconds` | Gateway timeout hint for commit-cadence advice | unset |
| `final_audit_max_remediation_rounds` | Max post-flight remediation rounds before escalation (`final_audit_sanity.py`) | `2` |
| `final_audit_overrides` | Tier 2 doc-coverage allowlist (array of `signal`, `path`, `rationale`) | `[]` |
| `subagent_gate.enabled` | Parallel pre-dispatch gate via Hermes `delegate_task` (orchestrator session); serial fallback when `false` or no `delegation` toolset | `true` |
| `subagent_gate.timeouts` | Per-domain seconds before E022 (`plan_gate`, `env_gate`, `infra_gate`, `plan_parse`, `cron_setup`) | see example YAML |
| `ui_stack` | Framework-neutral presentation acceptance anchors (route shell glob, motion patterns, frontend test command) | unset — optional; required when running layout acceptance on a host UI |
| `plan_search_dirs` | Repo-relative directories to search for plan markdown; init always writes `.hermes/kanban/plans` first (canonical SSOT). Built-in resolver also checks common agent tool dirs | `[.hermes/kanban/plans]` |
| `plan_memory_path` | Repo-relative plan memory JSON directory | `.hermes/kanban/memory` |

`final_audit_overrides` is **operator-owned**: read at audit time from overlay YAML but **not** in init `_MANAGED_KEYS` — re-run `hermes kanban-advanced init` does not overwrite your allowlist. Edit `.hermes/kanban-overrides/kanban-config.yaml` directly; schema in `schema/kanban-config.schema.json`. See `plugin/data/references/final-audit-doc-coverage.md`.

### Parallel subagent gate (`subagent_gate`)

**Default on.** Orchestrator runs plan/env/infra checks via Hermes `delegate_task` in parallel, then attestation + prewarm serially. **Serial fallback:** `pre_dispatch_gate.sh` when `enabled: false`, `delegation` toolset missing, parallel timeout (E022), or malformed subagent JSON. Absent `subagent_gate` block in overlay → treated as enabled (`plugin/config_overlay.py`). When parallel is the default path, `kanban_handoff.py` **defers** serial gate at handoff build (`pre_dispatch_gate: DEFERRED`); set `enabled: false` to run serial gate at handoff as before.

```yaml
subagent_gate:
  enabled: true   # set false to force serial gate only
  timeouts:
    plan_gate: 30
    env_gate: 120
    infra_gate: 15
    plan_parse: 60
    cron_setup: 30
```

Blocking/warning severities match serial gate (preflight `fail` = WARN, not block). Full design: `plugin/data/references/parallel-subagent-gate.md`. Sad-path: E022 in `kanban-orchestrator-governance`.

### UI stack (`ui_stack`)

Optional block for **frontend / presentation acceptance** on the operator host. Plugin scripts read it for `kanban_layout_acceptance.sh` and evaluation-chain checks **E028** / **E029** — they never hardcode framework paths or CSS class strings in the bundle.

```yaml
ui_stack:
  framework: react-next   # react-next | vue-nuxt | sveltekit | angular | static
  page_glob: "frontend/app/**/page.tsx"
  motion:
    reduced_query: "prefers-reduced-motion: reduce"
    entry_transition_pattern: "animate-in fade-in|transition-opacity"
  test_command: "cd frontend && npm test --"
```

| Field | Purpose |
| --- | --- |
| `framework` | Host UI stack label (documentation + future tooling) |
| `page_glob` | Route shell files for DOM line-order grep |
| `motion.reduced_query` | Reduced-motion guard pattern |
| `motion.entry_transition_pattern` | Entry transition class grep when Spec mentions fade/slide |
| `test_command` | Optional override for frontend unit tests |

Validate overlay: `python hermes-kanban-advanced-workflow/scripts/validate_config.py .hermes/kanban-overrides/kanban-config.yaml`. Commented examples in `kanban-config.example.yaml` do **not** trigger `ui_stack` validation.

Plans declare **surface slots** and `Acceptance (layout|a11y):` bullets; see `plugin/data/references/frontend-neutrality.md` and `plan-file-format.md` § Acceptance surfaces.

### Plan paths (`plan_search_dirs`)

| Location | Role |
| --- | --- |
| `.hermes/kanban/plans/` | **Canonical SSOT** in the host git repo — hardened plans for decomposition (not `$HERMES_HOME`) |
| IDE-native draft dirs | e.g. host-tool plan folders — draft OK; **Harden** copies into `.hermes/kanban/plans/` |
| `plan_search_dirs` in overlay | Optional extra resolver paths; init re-emits canonical first and preserves extras on re-init |

```yaml
plan_search_dirs:
  - .hermes/kanban/plans
  - custom/plans   # optional
```

**Plan memory `acceptance_matrix`:** After decompose, `.hermes/kanban/memory/{plan_id}.json` stores `acceptance_matrix` from plan frontmatter when present, otherwise parsed from the optimization section (`extract_acceptance_matrix`). Card stamping uses the same loader (`decompose_stamp.load_acceptance_matrix`).

Set `notify_lifecycle: false` or dashboard **Cron → Lifecycle notify** off to skip lifecycle cron provisioning. Set `walk_away_mode: true` or dashboard **Cron → Walk-away mode** on for unattended reconciliation → cleanup → postmortem → completion notify after final audit. Full contract: `plugin/data/references/walk-away-mode.md`. Intervention paging (`kanban-advanced:kanban-notify`) is unchanged.

## Coding agent resolution

The `coding_agent_binary` flows through three layers to the worker:

1. **Init (step 1c)** — user picks from commands **currently on PATH** (numbered list) or types a custom command → written to `kanban-config.yaml` and `.env` as `KANBAN_CODING_AGENT`. Contested shared names (e.g. `agent`) print a symlink conflict notice — see [coding agents](../docs/reference/coding-agents.md) § Binary name collisions.
2. **Init (step 1c-ii)** — user picks model (`auto` or a CLI-specific ID; Cursor: `cursor-agent --list-models` or `agent --list-models`) → `coding_agent_model` in YAML and `KANBAN_CODING_AGENT_MODEL` in `.env`
3. **Worker environment** — gateway loads main-repo `.env` for `KANBAN_CODING_AGENT*`; card worktrees need their own `.env` only if you add it to `.worktreeinclude` ([operator-provisioning.md](../plugin/data/references/operator-provisioning.md))
4. **Worker dispatch** — `scripts/coding_agent_invoke.sh` (or `build_dispatch_argv` in `plugin/coding_agent.py`) applies per-binary headless flags; see [coding agents](../docs/reference/coding-agents.md) and `plugin/data/references/coding-agent-cli-invocation.md`
5. **Dashboard reachability** — `coding_agent_cli.model_reachable` (probe or Save) smokes from project root. Workers re-smoke from each card worktree at Step 3. These are complementary — see dashboard [API.md](../dashboard/API.md).

To change binary or model: use dashboard **Coding Agent** (binary + model row) and **Save**, edit `kanban-config.yaml` / `.env`, or re-run `hermes kanban-advanced init` (preserves existing values unless you override interactively).

## Re-init and branch preservation

`hermes kanban-advanced init` and dashboard **Bootstrap** refresh dispatch profiles (SOUL.md, role-only skills, verification), materialized shared skills, and cron **script files** (not cron jobs — see [[bootstrap]]). Init sets `plan_search_dirs` to `.hermes/kanban/plans` (canonical SSOT). The built-in resolver also searches `.agent/plans`, `.cursor/plans`, and other agent tool dirs for drafts. Optional extra entries in overlay extend resolution. They **do not** reset `working_branch` or `trigger_branch` when `kanban-config.yaml` already exists — values are read from the overlay unless you pass explicit overrides:

```bash
hermes kanban-advanced init --project-root .                    # keeps existing branches
hermes kanban-advanced init --project-root . --working-branch staging  # override integration branch
```

To change branches on an initialized project, prefer dashboard **Save** or edit `kanban-config.yaml` directly. **Working branch** defaults to git upstream / `origin/HEAD` / local `HEAD`, then `main`. **Trigger branch** is optional — leave blank to skip deploy-branch protection.

Optional keys you added manually (e.g. `feature_branch_prefix`, `gateway_timeout_seconds`, **`final_audit_overrides`**) are preserved across re-init.

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

Hermes stores reasoning effort per profile as **`agent.reasoning_effort`** (`none` | `low` | `minimal` | `medium` | `high` | `xhigh`). Default when unset: `medium`. Toggle at runtime in chat with `/reasoning [level]`.

Set the reasoning effort per profile based on its role:

| Profile | Reasoning effort | Rationale |
|---------|------------------|-----------|
| **kanban-advanced-orchestrator** | `high` | Plans, audits, reconciles — needs depth over speed |
| **kanban-advanced-worker** | `medium` | Supervises agents, runs eval chain — balance of speed and accuracy |
| **Coding agent** | model / CLI default | Code generation — speed over depth; the worker verifies output |

Dispatch profiles are created by init with `--no-skills` (no Hermes bundled skills). SOUL and role skills: [[bootstrap]]. Bootstrap seeds orchestrator/worker defaults when `agent.reasoning_effort` is absent.

**Dashboard:** Kanban-Advanced tab → **Profiles** → click a profile → set model and **Reasoning effort** in the modal. See [`docs/reference/dashboard-profile-reasoning.md`](../docs/reference/dashboard-profile-reasoning.md).

**CLI:**
```bash
hermes config set agent.reasoning_effort high --profile kanban-advanced-orchestrator
hermes config set agent.reasoning_effort medium --profile kanban-advanced-worker
```

Example `config.yaml` fragment:
```yaml
agent:
  reasoning_effort: high
model:
  default: <model-name>
  provider: <provider-name>
```

Legacy `model.thinking` is read for display only if present; new writes use `agent.reasoning_effort`.

Coding-agent binary reasoning is separate — configure via model choice or vendor CLI/config, not Hermes profile fields.

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
| `kanban.dispatch_stale_timeout_seconds` | **`0` (disabled)** in many upstream installs — **not** read from `kanban-config.yaml` | Reclaim `running` tasks with no heartbeat for this many seconds. Bootstrap sets **`14400` (4h)**. `0` disables. Rationale: [dispatch-stale-timeout.md](../plugin/data/references/dispatch-stale-timeout.md). |
| `kanban.failure_limit` | `2` | Auto-block after N consecutive non-success attempts (spawn_failed, timed_out, crashed). Built-in circuit-breaker. |
| `kanban.worker_log_rotate_bytes` | `2097152` | Worker log rotation size (2 MiB default). |
| `kanban.worker_log_backup_count` | `1` | Number of rotated worker log backups to keep. |

**Bootstrap** (`hermes kanban-advanced init` / dashboard **Bootstrap**) sets `kanban.auto_decompose=false` and `kanban.dispatch_stale_timeout_seconds=14400` via `hermes config set`. If upstream later ships a non-zero default, re-run init or adjust manually.

Do **not** put `dispatch_stale_timeout_seconds` in `.hermes/kanban-overrides/kanban-config.yaml` — `validate_config.py` rejects unknown overlay keys, and Hermes does not read that file for this setting.

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
