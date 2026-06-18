# Diagnosing stalled cards

> **For the agent:** When a card thrashes, blocks repeatedly, or never promotes — use this checklist before operator intervention.

## Quick triage

| Symptom | Check | Reference |
| --- | --- | --- |
| Malformed `Tests:` | P014 / `validate_board.sh` check 11 | `plan-file-format.md` § Tests |
| Plan file not on any card | `validate_card_bodies.py` V001 | `execution-doctrine.md` |
| verify-deploy archived without JSON | `kanban_pre_complete_gate.py` | `wiki/governance.md` § Card attestation |
| Same E-code ≥3 at same HEAD | `cycle_detector.py` → CYCLE_DETECTED | `wiki/troubleshooting.md` |
| Thrash / reblock loop | `board_keeper.sh` + postmortem `thrash_outliers` | `kanban-postmortem` skill |
| Parent not done | `auto_unblock.sh` / upstream [#16102](https://github.com/NousResearch/hermes-agent/issues/16102) | `decomposition-workflow.md` |
| Blocked on upstream feature | `planned-features.md` | Filing map + partial workarounds |
| Cron silent | `provision_kanban_crons.sh --check` | `walk-away-mode.md` |

## Yellow Belt (cycle detect)

When `cycle_detector.py` reports `CYCLE_DETECTED`:

1. Stop auto-unblock for the plan until operator reviews.
2. Load `kanban-orchestrator-governance` — classify as logistics vs plan intent.
3. Operator edits plan (split card, fix Tests:, add `TDD: allowed`) or archives stale cards with `--archive-prior`.

## verification-deploy false completion

1. Confirm `Type: verification-deploy` or `Deploy:` line on card.
2. Require `.hermes/kanban/card-attestations/{plan_id}-{card_key}.json` via `kanban_card_attestation.py write`.
3. Run `kanban_pre_complete_gate.py <task_id>` before `hermes kanban complete`.

## Multi-file acceptance miss

1. Run `plan_hardening_diff.py --plan <file>` after Harden.
2. Final audit tier1 `call_site_miss` / `acceptance_miss` — per-file `Verify: rg` in Acceptance.
