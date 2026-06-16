# Subagent E — Cron setup (decomposition prep)

**Goal:** Create and verify the auto-unblock and board-keeper wave crons for this plan.

**Context (substitute before delegate_task):**

```
Repo root: {REPO_ROOT}
Plan ID: {PLAN_ID}
Bundle path: {BUNDLE_PATH}

Steps:
1. bash {BUNDLE_PATH}/scripts/provision_kanban_crons.sh --create --plan-id {PLAN_ID}
   (deliver=local, no_agent=true — no messaging platform required)
2. bash {BUNDLE_PATH}/scripts/provision_kanban_crons.sh --check
3. Record cron job IDs from step 1 output for orchestrator cleanup reference.
```

Return EXACTLY this JSON structure:

```json
{
  "domain": "cron_setup",
  "status": "pass",
  "auto_unblock_cron_id": "<id>",
  "board_keeper_cron_id": "<id>",
  "checks": [
    {"id": "cron_create", "status": "pass", "severity": "blocking", "detail": "wave crons created"},
    {"id": "cron_check", "status": "pass", "severity": "blocking", "detail": "provision_kanban_crons.sh --check exit 0"}
  ]
}
```

Set `"status": "fail"` if either step fails. Gateway must be running for `--check` — surface gateway errors in `detail`.

**Toolsets:** `["terminal", "cronjob"]`

**MUST NOT:** create kanban cards or write attestation.
