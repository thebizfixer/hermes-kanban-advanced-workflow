# Subagent B — Env gate (preflight + coding-agent CLI)

**Goal:** Run the full preflight environment validation including coding-agent CLI reachability. Return structured JSON matching `pre_dispatch_gate.sh` severities.

**Context (substitute before delegate_task):**

```
Repo root: {REPO_ROOT}
Bundle path: {BUNDLE_PATH}
Coding-agent probe timeout: {CODING_AGENT_PROBE_TIMEOUT}  (orchestrator sets from PREFLIGHT_CODING_AGENT_PROBE_TIMEOUT, default 15)

Step 1 — Run preflight.sh:
  cd "{REPO_ROOT}"
  bash {BUNDLE_PATH}/scripts/preflight.sh 2>/dev/null
This outputs JSON on stdout with fields: status ("pass"|"degraded"|"fail"), checks (array of {id, status, severity, message})

Step 2 — Verify coding agent CLI reachability (BLOCKING):
  cd "{REPO_ROOT}"
  PYTHONPATH="{REPO_ROOT}" python3 {BUNDLE_PATH}/scripts/check_coding_agent_cli.py --timeout {CODING_AGENT_PROBE_TIMEOUT}

Step 3 — Combine results and return.
```

Return EXACTLY this JSON structure:

```json
{
  "domain": "env",
  "status": "pass",
  "preflight_status": "pass",
  "coding_agent_cli": "pass",
  "checks": [
    {"id": "preflight", "status": "pass", "severity": "warning", "detail": "overall: pass (2 warnings)"},
    {"id": "coding_agent_cli", "status": "pass", "severity": "blocking", "detail": "agent reachable"}
  ]
}
```

**Severity parity with serial gate (`pre_dispatch_gate.sh`):**

- **preflight:** `pass` or `degraded` → check `status: pass`. `fail` → check `status: fail`, `severity: warning` — domain `status` stays `pass` (non-blocking WARN, same as serial).
- **coding_agent_cli:** blocking — failure sets domain `status` to `fail`.

Set domain `"status": "fail"` only when `coding_agent_cli` fails.

Preflight.sh may write `preflight_cache.json` — that is its only side effect and is safe because only this subagent runs preflight.

**Toolsets:** `["terminal"]` only.

**MUST NOT:** run attestation, write plan_memory, or touch kanban.db.
