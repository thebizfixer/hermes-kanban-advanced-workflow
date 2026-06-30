# Agent Setup Guide

> **For the agent:** When a user says "set up kanban-advanced" or "I want to use this workflow," follow this guide. Load each referenced page as needed.

**Platforms:** Linux, macOS, Windows native (Hermes Git Bash), and WSL2 — [PLATFORM_NOTES.md](../PLATFORM_NOTES.md). **Coding CLIs:** any supported headless binary ([coding agents](../docs/reference/coding-agents.md)). **Host repo:** any git project; examples use neutral `hermes-kanban-advanced-workflow/` as the bundle path.

## Quick path (plugin install — recommended)

1. **Confirm Hermes is installed and running:**
   ```bash
   hermes --version          # ≥ 0.16.0 required (tested on 0.17.0)
   hermes gateway status     # must be running
   ```
   If not running: `hermes gateway run` (use tmux background for persistence).

2. **Install the plugin:**
   ```bash
   hermes plugins install thebizfixer/hermes-kanban-advanced-workflow
   ```
   Restart Hermes after install. Verify:
   ```bash
   hermes plugins list
   # Should show: kanban-advanced  v1.0.0
   ```

3. **Bootstrap your project** (creates dispatch profiles automatically):
   ```bash
   cd your-project
   hermes kanban-advanced init --project-root . --working-branch <branch-name>
   ```
   Init creates `kanban-advanced-orchestrator` and `kanban-advanced-worker` (or renames legacy `orchestrator`/`worker`), installs plugin **SOUL.md** prompts, seeds **role-only** profile skills (no Hermes bundled skills), and verifies the result. Full detail: [[bootstrap]].

   This also provisions config overlay, cron **script files** (not cron jobs — those are per-plan at decomposition), and environment settings. During init, you'll pick a **coding agent command currently on PATH** (step 1c — numbered list or custom name) and **model** (step 1c-ii; `auto` or a CLI-specific ID — Cursor: `cursor-agent --list-models` or `agent --list-models`). Install your CLI first and prefer unambiguous commands (`cursor-agent`, `grok`, …) over shared names like `agent` — see [coding agents](../docs/reference/coding-agents.md) § Binary name collisions. Values are written to `kanban-config.yaml` (`coding_agent_binary`, `coding_agent_model`) and `.env` (`KANBAN_CODING_AGENT`, `KANBAN_CODING_AGENT_MODEL`, `HOME`). Init runs an **advisory** smoke test when the binary is on PATH — it warns but does not block init. You must add vendor API keys to `.env` or run vendor login on the gateway host before execute; **preflight** blocks decomposition if headless auth still fails. See [[bootstrap#coding-agent-auth-during-bootstrap-limitations]], [coding-agent auth](../plugin/data/references/coding-agent-auth.md), and [coding agents](../docs/reference/coding-agents.md). Change binary/model later via dashboard **Coding Agent** → **Save**.

   **Operator provisioning (beyond init):** Init does not add application `.env`, API keys, `.venv/`, or `node_modules/` to card worktrees. Add what your cards need to `.worktreeinclude` yourself — see [operator-provisioning.md](../plugin/data/references/operator-provisioning.md). Agents: load that file and interview the user about tests and coding-agent auth before execute.

   **Re-init after `hermes update`:** Safe to run again — existing `working_branch` / `trigger_branch` are preserved unless you pass `--working-branch`. Bootstrap re-seeds dispatch profile SOUL/skills and re-verifies. To change the integration branch later, edit the overlay or use dashboard **Save** (not Bootstrap). If the dashboard shows the wrong branch, set `KANBAN_PROJECT_ROOT` to your app repo — see [[troubleshooting]].

4. **Configure reasoning effort per role** (optional — bootstrap seeds defaults when unset; dashboard **Profiles** modal also works — see [[configuration]]):
   - **kanban-advanced-orchestrator** → `high` (planning, auditing, reconciling)
   - **kanban-advanced-worker** → `medium` (supervision, eval chain)
   - **Coding agent** → separate from Hermes profiles; use model/CLI defaults for workers
   ```bash
   hermes config set agent.reasoning_effort high --profile kanban-advanced-orchestrator
   hermes config set agent.reasoning_effort medium --profile kanban-advanced-worker
   ```
   Verify each dispatch profile has a valid `config.yaml` with a `model:` block:
   ```bash
   for p in kanban-advanced-orchestrator kanban-advanced-worker; do
     DIR=$(hermes profile show "$p" 2>/dev/null | grep "Path:" | awk '{print $2}')
     [ -f "$DIR/config.yaml" ] && grep -q "default:" "$DIR/config.yaml" \
       && echo "OK: $p" || echo "FAIL: $p needs config.yaml with model.default"
   done
   ```

### Skill namespace

