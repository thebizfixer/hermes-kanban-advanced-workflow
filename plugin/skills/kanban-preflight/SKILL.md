---
name: kanban-preflight
description: Environment gating before Kanban decomposition — filesystem coherence, skill provisioning, memory, secrets, API, gateway, profiles, and environment parity.
version: 2.2.0
metadata:
  hermes:
    tags: [kanban, preflight, environment, gating]
    related_skills: [kanban-advanced:kanban-orchestrator, kanban-advanced:kanban-planning]
---

# Kanban Preflight — Environment Gating

> **Skill precedence (mandatory):** When this skill and any project-specific skill (e.g., `sentimentary-dev-environment`) provide conflicting information about profiles, assignees, workspace paths, or dispatch rules, **this skill wins**. Kanban governance rules override project conventions. Specifically:
> - Profile names (`worker`, `orchestrator`) come from `hermes profile list` and `kanban-config.yaml`, NOT from project skill examples or artifact tables.
> - Workspace paths and branch naming come from this skill's decomposition rules, not from project-specific CLI examples.
> - Card body format (`Files:`, `Mode:`, `agent -p` blocks) is enforced by card body policy (P001–P009), not by project documentation.
>
> If you detect a conflict between this skill and a project skill, apply this skill's rule and note the conflict in a `kanban_comment` on the affected card.

Run **after plan optimization** and **before decomposition or dispatch**. Preflight answers one question: is the host ready to burn tokens on a multi-agent board without failing on infrastructure?

The orchestrator must not create cards or dispatch workers until preflight passes (or the operator explicitly accepts a **degraded** result for non-blocking warnings).

## When to run

| Trigger | Who runs it |
| --- | --- |
| Operator says "proceed" / "execute" / "walk away" | Orchestrator |
| Walk-away mode start | Orchestrator (automated) |
| Final audit (optional re-check) | Orchestrator before push |

```bash
# From repo root (${bundle_path} in your overlay)
bash ${bundle_path}/scripts/preflight.sh
# Installed copy: bash scripts/preflight.sh when skills live under ~/.hermes
```

Exit codes: **0** = pass or degraded-only; **1** = blocking failure — stop.

## Preflight checklist (automated in `preflight.sh`)

Run `bash ${bundle_path}/scripts/preflight.sh` from the repository root. Checks include `filesystem_coherence`, `kanban_db_integrity`, memory, secrets, API, gateway, profiles, environment parity, token log, and plan backup.

Each check maps to a JSON `id` in script output. **Blocking** failures halt decomposition; **degraded** warnings may proceed with operator acknowledgment.

### 0. Filesystem coherence (`filesystem_coherence`) — automated

**Goal:** Confirm the working copy is on a single native filesystem. Cross-mount paths (network mounts, OS-translation layers, some shared-folder mounts) cause silent corruption and dual-clone worktree drift.

**Script:** `preflight.sh` `check_filesystem_coherence` blocks `/mnt/*` on Linux/WSL and filesystem types `9p`, `nfs`, `fuse`, etc.

**Dual-clone check (manual):** `git worktree list` — no stale prunable entries from a second clone. See `references/single-coherent-filesystem.md`.

**Env knobs:** `PREFLIGHT_SKIP_FS_CHECK`, `PREFLIGHT_ALLOWED_FS_TYPES` — see `references/preflight-env-knobs.md`.

---

### 0c. Kanban DB integrity (`kanban_db_integrity`) — automated

**Goal:** Verify `$HERMES_HOME/kanban.db` passes `PRAGMA integrity_check` and remove stale `kanban.db.init.lock` if present.

**Typical fixes:** `hermes gateway restart`; see `references/sqlite-kanban-db-recovery.md`.

**Goal:** Confirm that materialized kanban skill files match their canonical sources (public bundle + project overlay). Drift means the agent is running from a hand-edited or stale skill copy.

**Manual verification:**

```bash
# From repo root, with HERMES_PROJECT_OVERLAY set
export HERMES_PROJECT_OVERLAY="${HERMES_PROJECT_OVERLAY:-.hermes/kanban-overrides}"
bash hermes-kanban-advanced-workflow/scripts/provision.sh --check
echo "exit=$?"   # expect: 0
```

**Severity:** Degraded (not blocking) on the first run after cloning a fresh repo if the overlay does not exist yet. Blocking if the overlay exists and `--check` still fails — means materialized skills have drifted.

**Typical fixes:** Re-run `provision.sh` without `--check` to re-materialize. Commit the result. If the overlay directory does not exist at all, set it up per `hermes-kanban-advanced-workflow/README.md` § Adoption Protocol.

---

### 1. Memory budget (`memory_budget`)

**Goal:** Ensure the host has enough RAM for concurrent agent workspaces (default: block below 1024 MB available, warn below 2048 MB).

**Manual verification:**

