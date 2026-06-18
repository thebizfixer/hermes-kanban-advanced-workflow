# Subagent E — Cron verify (decomposition prep)

**Goal:** Verify wave crons for this plan (created at execute/handoff by default profile).

**Context (substitute before delegate_task):**

```
Repo root: {REPO_ROOT}
Plan ID: {PLAN_ID}
Bundle path: {BUNDLE_PATH}

Steps:
1. bash {BUNDLE_PATH}/scripts/provision_kanban_crons.sh --check
   (wave crons deliver=local, no_agent=true; lifecycle uses home-channel deliver when notify_lifecycle)
2. If step 1 fails, re-create once idempotently then re-check:
   bash {BUNDLE_PATH}/scripts/provision_kanban_crons.sh --create --plan-id {PLAN_ID}
   bash {BUNDLE_PATH}/scripts/provision_kanban_crons.sh --check
3. Record cron job IDs from create output when fallback ran (orchestrator cleanup reference).
```

Return EXACTLY this JSON structure:

```json
{
  "domain": "cron_setup",
  "status": "pass",
  "auto_unblock_cron_id": "<id>",
  "board_keeper_cron_id": "<id>",
  "lifecycle_notify_cron_id": "<id or empty when notify_lifecycle off>",
  "checks": [
    {"id": "cron_check", "status": "pass", "severity": "blocking", "detail": "provision_kanban_crons.sh --check exit 0"}
  ]
}
```

Set `"status": "fail"` if check fails after optional fallback create. Gateway must be running for `--check` — surface gateway errors in `detail`.

**Toolsets:** `["terminal", "cronjob"]`

**MUST NOT:** create kanban cards or write attestation.
