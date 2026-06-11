# How to: run preflight

Run preflight to validate your environment before decomposition:

```bash
hermes kanban-advanced preflight <plan-id>
```

Or run the script directly:

```bash
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
bash hermes-kanban-advanced-workflow/scripts/preflight.sh
```

Exit **0** = pass or degraded-only; **1** = blocking.

Checks include filesystem coherence, kanban DB integrity, memory, secrets, API URL (from overlay), gateway, profiles, environment parity, and **`coding_agent_cli_reachability`** (headless smoke of the configured coding CLI).

Bootstrap runs the same smoke **advisory** only — init can succeed when this check would fail. Preflight is the first **blocking** enforcement before decomposition.

Skip knobs: `references/preflight-env-knobs.md` (in plugin data). Auth SSOT: `plugin/data/references/coding-agent-auth.md`.

Preflight sources **main repo** `.env` for `required_secrets` (from `kanban-config.yaml`). Card worktrees need the same vars only if you add `.env` to `.worktreeinclude` — see [operator-provisioning.md](../../plugin/data/references/operator-provisioning.md).

For agent-facing detail, load the `kanban-advanced:kanban-preflight` skill.
