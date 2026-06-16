# Iteration budget case study (WS9)

Worked example for why **code relocation** cards need the same split discipline as greenfield work.

## Scenario

- **19 functions** moved to a new module with full test suite updates.
- **Happy-path turns:** ~72 agent iterations (read → copy → imports → delete → re-export → test → commit per function cluster).
- **Budget:** 90 turns per card → exhausted on first failure cascade.

## Lesson

| Metric | Value |
|--------|-------|
| Gross line motion | add+del ≈ 600, net ≈ 30 |
| Per-function overhead | ~3–4 turns minimum |
| Failure multiplier | 1 red test → +10–20 debug turns |

**Split rule:** Relocation cards follow the same `iteration-budget-estimation.md` ceiling (**35 turns** target per card, hard split before 90). One function group (3–5 symbols) per card with explicit `Files:` and `Mode:`.

## Decomposition pattern

1. Card A: extract helpers + tests (read-only source, new module skeleton).
2. Card B–D: move function groups; each card ends with green tests for touched files only.
3. Card E: remove re-exports from old module + integration test.

See `plugin/data/references/iteration-budget-estimation.md` for the formula.
