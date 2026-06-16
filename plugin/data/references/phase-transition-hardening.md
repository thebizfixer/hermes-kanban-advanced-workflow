# Phase transition hardening

Re-verify a **deferred plan phase** before re-activating it for decomposition.

## Checklist

1. **Re-anchor line numbers** — `git checkout` plan from `${working_branch}`; grep every `L\d+` claim against HEAD.
2. **Flesh placeholders** — replace `TBD` workstreams with `Files:`, test command, and acceptance bullets.
3. **Dependency graph** — redraw waves; see `dependency-graph-format.md`.
4. **Verification gates** — each workstream has a runnable test or explicit manual verify step.
5. **Goal cards** — re-run `verify_goal_cards.py`; budget ≤ `goal_card_budget`.
6. **Provider / env drift** — re-run `preflight.sh`; refresh attestation if TTL expired.

## Output

Short **phase delta** comment on the plan: what changed since last deferral, new risks, updated line_budget.
