# Subagent C — Infra gate (read-only)

**Goal:** Verify kanban infrastructure: database integrity, cron scripts, hermes on PATH, card policy script, gateway status. Return structured JSON.

**Context (substitute before delegate_task):**

```
Repo root: {REPO_ROOT}
Hermes home: {HERMES_HOME}
Bundle path: {BUNDLE_PATH}

Run these checks:

1. kanban_db integrity (BLOCKING):
   python3 -c "import sqlite3; db=sqlite3.connect('{HERMES_HOME}/kanban.db'); assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'"

2. cron_scripts present and executable (BLOCKING):
   test -x {HERMES_HOME}/scripts/auto_unblock.sh
   test -x {HERMES_HOME}/scripts/board_keeper.sh
   test -x {HERMES_HOME}/scripts/worktree_setup.sh

3. hermes on PATH (BLOCKING):
   PATH="${HOME}/.local/bin:${PATH}" command -v hermes >/dev/null 2>&1

4. card_policy_script exists (WARNING):
   test -f {BUNDLE_PATH}/scripts/kanban_card_policy.py

5. gateway_running (WARNING):
   hermes cron status 2>&1 | grep -qiE 'running|active'
```

Return EXACTLY this JSON structure:

```json
{
  "domain": "infra",
  "status": "pass",
  "checks": [
    {"id": "kanban_db", "status": "pass", "severity": "blocking", "detail": "integrity_check: ok"},
    {"id": "cron_scripts", "status": "pass", "severity": "blocking", "detail": "3 scripts executable"},
    {"id": "cron_hermes_path", "status": "pass", "severity": "blocking", "detail": "hermes at ~/.local/bin/hermes"},
    {"id": "card_policy_script", "status": "pass", "severity": "warning", "detail": "script present"},
    {"id": "gateway_running", "status": "pass", "severity": "warning", "detail": "gateway active"}
  ]
}
```

Set domain `"status": "fail"` only when any **blocking** check fails. **Warning** checks with `status: fail` do not change domain `status` (serial gate WARN parity).

**Toolsets:** `["terminal"]` only.

**MUST NOT:** write any files. Read-only checks only.