All kanban-advanced skills use the `kanban-advanced:` prefix — derived from `plugin.yaml`'s `name` field, not the literal string `plugin:`. Load skills with:
```
skill_view("kanban-advanced:kanban-planning")
skill_view("kanban-advanced:kanban-orchestrator")
```
The old `plugin:kanban-planning` form does NOT work. Skills are also materialized to `$HERMES_HOME/skills/kanban-advanced/` during init so they appear in the system prompt's `<available_skills>` index and can be loaded without the prefix from any profile.

### Coding agent binary

Set during init (step 1c) or dashboard **Bootstrap** / **Save**. Init and the dashboard **Binary on PATH** dropdown list only supported commands **currently on PATH** (plus custom) — not a static full menu.

**Supported products** (install first; ensure the exact command resolves on PATH before init):

| Command | Product | Install |
|--------|---------|---------|
| `cursor-agent` (preferred) or `agent` | Cursor CLI | `curl https://cursor.com/install -fsS \| bash` |
| `claude` | Claude Code | `npm i -g @anthropic-ai/claude-code` |
| `codex` | OpenAI Codex | `pip install openai-codex` |
| `grok` | Grok CLI (xAI or superagent) | xAI Grok CLI / `npm i -g grok-dev` |
| `aider` | Aider | `pip install aider-install` |
| `gemini` | Gemini CLI | `npm i -g @google/gemini-cli` |

The name `agent` is used by **multiple** CLIs (Cursor and Grok). If that is the only command on PATH, init/dashboard show it once with an ambiguous label and a **symlink conflict** notice — the plugin does not repair PATH for you. Prefer `cursor-agent` or `grok`. Full contract: [coding agents](../docs/reference/coding-agents.md) § Binary name collisions.

The worker reads `KANBAN_CODING_AGENT` and `KANBAN_CODING_AGENT_MODEL` from `.env`, extracts the prompt from the card body's fenced `agent` block, and dispatches via `scripts/coding_agent_invoke.sh` (per-binary headless flags — see [coding agents](../docs/reference/coding-agents.md) and `plugin/data/references/coding-agent-cli-invocation.md`). To change binary or model: dashboard **Save**, edit `.env` / `kanban-config.yaml`, or re-run init (preserves existing model unless you override interactively).

