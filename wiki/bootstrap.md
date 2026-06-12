# Bootstrap & Init — Dispatch Profiles

> **For the agent:** When a user asks about `hermes kanban-advanced init`, dashboard **Bootstrap**, profile creation, `SOUL.md`, skill isolation, `HERMES_HOME`, or why dispatch profiles still have default Hermes skills — answer from this page.

Bootstrap and init are the **same operation** from two entry points:

| Entry | Command / action |
| --- | --- |
| CLI | `hermes kanban-advanced init --project-root <repo> [--working-branch <branch>] [--force]` |
| Dashboard | **Kanban-Advanced** tab → **Bootstrap** → `POST /api/plugins/kanban-advanced/init` |

**Save** (`POST /save`) and **Update Plugin** (`POST /update`) also call profile reconciliation — see [Re-run behavior](#re-run-behavior).

---

## What init does (ordered)

1. **Resolve `HERMES_HOME`** — log the path used for all subprocess and filesystem work (see [HERMES_HOME resolution](#hermes_home-resolution)).
2. **Ensure dispatch profiles** — create or rename to prefixed names (see [Profile names](#dispatch-profile-names)).
3. **Model config** — copy default model/provider into dispatch profiles when missing.
4. **Orchestrator `max_turns`** — set to 180 (dashboard/CLI) when below threshold.
5. **Coding agent binary** (step 1c) — pick headless CLI on PATH → `coding_agent_binary` + `KANBAN_CODING_AGENT`.
6. **Coding agent model** (step 1c-ii) — pick `auto` or a CLI model ID → `coding_agent_model` + `KANBAN_CODING_AGENT_MODEL`. Cursor: `agent --list-models`. Runs smoke via `build_smoke_argv` when binary is on PATH (same flags as `scripts/coding_agent_invoke.sh smoke`). Workers re-smoke from each worktree at card flight.
7. **Config overlay** — write `.hermes/kanban-overrides/kanban-config.yaml` (preserves existing branches and coding-agent model on re-init unless overridden).
8. **Materialize shared skills** — copy all 11 plugin skills to `$HERMES_HOME/skills/kanban-advanced/` (discoverable from any profile via `<available_skills>`).
9. **Reconcile dispatch profiles** — SOUL.md, role-only profile skills, verification (see [Profile reconciliation](#profile-reconciliation)).
10. **Cron scripts (files only)** — `auto_unblock.sh`, `board_keeper.sh`, `token_tracker.py` → `$HERMES_HOME/scripts/`. Does **not** create Hermes cron **jobs** — those are per-plan at decomposition (`provision_kanban_crons.sh --create`).
11. **Environment** — `HERMES_ENABLE_PROJECT_PLUGINS=true`, `KANBAN_CODING_AGENT`, `KANBAN_CODING_AGENT_MODEL`, `KANBAN_POLICY_PROFILE`, and **`HOME=`** (for coding-agent credential paths) in project `.env`.
12. **`.worktreeinclude`** — repo-root file listing gitignored paths copied into each card worktree by `worktree_setup.sh` (`.hermes/scripts/`, `kanban-overrides/`, plugin invoke helpers when using project-local `.hermes`). Commit this file after init.
13. **Gateway check** — report running/stopped.

Init **fails loudly** if profile reconciliation/verification does not pass (dashboard returns `"error": "Profile reconciliation/verification failed"`).

---

## Coding-agent auth during bootstrap (limitations)

Bootstrap **tests** the configured headless CLI once; it does **not** fully provision auth for you.

| Bootstrap does | Bootstrap does **not** |
| --- | --- |
| Pick `coding_agent_binary` + model | Write `GROK_API_KEY`, `ANTHROPIC_API_KEY`, etc. to `.env` |
| Run **advisory** smoke (`say ok` headless) when binary is on PATH | **Block** init if smoke fails — logs `! coding CLI auth/model check failed` instead |
| Write `HOME=` to `.env` | Force gateway systemd to pass `HOME` (may need unit `Environment=`) |
| Write `KANBAN_CODING_AGENT*` to `.env` | Replace **pre-dispatch** / preflight gate before decomposition |

**Supported operator model:** API key in `.env` **or** OAuth/login on the gateway host (`agent login`, `claude login`, …). See [`plugin/data/references/coding-agent-auth.md`](../plugin/data/references/coding-agent-auth.md).

**Blocking enforcement** happens later:

1. `preflight.sh` → `coding_agent_cli_reachability`
2. `pre_dispatch_gate.sh` → `check_coding_agent_cli.py`
3. Worker Step 3 → `coding_agent_invoke.sh smoke` from each worktree

### Agent: user says "bootstrap passed but workers can't auth"

1. Explain bootstrap smoke is **advisory** — decomposition requires preflight/gate.
2. Load `plugin/data/references/coding-agent-auth.md` and run `check_coding_agent_cli.py` (not only dashboard status).
3. Check `HOME` in gateway worker env (`HOME: unbound variable` is a common false OAuth).
4. After fix: `rm -f .hermes/kanban/preflight_cache.json`, `hermes gateway restart`, re-run preflight.

Full symptom matrix: [troubleshooting.md](troubleshooting.md) (coding-agent sections).

---

## Operator provisioning (beyond plugin init)

Init provisions **kanban infrastructure** — not your application runtime. See [`plugin/data/references/operator-provisioning.md`](../plugin/data/references/operator-provisioning.md) (SSOT).

| Init provides | Operator must add (typical) |
| --- | --- |
| `.worktreeinclude` kanban paths (overlay, memory, invoke scripts) | **`.env`** in `.worktreeinclude` when cards/tests read secrets from cwd |
| `KANBAN_CODING_AGENT*`, `HOME`, policy profile in main `.env` | Vendor API keys, `MONGODB_URI`, `SECRET_KEY`, `required_secrets` vars |
| Advisory coding-agent smoke | OAuth login on gateway host **or** API keys in `.env` |
| Materialized scripts under `$HERMES_HOME` | **`.venv/`**, **`node_modules/`** in `.worktreeinclude` if worktree tests need them |

**Agent:** Interview the user about coding agent binary, auth model, and whether worktree cards run `pytest` / `npm test` / DB-backed tests — then recommend `.env` and `.worktreeinclude` lines they add themselves. Commit `.worktreeinclude` after init.

---

## Dispatch profile names

| Role | Canonical name | Legacy name (auto-renamed on init) |
| --- | --- | --- |
| Orchestrator | `kanban-advanced-orchestrator` | `orchestrator` |
| Worker | `kanban-advanced-worker` | `worker` |

Names are stored in `kanban-config.yaml` as `orchestrator_profile` and `worker_profile`. Card `assignee` fields and the dispatcher must use these exact names.

**Do not** manually `hermes profile create … --clone` for dispatch profiles — init uses `--no-skills` and manages SOUL/skills itself.

---

## Profile creation (`--no-skills`, not `--clone`)

Hermes `profile create --clone` copies **config, SOUL, and the full default skill tree** into the new profile. That breaks kanban-advanced: workers would load stale built-in skills instead of plugin skills.

Init instead runs:

```bash
hermes profile create <name> --no-skills
```

Then:

- Copies **only** `config.yaml` and `.env` from the default profile (model/auth) — **not** SOUL, **not** skills.
- Writes **`.no-bundled-skills`** in the profile home so `hermes update` does not re-inject Hermes bundled skills.
- Removes any empty `skills/` dir Hermes may leave behind.
- Seeds role-specific content in the reconciliation step (below).

`--no-skills` and `--clone` are **mutually exclusive** in Hermes CLI.

---

## Profile reconciliation

Implemented in `plugin/profile_bootstrap.py` → `reconcile_dispatch_profiles()`.

For each dispatch profile:

### 1. SOUL.md

Source (installed plugin checkout):

| Profile | Prompt file |
| --- | --- |
| `kanban-advanced-worker` | `plugin/data/prompts/worker.md` |
| `kanban-advanced-orchestrator` | `plugin/data/prompts/orchestrator.md` |

Destination: `<profile-home>/SOUL.md` (profile home resolved from `hermes profile show <name>` → `Path:` line).

SOUL opens with `# Worker Prompt` or `# Orchestrator Prompt` after a successful bootstrap.

### 2. Role-only skills (profile-local)

Wipes `<profile-home>/skills/` completely, then copies **only** these plugin skills:

| Profile | Skill count | Skills |
| --- | ---: | --- |
| `kanban-advanced-worker` | 2 | `kanban-worker`, `kanban-worker-governance` |
| `kanban-advanced-orchestrator` | 9 | `kanban-advanced`, `kanban-cleanup`, `kanban-notify`, `kanban-orchestrator`, `kanban-orchestrator-governance`, `kanban-planning`, `kanban-postmortem`, `kanban-preflight`, `kanban-reconciliation` |

Each skill is a directory with `SKILL.md` copied from `plugin/skills/<name>/SKILL.md` in the **installed plugin** (`$HERMES_HOME/plugins/kanban-advanced/`), not from a random dev checkout unless that is the install path.

### 3. Verification

After seeding, init verifies:

- Profile exists in `hermes profile list` under the prefixed name.
- `.no-bundled-skills` marker present.
- `SOUL.md` present.
- `skills/` contains **exactly** the role's allowed set (no extra dirs like `devops`, `github`, etc.).

On failure: log issues, reseed once, re-verify. Still failing → init returns error.

Bootstrap output includes the **resolved profile path** on SOUL/skills lines, e.g.:

```text
OK kanban-advanced-worker: SOUL.md <- worker.md (/path/to/.hermes/profiles/kanban-advanced-worker)
OK kanban-advanced-worker: 2 skills seeded [...] (/path/to/.hermes/profiles/kanban-advanced-worker)
OK Profiles verified: kanban-advanced-worker, kanban-advanced-orchestrator (role skills only)
```

---

## Two skill locations (do not confuse)

| Location | Contents | Who sees it |
| --- | --- | --- |
| `$HERMES_HOME/skills/kanban-advanced/` | All 11 plugin skills (materialized at init) | Every profile — `<available_skills>` index |
| `$HERMES_HOME/profiles/<dispatch-profile>/skills/` | Role-only subset (2 or 9) | That profile when dispatched |

Dispatch profiles must **not** inherit Hermes bundled skills in their profile-local `skills/` tree. The shared materialized tree is intentional for `skill_view()` discovery.

---

## `HERMES_HOME` resolution

Python (`resolve_hermes_home()` in `plugin/config_overlay.py`) and init subprocesses use the same order:

1. `hermes_constants.get_hermes_home()` — when running inside Hermes Agent (gateway, dashboard).
2. `$HERMES_HOME` or `$HERMES_STATE_DIR` environment variable.
3. `<project-root>/.hermes` — **only if that directory already exists** (project-scoped plugins).
4. `%LOCALAPPDATA%/hermes` — Windows native default.
5. `~/.hermes` — global fallback.

**Vanilla global install:** steps 1–2 usually resolve to `~/.hermes` or `%LOCALAPPDATA%/hermes`. Step 3 applies only when the project already has a `.hermes` directory.

**Profile home path:** never guessed only from `$HERMES_HOME/profiles/<name>`. Seeding uses `hermes profile show <name>` → `Path:` as authoritative. This prevents creating profiles in one home and seeding another.

Init logs `HERMES_HOME: …` at the start — the path you inspect on disk must match.

---

## Re-run behavior

| Action | Profiles | Branches in overlay | Profile SOUL/skills |
| --- | --- | --- | --- |
| **Bootstrap / init** | ensure + reconcile | preserved unless `--working-branch` override | re-seeded + verified |
| **Save** | reconcile | updated from form | re-seeded + verified |
| **Update Plugin** | reconcile after git pull | unchanged | re-seeded + verified |

Re-init is **safe** for fixing drift (legacy names, extra skills, wrong SOUL). It does **not** replace **Save** for changing `working_branch` — use **Save** or edit `kanban-config.yaml`.

---

## Verify on disk (after bootstrap)

```bash
# 1. Confirm home
hermes profile show kanban-advanced-worker | grep -E '^(Profile|Path|Skills):'
hermes profile show kanban-advanced-orchestrator | grep -E '^(Profile|Path|Skills):'
# Skills: should be 2 and 9 respectively

# 2. Worker profile home
WP=$(hermes profile show kanban-advanced-worker | awk '/^Path:/ {print $2}')
ls "$WP/skills"                    # exactly: kanban-worker  kanban-worker-governance
test -f "$WP/.no-bundled-skills"
head -1 "$WP/SOUL.md"              # # Worker Prompt

# 3. Orchestrator profile home
OP=$(hermes profile show kanban-advanced-orchestrator | awk '/^Path:/ {print $2}')
ls "$OP/skills" | wc -l            # 9
head -1 "$OP/SOUL.md"              # # Orchestrator Prompt
```

---

## Troubleshooting

### Profiles still have default Hermes skills (devops, github, …) or generic SOUL

**Symptoms:** `hermes profile show` reports Skills: 90+; `SOUL.md` is not the Worker/Orchestrator Prompt; disk `skills/` has many non-kanban dirs.

**Causes:**

1. **Bootstrap not run** after plugin update — run **Bootstrap** or `hermes kanban-advanced init --force`.
2. **Wrong `HERMES_HOME`** — init logged a different home than where you are inspecting. Compare bootstrap `HERMES_HOME:` line with `echo $HERMES_HOME` in the shell where you list files.
3. **Legacy manual `profile create --clone`** — delete dispatch profiles and re-run bootstrap (init uses `--no-skills`).
4. **Stale plugin code** — **Update Plugin**, restart gateway + dashboard, bootstrap again.
5. **WSL vs Windows split** — separate `$HERMES_HOME` trees; fix in the environment where the gateway runs.

**Fix:** Delete `kanban-advanced-worker` and `kanban-advanced-orchestrator` (`hermes profile delete <name> -y`), run bootstrap, confirm verification lines in output.

### Init succeeds but dashboard shows wrong profile names

Status API returns `dispatch_profiles` with configured names. Red "not found" means Hermes `profile list` lacks those names — re-run bootstrap.

### `Profile reconciliation/verification failed`

Read the listed issues in bootstrap output. Common: prompts missing at install path (`plugin/data/prompts/`), skills bundle missing, profile home not resolvable.

### Deleting profile in dashboard does not remove files

Hermes dashboard delete may not remove the profile directory on disk. Use `hermes profile delete <name> -y` and re-bootstrap.

---

## Related pages

- [[setup]] — full install path
- [[configuration]] — overlay variables, thinking levels, `preflight_profiles`
- [[troubleshooting]] — error codes and branch preservation
- `plugin/data/references/hermes-state-directory.md` — `$HERMES_HOME` layout
- `dashboard/API.md` — bootstrap API request/response