```bash
# Linux
awk '/^MemAvailable:/ {print $2/1024 " MB"}' /proc/meminfo
# or
free -m | awk '/^Mem:/ {print "available:", $7, "MB"}'
```

**Env knobs:** `PREFLIGHT_MEMORY_MIN_MB` (blocking floor), `PREFLIGHT_MEMORY_WARN_MB` (degraded threshold).

**Typical fixes:** Close heavy IDE/indexer processes; reduce parallel dispatch; run on a machine with more RAM.

---

### 2. Secret availability (`secret_availability`)

**Goal:** Required secrets are present in the environment after sourcing `.env` (repo root). Production additionally requires a `SECRET_KEY` equivalent.

**Manual verification:**

```bash
# After sourcing .env — replace MY_SECRET with your project's required vars
: "${MY_SECRET:?missing}"
# Check the project's .env.example for the authoritative required-secrets list
```

**Env knobs:** `PREFLIGHT_REQUIRED_SECRETS` (comma-separated list of env var names the project requires; default: inspect `kanban-config.yaml` `required_secrets` field if present, otherwise warn and skip).

**Typical fixes:** Copy `.env.example` → `.env` and fill values; for WSL users with `.env` on the Windows side, source it directly before running preflight: `set -a && source /mnt/<drive>/Projects/<project>/.env && set +a`. The `source` command reads env vars safely even from DrvFS paths (no filesystem operations are performed — only variable exports). Do NOT clone or symlink the Windows `.env` into the WSL filesystem. For cloud deploys use Secret Manager mounts — never commit real secrets.

---

### 3. API reachability (`api_reachability`)

**Goal:** If the plan touches a local running API, verify its health endpoint responds with HTTP 2xx within the timeout. **Degraded only** — plans that do not touch a running API may proceed after operator acknowledgment.

