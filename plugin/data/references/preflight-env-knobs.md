# Preflight environment knobs

| Variable | Default | Effect |
| --- | --- | --- |
| `HERMES_HOME` | `$HOME/.hermes` | State dir for DB, profiles, token log |
| `PREFLIGHT_PROFILES` | overlay `preflight_profiles` or `kanban-advanced-worker,kanban-advanced-orchestrator` | Profiles checked in preflight |
| `PREFLIGHT_REQUIRED_SECRETS` | overlay `required_secrets` | Comma-separated env vars |
| `PREFLIGHT_SKIP_FS_CHECK` | unset | Set `1` to skip filesystem coherence |
| `PREFLIGHT_SKIP_DB_CHECK` | unset | Set `1` to skip kanban DB integrity |
| `PREFLIGHT_SKIP_API` | unset | Set `1` to skip API health URL |
| `PREFLIGHT_ALLOWED_FS_TYPES` | ext4,xfs,apfs,btrfs,tmpfs | Allowed `df` filesystem types |
| `KANBAN_PLAN_ID` | unset | Optional plan id for plan-backup check |
| `PREFLIGHT_MODEL_PING_TIMEOUT` | `15` | Seconds for Hermes profile `model_reachability` ping |
| `PREFLIGHT_CODING_AGENT_PROBE_TIMEOUT` | `45` | Seconds for `coding_agent_cli_reachability` smoke |
| `PREFLIGHT_SKIP_CODING_AGENT_CLI` | unset | Set `1` to skip coding-agent CLI reachability (audit-noted) |
| `KANBAN_CODING_AGENT` | overlay / `.env` | Binary name for coding-agent smoke (`agent`, `claude`, …) |
| `KANBAN_CODING_AGENT_MODEL` | overlay / `.env` | Model ID or `auto` for coding-agent smoke |

Run from repo root: `bash ${bundle_path}/scripts/preflight.sh`
