# Subagent A — Plan gate (read-only)

**Goal:** Verify the plan file exists on the working branch, is pushed, and has fresh plan memory seeded. Run only read-only checks. Return structured JSON.

**Context (substitute before delegate_task):**

```
Repo root: {REPO_ROOT}
Working branch: {WORKING_BRANCH}
Plan ID: {PLAN_ID}
Bundle path: {BUNDLE_PATH}
Plan memory path: {PLAN_MEMORY_PATH}

Run these checks:

1. Plan on working_branch (BLOCKING):
   - source {BUNDLE_PATH}/scripts/lib/plan_paths.sh
   - PLAN_REL=$(resolve_plan_file "{REPO_ROOT}" "{PLAN_ID}" "" 2>/dev/null || true)
   - If PLAN_REL is non-empty: git -C "{REPO_ROOT}" log --oneline -1 -- "$PLAN_REL" | grep -q .
   - Else: git -C "{REPO_ROOT}" log --oneline -1 -- .hermes/kanban/plans/*{PLAN_ID}*.md .agent/plans/*{PLAN_ID}*.md 2>/dev/null | grep -q .

2. Plan pushed (WARNING):
   - git -C "{REPO_ROOT}" fetch origin {WORKING_BRANCH} --dry-run 2>&1 | grep -q 'up to date'

3. Plan memory exists (BLOCKING):
   - test -f {PLAN_MEMORY_PATH}/{PLAN_ID}.json

4. Plan memory fresh (WARNING) — only if memory file exists:
   - python3 {BUNDLE_PATH}/scripts/lib/plan_memory_gate_check.py --memory {PLAN_MEMORY_PATH}/{PLAN_ID}.json --plan "$PLAN_REL" --repo-root "{REPO_ROOT}" --bundle-scripts "{BUNDLE_PATH}/scripts"
```

Return EXACTLY this JSON structure (no prose, no markdown wrapping):

```json
{
  "domain": "plan",
  "status": "pass",
  "checks": [
    {"id": "plan_on_branch", "status": "pass", "severity": "blocking", "detail": "found at .hermes/kanban/plans/foo.plan.md"},
    {"id": "plan_pushed", "status": "pass", "severity": "warning", "detail": "up to date with origin/main"},
    {"id": "plan_memory", "status": "pass", "severity": "blocking", "detail": "memory file exists"},
    {"id": "plan_memory_fresh", "status": "pass", "severity": "warning", "detail": "card count matches plan"}
  ]
}
```

If any **blocking** check fails, set `"status": "fail"` and include failure detail per failed check. **Warning** checks with `status: fail` do not change domain `status` (serial gate WARN parity).

**Toolsets:** `["terminal"]` only — no delegation, cronjob, kanban_create, or file-write tools.

**MUST NOT:** write attestation.yaml, plan_memory.json, kanban.db, or any file. Read-only git and filesystem operations only.
