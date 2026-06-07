# Iteration Budget Estimation

Formula for estimating happy-path agent turns per card:

```
estimated_turns = (functions × 3) + (test_runs × 2) + (consumer_checks × 2) + (import_fixes × 2) + 2 buffer
```

## Ceiling

- **35 turns** — maximum happy-path estimate. Cards exceeding this must be split.
- **90 turns** — total budget. Happy path should consume ≤35, leaving 55 for debugging.

## Real Phase 2 outcomes

Card 2 agent-prompt (17-turn estimate): 11 runs, 0 autonomous completions. Root cause: scope underestimation — section references forced worker to guess at function bodies, burning turns on research instead of implementation.

## Code relocation is not exempt

Moving 19 functions between files:
- 19 extractions × 3 turns = 57 turns (exceeds ceiling)
- Must be split into 2+ cards

See `kanban-planning` §Line budget analysis for the full table.
