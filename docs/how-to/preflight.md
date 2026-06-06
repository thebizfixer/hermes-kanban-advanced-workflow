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

Checks include filesystem coherence, kanban DB integrity, memory, secrets, API URL (from overlay), gateway, profiles, environment parity.

Skip knobs: `references/preflight-env-knobs.md` (in plugin data).

For agent-facing detail, load the `kanban-advanced:kanban-preflight` skill.
