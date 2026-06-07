# Agent Setup Guide

> **For the agent:** When a user says "set up kanban-advanced" or "I want to use this workflow," follow this guide. Load each referenced page as needed.

## Quick path (plugin install — recommended)

1. **Confirm Hermes is installed and running:**
   ```bash
   hermes --version          # ≥ 0.15.2 required
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

3. **Create profiles:**
   ```bash
   hermes profile create orchestrator --clone
   hermes profile create worker --clone
   ```
   Configure thinking effort per role (see [[configuration]]):
   - **orchestrator** → `thinking: high` (planning, auditing, reconciling)
   - **worker** → `thinking: medium` (supervision, eval chain)
   - **Coding agent** → `thinking: low` or off (code generation, speed over depth)
   ```bash
   hermes config set model.thinking high --profile orchestrator
   hermes config set model.thinking medium --profile worker
   ```
   Verify each profile has a valid `config.yaml` with a `model:` block:
   ```bash
   for p in orchestrator worker; do
     DIR=$(hermes profile show "$p" 2>/dev/null | grep "Path:" | awk '{print $2}')
     [ -f "$DIR/config.yaml" ] && grep -q "default:" "$DIR/config.yaml" \
       && echo "OK: $p" || echo "FAIL: $p needs config.yaml with model.default"
   done
   ```

4. **Bootstrap your project:**
   ```bash
   cd your-project
   hermes kanban-advanced init --project-root . --working-branch <branch-name>
   ```
   This provisions config overlay, cron scripts, and environment settings. During init, you'll be asked which **coding agent binary** you use (Cursor CLI `agent`, Claude Code `claude`, OpenAI Codex `codex`, etc.). The choice is written to `.hermes/kanban-overrides/kanban-config.yaml` (`coding_agent_binary`) and `.env` (`KANBAN_CODING_AGENT`). Workers read this to dispatch the right binary. See [[configuration]] for what the overlay contains.

### Skill namespace

All kanban-advanced skills use the `kanban-advanced:` prefix — derived from `plugin.yaml`'s `name` field, not the literal string `plugin:`. Load skills with:
```
skill_view("kanban-advanced:kanban-planning")
skill_view("kanban-advanced:kanban-orchestrator")
```
The old `plugin:kanban-planning` form does NOT work. Skills are also materialized to `$HERMES_HOME/skills/kanban-advanced/` during init so they appear in the system prompt's `<available_skills>` index and can be loaded without the prefix from any profile.

### Coding agent binary

Set during init (step 1c). Supported agents:

| Binary | Source | Install |
|--------|--------|---------|
| `agent` | Cursor CLI | `curl https://cursor.com/install -fsS \| bash` |
| `claude` | Claude Code | `npm i -g @anthropic-ai/claude-code` |
| `codex` | OpenAI Codex | `pip install openai-codex` |
| `grok` | grok-cli | `npm i -g grok-dev` |
| `aider` | Aider | `pip install aider-install` |
| `gemini` | Gemini CLI | `npm i -g @google/gemini-cli` |

The worker reads `KANBAN_CODING_AGENT` from the environment (set in `.env`) and dispatches the coding agent with `[coding_agent, "-p", prompt, ...]`. To change later, edit `.env` or re-run `hermes kanban-advanced init`.

5. **Verify everything:**
   ```bash
   hermes kanban-advanced preflight <plan-id>
   ```
   Fix any failures before proceeding. See [[troubleshooting]] for common issues.

6. **Tell the user:** "Setup complete. Create a plan with the orchestrator (`orchestrator` profile), then run `hermes kanban-advanced decompose --plan <file>`. See the README for the full lifecycle."

## Fresh Hermes install

If Hermes Agent isn't installed yet:

1. **Install Hermes Agent.** See [[external-references]] → Hermes Agent docs.
2. **Create the default profile** with a working model and provider.
3. **Return to Quick Path** above.

## Windows native (Hermes Desktop)

Hermes Agent runs natively on Windows 10/11 — no WSL required. The installer provisions **PortableGit** (a self-contained Git-for-Windows with `bash.exe` and the full POSIX toolchain).

Hermes state directories on native Windows:
- **Data:** `%USERPROFILE%\.hermes` (config, profiles, skills, memory)
- **Install:** `%LOCALAPPDATA%\hermes\hermes-agent`
- **Git:** `%LOCALAPPDATA%\hermes\git` (PortableGit)

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
1. Draft a plan with the orchestrator (`orchestrator` profile) — provide a goal, let the orchestrator write it
2. The orchestrator runs preflight → attestation → decomposition
3. Workers execute, evaluation chain verifies, orchestrator audits

**Guide the user through the interaction model:** The workflow uses trigger phrases at each stage — `"Plan this out"` → `"Do a sanity check"` → `"Harden the plan"` → `"Optimize for Kanban"` → `"Execute the plan"`. After execution, the agent checkpoints at reconciliation, cleanup, and postmortem. The user can walk away after saying "execute." Full details in the [README Interaction Model](../README.md#interaction-model).

**KPIs are automatic.** The agent surfaces success rate, intervention rate, token burn, and failure-mode distribution at the reconciliation checkpoint. See the [README Agent KPIs](../README.md#agent-kpis).

On session start, the `on_session_start` hook fires: on the orchestrator profile it hints to load `kanban-advanced:kanban-orchestrator`; on other profiles it hints about trigger phrases and the bridge skill. All 11 skills are also materialized to `$HERMES_HOME/skills/kanban-advanced/` during init, making them discoverable via the system prompt's `<available_skills>` index.