**Manual verification:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" --max-time 5 "${PREFLIGHT_API_URL:-http://127.0.0.1:8000/healthz}"
```

**Env knobs:** `PREFLIGHT_API_URL` (set to your project's health endpoint), `CHECK_TIMEOUT`, `PREFLIGHT_SKIP_API=1` (skip with explicit pass note for plans that have no running-API dependency).

**Typical fixes:** Start your local server / Docker Compose stack; fix the port; set `PREFLIGHT_API_URL` for remote dev stacks; use `PREFLIGHT_SKIP_API=1` for docs-only or infra-only plans.

---

### 3b. Hermes version (`hermes_version`, `kanban_goal_flag`)

**Goal:** Hermes Agent **≥ 0.16.0** with kanban per-card goal mode (`--goal` on `hermes kanban create`).

**Automated:** `preflight.sh` parses `hermes --version` and probes `hermes kanban create --help` for `--goal`.

**Typical fixes:** `hermes update` or reinstall `hermes-agent>=0.16.0`; see `references/hermes-v0.15.0-upgrade.md`.

---

### 4. Gateway health (`gateway_health`)

**Goal:** Hermes gateway is running — without it, `hermes kanban dispatch` never claims tasks.

**Manual verification:**

```bash
hermes gateway status
# If down:
hermes gateway run   # tmux or background for persistence
```

**Env knobs:** `CHECK_TIMEOUT` for status probe.

**Typical fixes:** Start gateway in tmux; restart after profile/crash; confirm `hermes` on PATH.

---

### 5. Profile availability (`profile_availability`)

**Goal:** Required Hermes profiles exist, the Cursor/agent CLI works, auth is valid, and orchestrator SOUL.md is not corrupted.

**Manual verification:**

```bash
hermes profile list
agent --version
agent status | grep -q "Logged in"
# SOUL integrity (${worker_profile} path)
grep -qE '%3C|%3E' "${HERMES_HOME}/profiles/${worker_profile}/SOUL.md" \
  && echo "CORRUPT" || echo "clean"
```

**Env knobs:** `PREFLIGHT_PROFILES` (comma-separated; overlay `preflight_profiles` or default `code-worker,orchestrator`).

**Typical fixes:** `hermes profile create …`; `agent login`; restore SOUL.md from backup; remove stale `cursor` shim shadowing `agent` (see autonomy-gaps plan).

---

### 6. Environment parity (`environment_parity`)

**Goal:** The active `ENVIRONMENT` value matches the deployment target (e.g. `local`, `dev`, `production`). Local is not accidentally pointed at production data; production is not using localhost URLs.

**Manual verification:**

```bash
echo "ENVIRONMENT=${ENVIRONMENT:-unset}"
# Basic smell test: local env pointed at prod-named DB URI
[[ "${ENVIRONMENT:-local}" != "local" || -z "${DB_URI:-}" ]] \
  || printf '%s' "$DB_URI" | grep -qiE 'prod|production' && echo "WARN: local env with prod-like DB URI"
```

**Env knobs:** `PREFLIGHT_ALLOWED_ENVIRONMENTS` (comma-separated; default `local,dev,production`). Any value outside this list is a blocking failure.

**Typical fixes:** Set `ENVIRONMENT=local` for laptop work; align your data store URI with the target environment; ensure `PUBLIC_APP_URL` matches deployment target.

---

## Output format

`preflight.sh` prints a single JSON object to stdout (human-readable logs go to stderr only if you wrap the script — default is JSON-only on stdout).

```json
{
  "status": "pass | degraded | fail",
  "timestamp": "2026-05-21T12:00:00Z",
  "environment": "local",
  "repo_root": "/path/to/repo",
  "blocking_failures": 0,
  "degraded_warnings": 1,
  "checks": [
    {
      "id": "memory_budget",
      "status": "pass | degraded | fail",
      "severity": "blocking | degraded",
      "message": "human-readable detail"
    }
  ]
}
```

| `status` | Orchestrator action |
| --- | --- |
| `pass` | Present results at user gate; proceed when operator says go |
| `degraded` | Present warnings; proceed only if plan does not need failed checks (e.g. API down but docs-only plan) |
| `fail` | **Stop.** Do not decompose, dispatch, or enter walk-away mode |

Parse example:

```bash
result=$(bash hermes-kanban-advanced-workflow/scripts/preflight.sh)
echo "$result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['status'], d['blocking_failures'])"
```

## Orchestrator integration

Insert as **Step 0b** in decomposition choreography (between plan optimization and user gate / card creation):

1. Run `bash hermes-kanban-advanced-workflow/scripts/preflight.sh`.
2. If `fail` → report blocking checks, fix environment, re-run.
3. If `degraded` → list warnings; require explicit operator OK for walk-away.
4. If `pass` → include summary in "Plan optimized and preflight passed" message at user gate.

Use **`${bundle_path}/scripts/preflight.sh`** as the single pre-dispatch gate. If your application has a lighter project-specific env script, run it **in addition to** (not instead of) this bundle preflight — do not skip filesystem, DB, profile, or gateway checks defined here.

## Pitfalls

- **Skipping preflight after plan edits.** Environment drifts (gateway died, agent logged out) while the plan sat in review. Re-run preflight every time the operator says "go," not only once at plan creation.
- **Treating degraded as pass silently.** API down + extraction plan = wasted board. Always surface degraded checks and tie them to plan scope.
- **Wrong repo root.** Script walks up from `hermes-kanban-advanced-workflow/scripts/` for `.env` / `.git`. Running from a path without `.env` yields false secret failures — run from repo root or export vars explicitly.
- **Stale profile list.** `PREFLIGHT_PROFILES` must match profiles you will assign in card bodies. Default names are examples; discover with `hermes profile list` and export overrides before walk-away.
- **Blocking on API for docs-only plans.** Use `PREFLIGHT_SKIP_API=1` or accept degraded with operator acknowledgment — do not hack the script to always pass.
- **Working copy on a cross-mount path.** Check 0 (`filesystem_coherence`) blocks known cross-mount prefixes and filesystem types. Clone to a native path and re-run. See `docs/examples/cross-mount-filesystems.md`.
- **Skill provisioning drift.** Check 0b (`skill_provisioning`) failing means materialized skill files have been hand-edited or the overlay changed without re-provisioning. Run `provision.sh` and commit before proceeding.
- **Production without a secret key.** The app must fail loud at startup — preflight blocks early instead of mid-board failures.
- **SOUL.md corruption.** HTML entities or unexpected markup in SOUL.md produce nonsense card bodies; profile check blocks until restored.
- **Gateway up but dispatcher wedged.** `gateway status` succeeding does not replace `hermes kanban watch` / cron monitoring during execution — preflight is pre-flight only.

## Cross-references

- Script: `hermes-kanban-advanced-workflow/scripts/preflight.sh`
- Orchestrator: `kanban-advanced:kanban-orchestrator` Step 0 user gate + Step 0b preflight
- Prompt: `hermes-kanban-advanced-workflow/prompts/orchestrator.md` § Preflight gating
- Bundle documentation audit: [`references/bundle-documentation-audit.md`](references/bundle-documentation-audit.md) — README vs file tree drift detection, distinct from `provision.sh --check`
- Filesystem coherence detection: [`references/filesystem-coherence-detection.md`](references/filesystem-coherence-detection.md) — canonical shell patterns for cross-mount detection (path-prefix blocklist, `df -T` FS type, config overrides)
- Preflight env knobs: [`references/preflight-env-knobs.md`](references/preflight-env-knobs.md) — quick-reference table of all env vars that control preflight behavior
- WSL `.env` sourcing: [`references/wsl-env-sourcing.md`](references/wsl-env-sourcing.md) — sourcing `.env` from Windows side when the WSL repo lacks its own copy
