# Subagent D — Plan parse (read-only, decomposition prep)

**Goal:** Parse the optimized plan file and validate all proposed card bodies against card-body-policy.yaml. Return structured cards_yaml-ready summary.

**Context (substitute before delegate_task):**

```
Repo root: {REPO_ROOT}
Plan ID: {PLAN_ID}
Bundle path: {BUNDLE_PATH}
Plan memory path: {PLAN_MEMORY_PATH}

Steps:
1. Resolve plan file via {BUNDLE_PATH}/scripts/lib/plan_paths.sh (resolve_plan_file).
2. Run the same parsing path kanban_decompose.py uses (read-only):
   - Extract workstreams, agent-prompt blocks, Files/Mode lines
   - Validate each block against P001–P009 via {BUNDLE_PATH}/scripts/kanban_card_policy.py where applicable
   - Estimate line budgets per card
3. If {PLAN_MEMORY_PATH}/{PLAN_ID}.yaml exists, cross-check card count vs parsed workstreams.
```

Return EXACTLY this JSON structure:

```json
{
  "domain": "plan_parse",
  "status": "pass",
  "plan_path": ".hermes/kanban/plans/example.plan.md",
  "cards_yaml_path": ".hermes/kanban/memory/example.yaml",
  "card_count": 12,
  "policy_violations": [],
  "checks": [
    {"id": "plan_parse", "status": "pass", "severity": "blocking", "detail": "12 workstreams parsed"},
    {"id": "card_policy", "status": "pass", "severity": "blocking", "detail": "0 P-code violations"}
  ]
}
```

Set `"status": "fail"` when parsing fails or any blocking policy violation is found. List violations in `policy_violations` as `{code, detail}` objects.

**Toolsets:** `["terminal"]` only.

**MUST NOT:** create kanban cards, write kanban.db, or run attestation.
