# Plan Anchor Verification — Common Inaccuracy Patterns

When verifying plan claims against the codebase before decomposition, these four patterns are the most common failures. Each wastes implementation time because the agent receives wrong information about what the codebase currently does.

## Pattern 1: "Function / flag doesn't exist" — but it does

**Symptom:** A plan proposes creating a helper, gate, or check that already exists in the codebase.

**Example:** A plan proposes a new helper `_db_retained_count(snapshot_id, ...)`. A function `_retained_sample_count_this_run` already does the exact same count. The plan proposes a duplicate of existing functionality.

**Verification:** Before proposing any new helper function, search for it across the codebase. If it already exists, reference it rather than recreating it.

## Pattern 2: "Flag isn't respected" — but it is

**Symptom:** A plan claims a guard flag or early-return condition is ignored, but the code already checks it.

**Example:** A plan says "Remove duplicate rescoring when `skip_flag` is set" — implying the flag is ignored and rescoring happens anyway. But multiple call sites already check the flag and skip the operation. The claimed duplicate does not exist.

**Verification:** When a plan claims a flag is NOT checked, search for every usage site of that flag. Verify whether each site actually gates the behavior the plan says is un-gated.

## Pattern 3: "Need to add a check" — but it's already there (different threshold)

**Symptom:** A plan says to add a gate or guard, but the code already has one — just with different parameters.

**Example:** A plan says "Skip continuation when `remaining() < 1.0`" — implying the check needs to be *added*. But the code already has `if rem <= 0.01: return`. The fix is to *raise the threshold*, not *add the gate*.

**Verification:** When a plan says "add a check for X," search for X in the relevant area first. If it already exists, rephrase the plan as "raise/lower the threshold" with the current value noted.

## Pattern 4: "In-memory" vs "DB-backed" mischaracterization

**Symptom:** A plan describes a value as "in-memory" when it is actually a database query (or vice versa). This leads to wrong hypotheses about the bug mechanism.

**Example:** A plan says "the zero-yield guard uses **in-memory counters** (`retained == 0`)." But `retained` is actually a `count_documents(...)` database call — not an in-memory counter. The bug mechanism is wrong because the two value sources have different staleness properties.

**Verification:** Trace each variable in a condition back to its source. If the plan claims "in-memory," verify the assignment chain is not a DB read. `count_documents`, `find_one`, `aggregate` = DB-backed. Local list comprehensions, `len()` on local lists = in-memory.

## Verification workflow

For each plan claim that a specific function / flag / condition exists or doesn't:

1. Search for the function/flag name across the codebase.
2. Read the code at the claimed location to verify it matches the description.
3. Trace the data source — is it DB or in-memory? Does the plan describe it correctly?
4. Check imports — if the plan says a function is "unwired," verify it is not imported anywhere.
5. Look for existing implementations of proposed new helpers — they may already exist.

If the plan gets any of these wrong, flag it before decomposition. Wrong claims about current state produce wrong implementation instructions.
