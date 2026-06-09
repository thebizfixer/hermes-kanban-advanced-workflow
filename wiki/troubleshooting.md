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

**Root cause:** `--triage` status can only be promoted by the dispatcher. If the dispatcher is degraded (SQLite corruption, stuck tick), triage cards are unrecoverable.

**Fix:** Archive stuck triage cards and recreate using the blocked pattern: create as ready → immediately block → link parents → unblock when parents done. Never use `--triage` for dependent cards.

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

# Option B — dashboard → Kanban-Advanced → Update settings (not Bootstrap)
# Set Working branch, then click Update settings

# Option C — CLI init with explicit override
hermes kanban-advanced init --project-root . --working-branch <your-branch>
```

**Prevention (current behavior):**

- Re-init **preserves** `working_branch` and `trigger_branch` from the existing overlay unless you pass `--working-branch` / `--trigger-branch`.
- Dashboard **Bootstrap** on an already-initialized project also preserves branches from file; use **Update settings** to change them.
- Pin the project when the gateway cwd is ambiguous (multi-clone or plugin dev tree):

```bash
export KANBAN_PROJECT_ROOT=/absolute/path/to/your/project
# or
export HERMES_KANBAN_CONFIG=/absolute/path/to/your/project/.hermes/kanban-overrides/kanban-config.yaml
```

**Verify:** `GET /api/plugins/kanban-advanced/status` includes `project_root` and `config_path` — confirm they point at your app repo, not the plugin install directory.

## Full error code listing

See `hermes-kanban-advanced-workflow/registry/error-codes.yaml` for all 24 codes with severity, recovery, and retry flags.

## Still stuck?

- **Hermes Agent issues:** See [[external-references]] → Hermes Agent docs
- **Rate limits / provider setup:** See [[provider-strategy]]
- **Governance concepts:** See [[governance]]
- **Setup problems:** See [[setup]]
- **Config questions:** See [[configuration]]
- **Interaction model / trigger phrases:** See the [README Interaction Model](../README.md#interaction-model)
- **KPI questions:** See the [README Agent KPIs](../README.md#agent-kpis)