5. **Verify dispatch profiles on disk** (see [[bootstrap#verify-on-disk-after-bootstrap]]):
   ```bash
   hermes profile show kanban-advanced-worker | grep Skills:
   hermes profile show kanban-advanced-orchestrator | grep Skills:
   # Expect: Skills: 2  and  Skills: 9
   ```

6. **Verify environment:**
   ```bash
   hermes kanban-advanced preflight <plan-id>
   ```
   Fix any failures before proceeding. See [[troubleshooting]] for common issues.

7. **Plugin verification tests** (when bootstrap/update looks wrong — optional but recommended after **Update Plugin**):
   ```bash
   python3 hermes-kanban-advanced-workflow/scripts/smoke_test_plugin.py
   bash hermes-kanban-advanced-workflow/scripts/sanity_check.sh
   bash hermes-kanban-advanced-workflow/scripts/provision.sh --check
   ```
   Full matrix: [[plugin-verification]].

   After init, run the [standard smoke test plan](../test-plan/kanban-standard-smoke-test.plan.md) to validate the full governance pipeline end-to-end. Copy the plan to `.hermes/kanban/plans/`, decompose, and execute.

8. **Tell the user:** "Setup complete. Create a plan with the orchestrator (`kanban-advanced-orchestrator` profile), then run `hermes kanban-advanced decompose --plan <file>`. See the README for the full lifecycle."

## Updating the Plugin

When a new version is released, update from the dashboard. The plugin handles git pull, asset materialization, and sidecar restart automatically — but you must re-bootstrap and (sometimes) restart the gateway.

### Agent workflow (after user says "update the plugin")

1. **Update Plugin** — Click **"Update Plugin"** in the dashboard. This runs `git pull`, materializes updated skills/scripts to `$HERMES_HOME`, reconciles dispatch profiles, and restarts the sidecar. If the dashboard is unavailable or the button fails:
   ```bash
   cd "$(hermes plugins list | grep kanban-advanced | awk '{print $NF}')"
   git pull
   ```
   Then click **"Update Plugin"** anyway — it detects the repo is current but still restarts the sidecar and re-materializes.

2. **Re-bootstrap** — **Always** click **"Bootstrap"** (or run `hermes kanban-advanced init`) after updating. This re-provisions the config overlay, dispatch profile models/skills, materialized scripts, and `.env` sync. Existing `working_branch` / `trigger_branch` are preserved unless explicitly changed.

3. **Restart gateway** (conditional) — Only when the update touches `kanban.*` config keys, `.env` variables the dispatcher reads, or gateway-side cron scripts:
   ```bash
   hermes gateway restart
   ```
   The gateway does **not** hot-reload config. Restart from **outside** the Hermes session.

4. **Verify** — Plugin verification tiers confirm the update applied cleanly:
   ```bash
   python3 hermes-kanban-advanced-workflow/scripts/smoke_test_plugin.py   # Tier 1 — contract
   bash hermes-kanban-advanced-workflow/scripts/sanity_check.sh           # Tier 1 — structure
   bash hermes-kanban-advanced-workflow/scripts/provision.sh --check       # Tier 2 — materialization
   ```
   Full matrix: [[plugin-verification]]. If any verification fails, re-run Bootstrap and re-check.

### Reference for agents

| Step | What | Required? |
|------|------|:---:|
| Update Plugin | `git pull` + materialize + restart sidecar | ✓ |
| Bootstrap | Re-provision profiles, overlay, scripts, `.env` | ✓ |
| Gateway restart | Only when config/cron/`.env` changed | Conditional |
| Verify | `smoke_test_plugin.py` + `provision.sh --check` | Recommended |

The sidecar restart is automatic (dashboard "Update Plugin" schedules it). Do **not** use `taskkill /F /IM python.exe` to restart the sidecar on Windows — it kills the gateway. Use PID-targeted kill or let the dashboard button handle it. See [[troubleshooting]] § Sidecar server restart kills gateway.

User-facing reference: [README.md](../README.md#updating-the-plugin) and [install guide](../docs/how-to/install-as-plugin.md#updating).

## Fresh Hermes install

If Hermes Agent isn't installed yet:

1. **Install Hermes Agent.** See [[external-references]] → Hermes Agent docs.
2. **Create the default profile** with a working model and provider.
3. **Return to Quick Path** above.

## Windows native (Hermes Desktop)

Hermes Agent runs natively on Windows 10/11 — no WSL required. The installer provisions **PortableGit** (a self-contained Git-for-Windows with `bash.exe` and the full POSIX toolchain).

Hermes state directories on native Windows:
- **Data:** `%LOCALAPPDATA%\hermes` (config, profiles, skills, memory) — primary on Hermes Desktop
- **Legacy:** `%USERPROFILE%\.hermes` (some installs)
- **Install:** `%LOCALAPPDATA%\hermes\hermes-agent`
- **Git:** `%LOCALAPPDATA%\hermes\git` (PortableGit)

Init resolves `HERMES_HOME` automatically; see [[bootstrap#hermes_home-resolution]].

See the [Windows Native Guide](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native) for full details.

1. **Install Hermes** — PowerShell one-liner or Hermes Desktop GUI:
   ```powershell
   iex (irm https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.ps1)
   ```
   Or download [Hermes Desktop](https://github.com/NousResearch/hermes-agent/releases/latest) for a GUI installer.

2. **Follow Quick Path** above — the plugin install works identically on Windows.

3. **Worktree paths on Windows** — Git Bash maps `/tmp` to `%TEMP%`:
   ```
   --workspace "worktree:/tmp/wt-<plan>-<card>"         # Git Bash
   --workspace "worktree:C:/temp/wt-<plan>-<card>"       # Native CMD/PowerShell
   ```

See the [Hermes Windows Native Guide](https://hermes-agent.nousresearch.com/docs/user-guide/windows-native) for full Windows compatibility details.

## WSL users

Clone the repo to a **native WSL path** (not `/mnt/c/` or `/mnt/d/`):
```bash
git clone <repo-url> ~/projects/<repo-name>   # ✓ native ext4
# NOT: /mnt/c/Users/...                         # ✗ DrvFs cross-mount
```
Cross-mount paths cause silent write corruption. Preflight check 0 catches this and blocks.

## After setup: first plan

The user should:
1. Draft a plan with the orchestrator (`kanban-advanced-orchestrator` profile) — provide a goal, let the orchestrator write it
2. The orchestrator runs preflight → attestation → decomposition
3. Workers execute, evaluation chain verifies, orchestrator audits

**Guide the user through the interaction model:** The workflow uses trigger phrases at each stage — `"Plan this out"` → `"Do a sanity check"` → `"Harden the plan"` → `"Optimize for Kanban"` → `"Execute the plan"`. After execution, the agent checkpoints at reconciliation, postmortem, and cleanup **unless** dashboard **Cron → Walk-away mode** is on (`walk_away_mode: true` — then post-execution is automated after final audit). Full details in [Interaction Model](../docs/reference/interaction-model.md) and `plugin/data/references/walk-away-mode.md`.

**KPIs are automatic.** The agent surfaces success rate, intervention rate, token burn, and failure-mode distribution at the reconciliation checkpoint. See the [README Agent KPIs](../README.md#agent-kpis).

On session start, the `on_session_start` hook fires: on `kanban-advanced-orchestrator` it hints to load `kanban-advanced:kanban-orchestrator`; on other profiles it hints about trigger phrases and the bridge skill. All 12 skills are materialized to `$HERMES_HOME/skills/kanban-advanced/` during init (shared index); dispatch profiles additionally get role-only copies under their profile `skills/` dirs — see [[bootstrap#two-skill-locations-do-not-confuse]].
