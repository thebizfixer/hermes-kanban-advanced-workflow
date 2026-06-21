# Plan Hardening Methodology

Tier-gated hardening pass after a sanity check. Work through each tier in order, stopping when time or token budget is exhausted.

## Tiers

### Critical (must fix before decomposition)
- Plan not in canonical location `.hermes/kanban/plans/` (copy during Harden — see `plan-hardening-checklist.md` item 0)
- Missing `Anchor:` on non-trivial code-gen cards (`audit_anchors.py --strict`)
- Stale **declared** anchor pins (`verify_anchors.py` against HEAD)
- Missing edge cases that would block card execution
- Unverified auto-research claims

### Important (should fix)
- Deferred bloat (>30% decisions deferred)
- Missing test strategies
- Redundant or overlapping changes
- **Docs cards ordered after implementation.** Documentation workstreams that describe shipped behavior must not dispatch before their referenced implementation cards. Flag when a docs card appears in an earlier wave than the implementation cards it documents — the `verify_optimization.sh` check 14 produces an inverted-graph WARN. The clockwork-v2 anti-pattern (Card 1 docs before Cards 2–5 implementation) produced `EXTRACTION.md` with stale 3.5s poll times, `[new]` tags, and `pending` backend-mode references. Fix during Harden: either reorder docs cards to the final wave, or add `Reconcile against HEAD after wave N` acceptance with an `acceptance-verify` follow-up card.

### Nice-to-have (fix if time permits)
- Consolidation opportunities (merge same-file cards)
- Documentation consistency

## Verification script suite

After hardening, verify (from repo root):

```bash
# Shape: non-trivial cards declare Anchor:; Files: are plain paths
python3 hermes-kanban-advanced-workflow/scripts/audit_anchors.py --plan .hermes/kanban/plans/{plan_id}.plan.md --strict

# Freshness: declared pins vs HEAD (±5 line symbol drift = warn)
python3 hermes-kanban-advanced-workflow/scripts/verify_anchors.py --plan .hermes/kanban/plans/{plan_id}.plan.md

# Suggestions when pins are missing (paste into plan — do not auto-write)
python3 hermes-kanban-advanced-workflow/scripts/lib/plan_parse.py suggest-anchors --plan .hermes/kanban/plans/{plan_id}.plan.md --json
```

**Prose-only line refs** (`example.py L1864` in signal maps without `Anchor:`) are **sanity-check scope** — review manually; they are not extracted for `verify_anchors`.
