# Final audit sanity check — operator runbook

**Load:** `skill_view("kanban-advanced:kanban-advanced", "references/final-audit-sanity-check.md")`

Scripted two-tier final audit + post-flight remediation loop. Orchestrator runs audits; workers fix gaps via remediation cards.

## Commands

```bash
python3 hermes-kanban-advanced-workflow/scripts/final_audit_sanity.py --plan-id <id> [--tier 1|2|all]
python3 hermes-kanban-advanced-workflow/scripts/final_audit_sanity.py --plan-id <id> --spawn-remediation [--round N]
```

Reports (default-on): `.hermes/kanban/reports/{plan_id}_audit_tier1.json`, `tier2.json`. Use `--no-json` to suppress.

## Exit codes

| Exit | Meaning | Orchestrator action |
| --- | --- | --- |
| `0` | Clean | `kanban_complete` audit card (after check 13 clears) |
| `1` | Violations | `--spawn-remediation`, wait for wave, re-run audit |
| `2` | Script error (plan missing, git/DB unreachable) | `kanban_block` audit card; page operator — **do not spawn remediation** |

## Orchestrator phased SOP

1. Mechanical gates (merge, optional `post_merge_gate.sh`, KPI sources, churn) — keep existing checklist items 1–10.
2. Run `final_audit_sanity.py --tier all`.
   - Exit 0 → complete audit card.
   - Exit 1 → `--spawn-remediation`, wait for remediation wave, repeat from step 2.
   - Exit 2 → block audit card with error detail; page operator.
3. Cleanup + postmortem.

**Do not** manually run `auto_unblock.sh` during remediation. The `_has_active_remediation_children` guard in `auto_unblock_core.sh` prevents premature audit promotion.

## Card body fields (audit card)

| Field | Set by | Purpose |
| --- | --- | --- |
| `Audit-baseline-sha:` | `kanban_decompose.py` at decompose | Frozen git baseline for Tier 1 (never re-resolve at re-audit) |
| `Audit-round:` | `--spawn-remediation` via `hermes kanban edit` | Durable round counter (survives orchestrator restart) |

## Tier 1 ↔ in-flight (E001) alignment

Tier 1 **`plan_file_zero_diff`** compares each planned `Files:` path against `Audit-baseline-sha..HEAD`. When a path shows zero diff, Tier 1 applies the **same prior-commit forgiveness** as evaluation-chain **E001** (step 1):

1. Find a **done** impl/remediation card whose `Files:` includes the path.
2. Read that card's `Commit:` line.
3. Call `find_prior_commit` (`scripts/lib/card_body.py`) — scan `baseline..HEAD`, then recent history — for a commit whose subject contains the `Commit:` fragment **and** whose tree touched **all** paths on that card's `Files:` list.

If found → **no violation** (work already landed in an earlier card commit). If not found → `plan_file_zero_diff` → remediation spawn.

**Requirements for forgiveness:** done card status, path on card `Files:`, non-empty `Commit:` (E004 enforces this per card). Plan-only paths with no owning card cannot be forgiven via prior commit.

## Remediation card template

```text
plan_id: <id>
Type: remediation
Remediation-phase: final
Remediates: <parent_task_id>
Missed:
- [tier1|tier2] <class>: <detail>
Files: <paths to fix>
Acceptance: <verify bullets — see per-class templates below>
Tests: doc: link-check
```

## `Tests: doc:` protocol

Evaluation chain step 3 skips shell when `Tests:` starts with `doc:` and calls `verify_doc_tests` instead.

| Method | Verifies |
| --- | --- |
| `doc: link-check` | Markdown links in `Files:` paths resolve |
| `doc: symbol-grep <symbol>` | Symbol appears in doc file |
| `doc: yaml-validate` | YAML frontmatter / config parses |

Code tests use `code:` prefix (e.g. `code: pytest tests/test_foo.py`).

## Per-class Acceptance templates

| Violation class | Acceptance template |
| --- | --- |
| `plan_file_zero_diff` | Diff vs `Audit-baseline-sha..HEAD` **or** E001 prior-commit match on a done card's `Commit:` + `Files:` |
| `acceptance_miss` | Acceptance bullet verifiable in merged tree at `{path}` |
| `call_site_miss` | Symbol `{symbol}` resolvable via rg/ast at listed call-sites |
| `unplanned_change` | Path removed from diff or added to plan/card `Files:` union |
| `plan_todo_drift` | Plan frontmatter todo status matches board reality |
| `doc_coverage_gap` | Required doc surface mentions feature or links to SSOT reference |

## Max rounds

`final_audit_max_remediation_rounds` in overlay (default **2**). When `Audit-round >= max` with violations remaining: `bash scripts/kanban_escalation_tracker.sh --task-id <audit_tid> --block-reason "<reason>"`, then `hermes kanban block <audit_tid>` with unresolved violation summary.

## Sad-path quick refs

| Symptom | First action |
| --- | --- |
| Exit 2 on audit | Read stderr; fix plan path / git / DB — do not spawn remediation |
| False `plan_file_zero_diff` after E001 ALLOW | Done card missing `Commit:` or path not on card `Files:` — add/fix card body |
| Remediation wave stuck | Check `hermes kanban list --parent <audit_tid>` for running/blocked children |
| Max rounds exceeded | Review tier JSON unresolved violations; operator triage |
| Tier 2 false positive | Add `final_audit_overrides` entry |

## Cross-references

- Doc matrix SSOT: `final-audit-doc-coverage.md`
- Completeness loop: `wiki/governance.md` § Role-based completeness loop
- Scripts reference: `docs/reference/scripts.md`
