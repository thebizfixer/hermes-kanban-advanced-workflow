# Plan Hardening Methodology

Tier-gated hardening pass after a sanity check. Work through each tier in order, stopping when time or token budget is exhausted.

## Tiers

### Critical (must fix before decomposition)
- Plan not in canonical location `.hermes/kanban/plans/` (copy during Harden — see `plan-hardening-checklist.md` item 0)
- Stale anchor points (line numbers, function names against HEAD)
- Missing edge cases that would block card execution
- Unverified auto-research claims

### Important (should fix)
- Deferred bloat (>30% decisions deferred)
- Missing test strategies
- Redundant or overlapping changes

### Nice-to-have (fix if time permits)
- Consolidation opportunities (merge same-file cards)
- Documentation consistency

## Verification grep suite

After hardening, verify:
- All line numbers match HEAD: `grep -n "L[0-9]" <plan>.md | while read line; do ...`
- All function names exist: `grep -oP '`[a-z_]+\(`' <plan>.md | while read fn; do grep -r "def $fn" ...`
- All file paths exist: `grep -oP '`[a-z_/]+\.py`' <plan>.md | while read f; do test -f "$f" ...`
