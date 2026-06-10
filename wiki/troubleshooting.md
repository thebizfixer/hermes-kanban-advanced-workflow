# Troubleshooting

> **For the agent:** When a user reports a failure, match the symptom to the error code below. Every error maps to a recovery action in [[governance]].

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

### "Evaluation chain DENY" (E001-E006)

**Symptom:** Worker completed agent run but task blocked with `E00x`.

**Fix:** See the specific error:
- E001: Agent missed a file. Check agent output, retry with explicit path.
- E002: Agent modified unlisted files (auto-reverted). Add files to `Files:` if intentional.
- E003: Tests failed. Review diff, fix code, re-run agent.
- E004: Commit message mismatch. Amend commit or update `Commit:` line.
- E005: Token log missing. Run `scripts/token_tracker.py` manually.
- E006: Zero output. Check workspace type (must be `worktree`, not `scratch`).

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

### Agent asked to switch to orchestrator but user doesn't know how

Hermes **cannot switch profiles inside an active chat**. `/profile` only shows the current profile ([Slash Commands Reference](https://hermes-agent.nousresearch.com/docs/reference/slash-commands)). Profile switching is a **new session** ([Profiles guide](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)).

```bash
hermes profile list          # * marks active; discover real names
hermes -p orchestrator chat  # new orchestrator session (all platforms)
# or: orchestrator chat      # if profile alias exists
# or: hermes profile use orchestrator && hermes chat
```

Then repeat **execute the plan**. Plugin reference: `plugin/data/references/profile-switching.md`.

## Full error code listing

See `plugin/data/registry/error-codes.yaml` for all 36 codes with severity, recovery, and retry flags.

## Still stuck?

- **Hermes Agent issues:** See [[external-references]] → Hermes Agent docs
- **Rate limits / provider setup:** See [[provider-strategy]]
- **Governance concepts:** See [[governance]]
- **Setup problems:** See [[setup]]
- **Config questions:** See [[configuration]]
- **Interaction model / trigger phrases:** See the [README Interaction Model](../README.md#interaction-model)
- **KPI questions:** See the [README Agent KPIs](../README.md#agent-kpis)
