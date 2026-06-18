# Troubleshooting

> **For the agent:** When a user reports a failure, match the symptom to the error code below. Every error maps to a recovery action in [[governance]].

## In-flight quick router

| Symptom keyword | Layer | Tier | Belt | First load |
|-----------------|-------|------|------|------------|
| goal_card / attestation | L0 | T2 | MBB | Index L0 → `verify_goal_cards.py` |
| preflight / gate FAIL | L1–L2 | T2 | MBB | Index L1–L2 → `pre_dispatch_gate.sh` |
| handoff stuck / exit 2–4 | L3 | T2/T3 | MBB | Index L3 → [[decomposition-workflow]] § handoff |
| scratch / crons / validate | L4 | T2 | MBB | Index L4 |
| E021 / exit 127 / auth smoke | L5-pre/L5 | T1→T3 | BB | Index L5 → `worktree_setup.sh` / invoke smoke |
| delegation / stale skill | L5 | T1/T2 | BB/MBB | Index L5 → [[#Stale skills / plugin updated mid-kanban execution]] |
| install / bootstrap / Update Plugin | — | T1–T2 | BB/MBB | [[plugin-verification]] |
| E001–E020 DENY | L6 | T1 | BB | worker-governance → `kanban_recover.py --list` |

**SSOT commands:** `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")`. Hub: [[in-flight-navigation]].

## Quick diagnosis

```bash
# Check overall board health
hermes kanban list

# See what blocked a card
hermes kanban show <task_id>

# Run recovery
python hermes-kanban-advanced-workflow/scripts/kanban_recover.py --list
python hermes-kanban-advanced-workflow/scripts/kanban_recover.py <task_id> <error_code>
```

## Common failures

### Handoff card stuck in `ready` (`Decompose: <plan_id>`)

**Symptom:** Handoff card stays `ready`; no orchestrator session starts.

**Checklist:**

1. `hermes config show` — `kanban.dispatch_in_gateway` must be `true`.
2. Card `assignee` must match `orchestrator_profile` in `.hermes/kanban-overrides/kanban-config.yaml`.
3. Gateway running: `hermes gateway status` (restart gateway after plugin Update Plugin).
4. Duplicate open handoff for same `plan_id` — `hermes kanban list` (idempotent reuse is OK).
5. Card created with `--allow-offline` — dispatcher was down; start gateway and wait for claim.

Handoff cards are intentionally `ready` without block (wave-0 dispatch). Stuck `ready` is dispatcher/config, not a missing block.

### Worktree incomplete (E021)

**Symptom:** Worker blocks with `E021_WORKTREE_INCOMPLETE: missing kanban scripts` before smoke.

**Fix:** Re-run governed bootstrap — do **not** use raw `git worktree add`:

```bash
bash <bundle>/scripts/worktree_setup.sh --task-id <task_id> --repo-root <repo_root>
```

Confirm `.worktreeinclude` lists kanban script paths and worktree has `.hermes/scripts/coding_agent_invoke.sh`.

### Layout / presentation acceptance (E028 / E029)

**Symptom:** Worker or evaluation chain blocks with `E028`, `layout_acceptance_failed`, or `E029` / `presentation_a11y_acceptance_failed`.

**Fix:**

1. Open the card body's `Acceptance (layout):` / `Acceptance (a11y):` bullets — they must be grep-verifiable against the route shell (`ui_stack.page_glob` in `.hermes/kanban-overrides/kanban-config.yaml`).
2. For DOM order: confirm `line(anchor_before) < line(anchor_after)` in the route shell source.
3. For motion: confirm entry transition classes match `ui_stack.motion.entry_transition_pattern` and a `prefers-reduced-motion` (or overlay `reduced_query`) guard exists.
4. Re-run locally:
   ```bash
   bash hermes-kanban-advanced-workflow/scripts/kanban_layout_acceptance.sh \
     --workspace . --card-body-file /tmp/card-body.md
   ```

See `plugin/data/references/frontend-neutrality.md`.

### verification-deploy without attestation

**Symptom:** `verification_deploy_requires_attestation` or final audit `verification_deploy_unattested`.

**Fix:** Orchestrator writes attestation JSON before completing the card:

```text
.hermes/kanban/card-attestations/{plan_id}-{card_key}.json
```

Minimum: `plan_id`, `card_key`, `attested_at`, `operator`, `evidence`. Session `attestation.yaml` does **not** satisfy this gate. See `wiki/governance.md` § Card attestation.

### "Profile has no config.yaml" (PR001)

**Symptom:** Worker fails with HTTP 401. Preflight §5 shows `FAIL: <profile> has no config.yaml`.

**Fix:**
```bash
DIR=$(hermes profile show <profile> | grep "Path:" | awk '{print $2}')
cp $HERMES_HOME/config.yaml "$DIR/config.yaml"
cp $HERMES_HOME/.env "$DIR/.env"
```

### "Attestation missing" (A001)

**Symptom:** Orchestrator refuses to decompose.

**Fix:**
```bash
bash hermes-kanban-advanced-workflow/scripts/preflight.sh > /tmp/preflight.json
python hermes-kanban-advanced-workflow/scripts/kanban_attestation.py <plan_id> --preflight-result /tmp/preflight.json
```

### "Card blocked by policy" (P001/P002/P003)

**Symptom:** Card in `blocked` state with `P00x` error.

**Fix:** Edit the card body to include the missing field (`Files:`, `agent -p` block, or `Mode:`). Re-run card policy.

### "Evaluation chain DENY" (E001-E006, E018, E020)

**Symptom:** Worker completed agent run but task blocked with `E00x`.

**Fix:** See the specific error:
- E001: Agent missed a file in the current diff. If work was already committed (re-run, salvage, or rebase), the chain should ALLOW via `find_prior_commit` (searches up to 64 commits). If you still see E001 with a matching commit in `git log`, update plugin and re-run eval chain.
- E002: Agent modified unlisted files (auto-reverted). Add files to `Files:` if intentional.
- E003: Tests failed. Review diff, fix code, re-run agent.
- E004: Commit message mismatch. Amend commit or update `Commit:` line.
- E005: Token log missing. Run `scripts/token_tracker.py` manually.
- E006: Zero output. Check workspace type (must be `worktree`, not `scratch`).
- E018: Token log missing exact agent attribution. Capture coding-agent stdout and log with `source=agent`.
- E020: Agent output not captured or smoke failed. See **Coding agent smoke failed** below.

### Stale skills / plugin updated mid-kanban execution

**Symptom:** Workers still run old smoke commands (missing `--trust`, wrong `coding_agent_invoke.sh` path, or direct coding instead of delegation). Materialized skill at `$HERMES_HOME/skills/kanban-advanced/kanban-worker/SKILL.md` does not match plugin source. `provision.sh --check` reports drift.

**Root cause:** Bootstrap or **Update Plugin** was run while cards were in flight, or only the git checkout was updated without rematerializing skills/scripts. Workers load profile skills from disk — stale copies persist until reprovisioned.

**Also check `scripts/lib/`:** `coding_agent_invoke.sh` and `worktree_setup.sh` source helpers from `$HERMES_HOME/scripts/lib/` (`coding_agent_env.sh`, `coding_agent_auth_lock.sh`, `kanban_bundle.sh`, `worktree_include.sh`, `kanban_config.sh`, …). Older plugin versions materialized only top-level scripts, causing exit 127 in workers. **Update Plugin**, `hermes kanban-advanced init`, or `provision.sh` sync the full list in `plugin/script_materialize.py`.

**Worktree provisioning (`.worktreeinclude`):** Card worktrees under `/tmp/wt-*` only contain tracked git files. Init merges **kanban** paths into `.worktreeinclude` (overlay, memory, invoke scripts). **Application** paths (`.env`, `.venv/`, `node_modules/`) are **operator responsibility** — add them yourself based on what cards run. See [operator-provisioning.md](../plugin/data/references/operator-provisioning.md). Symptom: worker resolves `bundle_path` from overlay yaml but `coding_agent_invoke.sh` or `kanban-config.yaml` is missing inside the worktree → exit 127. **Chicken-and-egg:** `worktree_setup.sh` must be invoked from `$HERMES_HOME/scripts/` or the main repo bundle — not a cwd-relative path inside an empty worktree. Fix: re-run **Bootstrap** / `hermes kanban-advanced init`, commit `.worktreeinclude`, **Update Plugin**, restart gateway.

**Fix (reset provisioning — pause dispatch first):**

```bash
# 1. Pause / block new work if a plan is active
hermes kanban list

# 2. Dashboard: Update Plugin → Bootstrap (or Save)
#    CLI equivalent after pull:
hermes kanban-advanced init --project-root .

# 3. Re-materialize project skills tree (if skills_output_path is set)
bash hermes-kanban-advanced-workflow/scripts/provision.sh
bash hermes-kanban-advanced-workflow/scripts/provision.sh --check

# 4. Restart gateway so workers reload skills
hermes gateway restart

# 5. Verify materialized worker skill
grep -E 'coding_agent_invoke|terminal\(\)' \
  "$HERMES_HOME/skills/kanban-advanced/kanban-worker/SKILL.md"
```

Also confirm the worker profile loads **plugin** skills (`kanban-git`, `kanban-worker`, `kanban-worker-governance` from profile-local `skills/` — sourced from the installed plugin), not the built-in `devops/kanban-worker` copy. `hermes profile show kanban-advanced-worker | grep Skills:` should list only role skills (count **3**), with content from the materialized plugin tree.

**In-flight index:** Workers and orchestrators should load `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")` for symptom-keyed recovery (delegation, stale skill, E021, scratch workspace). Operator regression pass: `plugin/data/references/handoff-regression-checklist.md`.

### Bootstrap passed but coding-agent auth fails at execute

**Symptom:** User says init or dashboard **Bootstrap** succeeded, but preflight, `pre_dispatch_gate.sh`, or workers block with `[escalation:coding_agent:auth]` or `coding_agent_cli_reachability` failure.

**Root cause:** Bootstrap runs **advisory** smoke — it logs `! coding CLI auth/model check failed` but does not fail init. Bootstrap also does **not** write vendor API keys (`GROK_API_KEY`, `ANTHROPIC_API_KEY`, …). Decomposition requires preflight/gate smoke to pass.

**Fix:**

```bash
# 1. Confirm binary + HOME
grep -E '^(KANBAN_CODING_AGENT|HOME)=' .env

# 2. Add missing API key OR run vendor login on gateway host (agent login, claude login, …)

# 3. Blocking smoke (same as gate)
PYTHONPATH=. python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py

# 4. Invalidate stale preflight cache
rm -f .hermes/kanban/preflight_cache.json
hermes gateway restart
```

SSOT: `plugin/data/references/coding-agent-auth.md`. Agent playbook: `AGENTS.md` § *When a user has coding-binary auth trouble*.

### Dashboard profile yellow ("model unreachable") vs coding-agent auth

**Symptom:** Kanban-Advanced dashboard **Profiles** row shows yellow **model unreachable** (optionally `provider auth failed` or `model not found`) on worker/orchestrator. Operator reads this as "Cursor auth failed."

**Root cause:** Two separate probes:

| Dashboard row | Check | Fix |
| --- | --- | --- |
| **Profiles** (orchestrator / worker) | Hermes LLM ping (`hermes -p <profile> chat -q "say ok"`) | `hermes auth add <provider>` or fix profile `model.default` in `config.yaml` |
| **Coding agent** | Headless CLI smoke (`check_coding_agent_cli.py`) | `agent login`, `HOME=` in `.env`, API keys — [coding-agent auth](../plugin/data/references/coding-agent-auth.md) |

Preflight mirrors the same split: `model_reachability` (Hermes profiles) and `coding_agent_cli_reachability` (external binary). `profile_availability` no longer uses `agent status | grep "Logged in"`.

**Fix (Hermes provider):**

```bash
hermes -p kanban-advanced-worker config show   # confirm model + provider
hermes auth add nous                           # example — use your provider
hermes -p kanban-advanced-worker chat -q "say ok"
```

Refresh dashboard with probe enabled (`GET .../status?probe=1`).

### Preflight / handoff hangs on coding-agent CLI smoke

**Symptom:** `kanban_handoff.py` or `pre_dispatch_gate.sh` stalls at `check_coding_agent_cli.py` when Cursor `agent` is installed but headless auth is broken or hangs.

**Fix:**

```bash
# Diagnose (fast mode — 15s default)
PYTHONPATH=. python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py

# Slow cold start
PREFLIGHT_CODING_AGENT_PROBE_TIMEOUT=120 python3 .../check_coding_agent_cli.py
# or
PYTHONPATH=. python3 .../check_coding_agent_cli.py --full
```

**Audit-noted skip** (decomposition only — fix auth before execute):

```bash
export PREFLIGHT_SKIP_CODING_AGENT_CLI=1
python3 hermes-kanban-advanced-workflow/scripts/kanban_handoff.py --plan ...
```

Handoff and preflight failure messages include this hint when a timeout is detected.

### "Coding agent smoke failed" / E020 / `Workspace Trust Required`

**Symptom:** Worker blocks at Step 3 or E020. Dashboard **Coding Agent** dot may still be green. Cursor stderr shows `Workspace Trust Required`, or smoke exits non-zero from the worktree.

**Root causes:**

1. **Worktree trust** — Dashboard smoke runs from project root; workers smoke from each card worktree. Cursor headless calls need `-p --output-format json --trust`. `worktree_setup.sh` pre-provisions trust files; the invoke script still passes `--trust` every time.
2. **Wrong binary or model** — `KANBAN_CODING_AGENT` / `KANBAN_CODING_AGENT_MODEL` out of sync with `kanban-config.yaml` or `.env`. Re-run dashboard **Save** or fix `.env`.
3. **OAuth / API key** — Cursor uses `~/.config/cursor/auth.json`, not `CURSOR_API_KEY`. Grok needs `GROK_API_KEY`.

**Fix:**

```bash
cd <worktree-path>
export KANBAN_CODING_AGENT=agent   # or your binary
export KANBAN_CODING_AGENT_MODEL=auto
bash hermes-kanban-advanced-workflow/scripts/coding_agent_invoke.sh smoke
```

Per-binary flags: `plugin/data/references/coding-agent-cli-invocation.md`. Do **not** grep worker logs for `[unauthenticated]` — that is the Cursor indexing service, not the agent.

**Prevention:** Step 3 uses `coding_agent_invoke.sh smoke` after `worktree_setup.sh`. Preflight cache (< 30 min) can skip smoke on Step 2 fast path — if auth changed, delete `.hermes/kanban/preflight_cache.json` or wait for expiry.

### `HOME: unbound variable` / false "OAuth required" (gateway workers)

**Symptom:** Worker blocks with `[escalation:coding_agent:auth]` or smoke exit 1. Cursor stderr shows `HOME: unbound variable`. `agent status` may still report logged in when run from an interactive shell with `HOME` set.

**Root cause:** Gateway systemd units with `SetLoginEnvironment=no` often do not pass `HOME` to worker processes. Cursor's `agent` wrapper uses `set -u` and reads `${HOME}/.config/cursor/auth.json` — without `HOME`, the binary crashes before OAuth is consulted.

**Fix:**

```bash
# Persist HOME for the project (init/Save does this automatically on latest plugin)
grep '^HOME=' .env || echo "HOME=$HOME" >> .env
# Or in gateway unit: Environment="HOME=/home/youruser"
hermes gateway restart
rm -f .hermes/kanban/preflight_cache.json
PYTHONPATH=. python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py
```

See `plugin/data/references/coding-agent-auth.md` for per-binary credential paths.

### Cursor OAuth expired (`agent status` OK, smoke fails)

**Symptom:** `agent status` reports logged in, but `agent -p "say ok" --trust` fails with `Authentication required`, times out, or hangs. Preflight / `pre_dispatch_gate.sh` blocks on `coding_agent_cli_reachability`. Workers tag `[escalation:coding_agent:auth]` — not a protocol violation.

**Why:** Cursor CLI uses OAuth in `~/.config/cursor/auth.json`. Tokens expire (~9+ days). `agent status` only checks that the file exists / looks logged in; it does **not** prove headless execution works. `CURSOR_API_KEY` does **not** authenticate the CLI.

**Diagnose (gateway host / WSL):**

```bash
agent status
agent -p "say ok" --trust
PYTHONPATH=. python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py
bash hermes-kanban-advanced-workflow/scripts/preflight.sh | python3 -m json.tool
```

**Fix (operator):**

```bash
agent login                    # interactive OAuth refresh
rm -f .hermes/kanban/preflight_cache.json
# Dashboard: Update Plugin → Bootstrap (or provision.sh) → hermes gateway restart
bash hermes-kanban-advanced-workflow/scripts/pre_dispatch_gate.sh <plan_id>
```

**Alternative:** Switch `coding_agent_binary` to another authenticated CLI (Claude, Codex, …) via dashboard **Save** if Cursor auth cannot be refreshed on that host.

### Symlink conflict on configured coding binary

**Symptom:** Init, dashboard **Save** / **Bootstrap**, or status shows `symlink conflict: two or more binaries are configured with the same command` (common when `coding_agent_binary` is `agent` and multiple CLIs register that name).

**Fix (operator — plugin does not repair PATH):**

1. Install your preferred CLI and ensure its **unambiguous** command is on PATH (`cursor-agent` for Cursor, `grok` for Grok).
2. Dashboard **Kanban-Advanced** → **Binary on PATH** → pick the detected command → **Save** (or re-run `hermes kanban-advanced init`).
3. See [coding agents](../docs/reference/coding-agents.md) § Binary name collisions.

### Binary not listed in init or dashboard picker

**Symptom:** Expected CLI missing from the numbered init list or dashboard dropdown.

**Fix:** Install the CLI and confirm the exact command resolves (`which cursor-agent`, `which grok`, etc.). The picker only shows supported commands **currently on PATH**. Use custom if you need a non-standard command name.

### Coding-agent auth failed (non-Cursor binary)

**Symptom:** Preflight `coding_agent_cli_reachability` or `pre_dispatch_gate.sh` `coding_agent_cli` check fails. Same worker tag `[escalation:coding_agent:auth]` applies — not a protocol violation.

**Fix by binary:** `claude login` / Anthropic key; Codex or `OPENAI_API_KEY`; `GROK_API_KEY` for grok; Gemini CLI login; aider provider keys in config. Re-run:

```bash
PYTHONPATH=. python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py
```

Slow cold starts: `PREFLIGHT_CODING_AGENT_PROBE_TIMEOUT=120` or `check_coding_agent_cli.py --full`.

### "Gateway not running" (G001)

**Symptom:** Cards sit in `ready` forever. `hermes gateway status` shows stopped.

**Fix:**
```bash
hermes gateway run   # run in tmux for persistence
# or: systemctl --user start hermes-gateway
```

### "Cross-mount filesystem" (E011)

**Symptom:** Preflight check 0 blocks. Working copy on `/mnt/c/` or NFS.

**Fix:** Clone to native path:
```bash
git clone <repo-url> ~/projects/<repo-name>
cd ~/projects/<repo-name>
```

### "Protocol violation loop" (gate/audit cards crashing repeatedly)

**Symptom:** Gate or final audit card shows 4+ `protocol_violation` events in `hermes kanban show`. Worker exits cleanly without signaling.

**Root cause:** Orchestrator-only card (no `agent -p` block) assigned to a worker profile. Worker spawns agent with nothing to execute.

**Fix:** Complete the card manually: `hermes kanban complete <task_id> --summary "Orchestrator-only card — no agent work."` Then run the audit/gate work directly. Prevention: `validate_board.sh` check 10 catches this before dispatch; worker Step 3 guard (E014) catches strays at runtime.

### "Triage cards permanently stuck"

**Symptom:** Cards created with `--triage` stay in triage status even after parents complete. `hermes kanban promote` fails with "promote only applies to 'todo' or 'blocked'."

**Root cause:** Triage exit requires the dispatcher + `kanban_decomposer` aux path (`kanban.auto_decompose=true`). kanban-advanced sets `auto_decompose=false` to prevent LLM rewrites of optimized card bodies — so triage cards never promote. This is expected when auto-decompose is off, not only when the dispatcher is degraded. See [umbrella #35986](https://github.com/NousResearch/hermes-agent/issues/35986) Gap 3.

**Fix:** Archive stuck triage cards and recreate using **block-on-create**: `hermes kanban create` (lands `ready`) → `hermes kanban block` immediately → link parents → orchestrator completes gate after `validate_board.sh` → `auto_unblock.sh` releases children when parents are `done`. Never use `--triage` for dependent cards. Full rationale: [[decomposition-workflow]].

### Final audit / remediation loop (post-flight)

**Symptom:** `final_audit_sanity.py` exit **1** or **2**; audit card blocked; remediation children stuck; `validate_board.sh` check **13** FAIL; postmortem shows `uncaught_violation_count: null`.

**Load first:** `plugin/data/references/final-audit-sanity-check.md`. Index: `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")` § **L7**. Orchestrator skill § **When final audit hits a problem**.

| Exit / symptom | Action |
| --- | --- |
| **Exit 2** (plan/git/DB) | `hermes kanban block` audit card — **no** `--spawn-remediation`; fix plan path, git state, or DB |
| **Exit 1** (violations) | `--spawn-remediation`; wait until `hermes kanban list --parent <audit_tid>` shows no running/blocked children; re-run `--tier all` |
| **Max rounds** / escalation | Review `{plan_id}_audit_tier*.json`; operator triage; `final_audit_max_remediation_rounds` in [[configuration]] |
| **`gave_up` remediation** | Escalation on audit card; violations marked `escalated` in tier JSON — no second remediation wave |
| **False `plan_file_zero_diff` after E001 ALLOW** | Add path to done card `Files:`; stamp `Commit:`; re-run audit — not a dropped sub-task |
| **Tier 2 false positive** | Add `final_audit_overrides` in overlay ([[configuration]] — operator-owned, not init-managed) |
| **Premature audit promote** | Do not run `auto_unblock.sh` manually during remediation — `_has_active_remediation_children` guard |
| **Missing tier JSON before cleanup** | Re-run `final_audit_sanity.py --tier all` before archive; see `kanban-advanced:kanban-postmortem` § Final audit KPIs |

### "Cards dispatched before parents finished" / "dependency gating bypassed"

**Symptom:** Child cards run while parent cards are still `todo`, `running`, or not yet linked.

**Root cause:** Vanilla dispatcher atomically claims `ready` cards in under a second ([#16102](https://github.com/NousResearch/hermes-agent/issues/16102)). Parent links added after a card is already `ready` (or already claimed) cannot stop dispatch.

**Fix:** Block every card immediately after create, before stagger sleep. Verify with `validate_board.sh` check 5. See [[decomposition-workflow#why-block-on-create-not-triage-not-initial-status-blocked]].

### "`--initial-status blocked` didn't block" / gate auto-promoted

**Symptom:** Card created with `--initial-status blocked` appears in `ready` or dispatches anyway.

**Root cause:** Observed race in production — create-time blocked status can promote before the block is durable. Separate `hermes kanban block` after create is reliable on `ready` cards (v0.15.0+).

**Fix:** Never use `--initial-status blocked`. Use `hermes kanban block <id>` immediately after `hermes kanban create`. See `plugin/data/references/vanilla-kanban-known-issues.md`.

### "SQLite torn-extend" (kanban.db corruption)

**Symptom:** Gateway logs show `sqlite3.DatabaseError: torn-extend detected: page count mismatch`. Dispatcher stops promoting triage cards, recording failures, or spawning workers.

**Root cause:** Heavy write contention — creating/archiving many cards rapidly collides with dispatcher ticks at page-extension boundaries.

**Fix:** Restart gateway (`hermes gateway restart`) — WAL recovery runs on next open and usually heals. Re-check DB integrity: `python3 -c "import sqlite3; db=sqlite3.connect('$HERMES_HOME/kanban.db'); print(db.execute('PRAGMA integrity_check').fetchone()[0])"`. Prevention: stagger card creates ≥1s apart, pause 3s every 5 cards, verify DB integrity before decomposition.

### "Workspace path rejected" (spawn_failed)

**Symptom:** Card shows `spawn_failed` with error "non-absolute worktree path '.'; use an absolute path."

**Root cause:** `--workspace worktree:.` — the dispatcher rejects relative paths.

**Fix:** Use absolute paths: `--workspace "worktree:/tmp/wt-<plan>-<card>"`. Archive and recreate any cards created with relative paths.

### "Dual-clone worktree drift" (WSL)

**Symptom:** `git worktree list` on Windows shows prunable `/tmp/wt-*` entries from a kanban run. Branches exist in the DrvFS clone but not the Linux clone.

**Root cause:** The kanban dispatcher resolved a cross-mount checkout as its repo, while the orchestrator ran from a native clone. Workers created worktrees registered in a different `.git`.

**Fix:** `git -C /mnt/<drive>/... worktree prune` on the DrvFS side, delete stale branches, verify only one clone is registered with the kanban board. Prevention: `preflight.sh` filesystem coherence check warns on dual-clone scenarios.

### "Postmortem KPI data missing"

**Symptom:** Postmortem report shows "Token log missing" and intervention counter at 0 despite interventions occurring.

**Root cause:** Three disconnected paths — token_tracker wrote to wrong directory, intervention counter was never incremented, postmortem generator read from wrong DB (`state.db` instead of `kanban.db`).

**Fix:** Run `governance_integrity.sh` before decomposition — verifies all data paths are aligned. During execution: workers must call `log_token_run()` (E005 enforces file existence), orchestrator must run `kanban_intervention_inc.sh` on every intervention.

### "Preflight cache stale" (E012)

**Symptom:** Worker reports `E012_STALE_CACHE`.

**Fix:** Orchestrator must re-run preflight:
```bash
bash hermes-kanban-advanced-workflow/scripts/preflight.sh
python hermes-kanban-advanced-workflow/scripts/kanban_attestation.py <plan_id>
```

### "hermes: command not found" / provisioning fails

**Symptom:** `provision.sh` or `preflight.sh` can't find `hermes`.

**Fix:** Ensure Hermes Agent is installed and on PATH:
```bash
which hermes
hermes --version
```

### Working branch reset to `main` after Hermes update

**Symptom:** After `hermes update` or a plugin refresh, the Kanban-Advanced dashboard or `kanban-config.yaml` shows `working_branch: main` even though you previously set a different integration branch (e.g. `staging`, `develop`).

**Root causes:**

1. **Re-init overwrote the overlay** — Older versions of `hermes kanban-advanced init` and dashboard **Bootstrap** always rewrote `kanban-config.yaml` with defaults. Re-running init after an update (or Bootstrap while the form still showed `main`) replaced your branch.
2. **Dashboard resolved the wrong project** — The settings API walks up from the gateway's working directory. After an update the cwd can shift, so status may read a different repo's overlay (often the plugin bundle example, which uses `main`).

**Fix (restore your branch):**

```bash
# Option A — edit the overlay directly
# .hermes/kanban-overrides/kanban-config.yaml
working_branch: <your-branch>

# Option B — dashboard → Kanban-Advanced → Save (not Bootstrap)
# Set Working branch, then click Save

# Option C — CLI init with explicit override
hermes kanban-advanced init --project-root . --working-branch <your-branch>
```

**Prevention (current behavior):**

- Re-init **preserves** `working_branch` and `trigger_branch` from the existing overlay unless you pass `--working-branch` / `--trigger-branch`.
- Dashboard **Bootstrap** on an already-initialized project also preserves branches from file; use **Save** to change them.
- Pin the project when the gateway cwd is ambiguous (multi-clone or plugin dev tree):

```bash
export KANBAN_PROJECT_ROOT=/absolute/path/to/your/project
# or
export HERMES_KANBAN_CONFIG=/absolute/path/to/your/project/.hermes/kanban-overrides/kanban-config.yaml
```

**Verify:** `GET /api/plugins/kanban-advanced/status` includes `project_root` and `config_path` — confirm they point at your app repo, not the plugin install directory.

### Plugin update: "local changes would be overwritten by merge"

The Hermes plugin **install** checkout (`plugin_install_path` from status — typically `$HERMES_HOME/plugins/kanban-advanced`) must stay a clean mirror of upstream. Local edits belong in your **application repo**, not the install tree.

**Dashboard:** **Update Plugin** resets the install dir before pull (all platforms). Check `plugin_local_changes` on status — a non-zero count means drift will be discarded on update.

**Manual recovery** (same commands on Linux, macOS, WSL, and Git Bash on Windows):

```bash
INSTALL="${HERMES_HOME:-$HOME/.hermes}/plugins/kanban-advanced"
cd "$INSTALL"
git status --short
git reset --hard HEAD
git clean -fd
git pull --ff-only || { git fetch origin && git reset --hard origin/main; }
```

On native Windows CMD/PowerShell, use the same `git` commands with your resolved install path (status API field `plugin_install_path`). WSL and native Windows use **separate** `$HERMES_HOME` trees — run the fix in the environment where your gateway runs.

After pull, restart the gateway so materialized skills/scripts refresh.

### Dispatch profiles still have default Hermes skills or wrong SOUL.md

**Symptom:** After bootstrap, `hermes profile show kanban-advanced-worker` reports Skills: 90+; profile `skills/` contains `devops`, `github`, etc.; `SOUL.md` is generic, not `# Worker Prompt` / `# Orchestrator Prompt`.

**Fix:** See [[bootstrap#troubleshooting]] — usually re-run bootstrap after **Update Plugin**, or `HERMES_HOME` mismatch between init and the path you inspect on disk. Delete dispatch profiles (`hermes profile delete <name> -y`) and bootstrap again.

### Agent asked to switch to orchestrator but user doesn't know how

Hermes **cannot switch profiles inside an active chat**. `/profile` only shows the current profile ([Slash Commands Reference](https://hermes-agent.nousresearch.com/docs/reference/slash-commands)). Profile switching is a **new session** ([Profiles guide](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)).

```bash
hermes profile list          # * marks active; discover real names
hermes -p kanban-advanced-orchestrator chat  # new orchestrator session (all platforms)
# or: kanban-advanced-orchestrator chat      # if profile alias exists
```

Then repeat **execute the plan**. Plugin reference: `plugin/data/references/profile-switching.md`.

### Intermittent Cursor auth on parallel workers (coding-agent OAuth race)

**Symptom:** Preflight and single-shot `check_coding_agent_cli.py` pass; some worker cards fail auth while others succeed.

**Fix:** Update plugin (materializes `coding_agent_auth_lock.sh` + pre-warm in `pre_dispatch_gate.sh`). Restart gateway. Verify lock file under `$HERMES_HOME/.locks/`. Re-run `pre_dispatch_gate.sh` before decomposition so OAuth pre-warms once. See [coding-agent auth](../plugin/data/references/coding-agent-auth.md) § Concurrent OAuth refresh race.

### Crons not firing (blocked cards stuck)

**Symptom:** Parents are `done` but children stay `blocked`; manual chat unblock works; no wave progression.

**Checks (in order):**

1. **Gateway running** — `hermes gateway status` or `hermes cron status`. Crons tick inside the gateway process; CLI chat alone does not fire them.
2. **Wave crons exist** — `hermes cron list` must show `kanban-auto-unblock-1m` and `kanban-board-keeper-3m` as `[active]` with `Deliver: local`. When `notify_lifecycle: true` (default), also expect `kanban-lifecycle-notify-5m` with **non-local** deliver (resolved home channel via `scripts/lib/resolve_notify_deliver.sh` — not `deliver=local`). Silent lifecycle → check gate card body includes `plan_id:` and lifecycle deliver is not local. Jobs must include `--workdir <repo-root>` (re-create with `provision_kanban_crons.sh --create --workdir "$(git rev-parse --show-toplevel)"` if logs never update).
3. **Created per plan** — jobs are provisioned at **execute/handoff** (`kanban_handoff.py` → `provision_kanban_crons.sh --create`), **not** at init or orchestrator decompose (`--no-crons` on the handoff path). Re-run create during an active plan if `--check` fails.
4. **Logs** — prefer project `.hermes/kanban/logs/auto-unblock.log` (SSOT); falls back to `$HERMES_HOME/kanban/logs/` when no project kanban dir. `board_keeper.sh` warns when logs are stale >3m while cards are active.
5. **Messaging optional** — missing Telegram/Discord does **not** stop script crons (`deliver=local`).
6. **Headless / no gateway** — `provision_kanban_crons.sh --create --headless` prints a manual loop; run `auto_unblock.sh --stagger-sec 30` every 60s while cards are active.

**Cleanup:** If plan ended but crons still listed → `bash scripts/provision_kanban_crons.sh --remove --plan-id <id>`.

### Broken Hermes post-merge hook (dashboard WebSocket SyntaxError)

**Symptom:** After `hermes update`, dashboard WebSocket `SyntaxError` at `tui_gateway/server.py` ~line 7639.

**Cause:** Local `~/.hermes/hermes-agent/.git/hooks/post-merge` re-applies a broken skill-bundle patch.

**Fix:**

```bash
cd "${HERMES_HOME:-$HOME/.hermes}/hermes-agent"
mv .git/hooks/post-merge .git/hooks/post-merge.disabled
git restore tui_gateway/server.py
git pull --ff-only
hermes gateway restart
```

## Upstream Hermes constraints ([#35986](https://github.com/NousResearch/hermes-agent/issues/35986))

kanban-advanced works around several vanilla Hermes behaviors. When something feels "broken but documented," check this table before patching application code.

| Gap | Symptom | kanban-advanced mitigation |
|-----|---------|---------------------------|
| **1 — Thrash / event churn** | Card burns retries with no durable state change | `board_keeper.sh` flags high event counts on active cards; postmortem `thrash_outliers` when `reblock_count ≥ 3`; iteration budget stamped at decompose |
| **3 — Triage without auto_decompose** | `--triage` cards stuck forever | `auto_decompose=false` + block-on-create; preflight WARN if auto_decompose true |
| **4 — Profile-scoped HERMES_HOME** | Crons created in profile store never tick | `gateway_hermes_home` resolver; `provision_kanban_crons` uses gateway store |
| **6 — OAuth parallel stampede** | Intermittent auth on wave unblocks | `auto_unblock` stagger + `--max-unblock 1`; blocking prewarm in gate; auth lock file |
| **7 — dispatch_stale_timeout default** | Stale dispatches never time out | Bootstrap sets `kanban.dispatch_stale_timeout_seconds=14400`; manual: `hermes config set kanban.dispatch_stale_timeout_seconds 14400` (not an overlay key). See [dispatch-stale-timeout.md](../plugin/data/references/dispatch-stale-timeout.md). |

**Messaging crons vs wave crons:** Lifecycle/completion notify crons use resolved home-channel deliver (`notify_deliver` overlay override optional). Wave progression crons (`auto_unblock`, `board_keeper`) use `deliver=local` only. `provision_kanban_crons.sh --check` fails when lifecycle is local while `notify_lifecycle` is enabled. WARNs when session `HERMES_HOME` is profile-scoped.

**post_tool_call context:** Hook-driven `auto_unblock` uses gateway `HERMES_HOME` + repo cwd; if gateway context is unavailable the hook fails silently (cron remains fallback).

## Full error code listing

See `plugin/data/registry/error-codes.yaml` for all 37 codes with severity, recovery, and retry flags.

## Still stuck?

- **Hermes Agent issues:** See [[external-references]] → Hermes Agent docs
- **Rate limits / provider setup:** See [[provider-strategy]]
- **Governance concepts:** See [[governance]]
- **Setup problems:** See [[setup]]
- **Install / bootstrap verification tests:** See [[plugin-verification]] (`smoke_test_plugin.py`, `sanity_check.sh`, `provision.sh --check`, unit suite)
- **Init / bootstrap / dispatch profiles:** See [[bootstrap]]
- **Config questions:** See [[configuration]]
- **Interaction model / trigger phrases:** See the [README Interaction Model](../README.md#interaction-model)
- **KPI questions:** See the [README Agent KPIs](../README.md#agent-kpis)
