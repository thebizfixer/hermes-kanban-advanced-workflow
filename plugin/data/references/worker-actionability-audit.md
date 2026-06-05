# Worker-Actionability Audit

Run after anchor-point verification and before declaring a plan ready for decomposition. A section that passes anchor verification can still fail here — anchor points may be correct but the section is missing fields a worker needs to execute without guessing.

## The five checks (per section)

| # | Check | What "fail" looks like | Fix |
|---|-------|----------------------|-----|
| 1 | **`Files:` line present** | Section header has no file list, or the file list is buried in prose | Add `**Files:** path/to/file.ext (modify-only)` at section top |
| 2 | **`Mode:` annotated per file** | Files listed without `modify-only` / `create-only` / `any` | Append mode to each file path |
| 3 | **`Commit:` line present** | No pre-written commit message | Add `**Commit:** type: summary` line |
| 4 | **`Tests:` line with file + assertions** | "Tests must pass" or missing entirely | Name a specific test file and at least 2–3 assertion patterns |
| 5 | **`Depends on:` when cross-section** | Section B calls a function section A creates, but no dependency stated | Add `**Depends on:** §N (function_name)` |

## Additional consistency checks

| Check | What "fail" looks like | Fix |
|-------|----------------------|-----|
| **Frontmatter/body alignment** | A `todos:` entry says "wire X" but the body says X is deferred | Edit the frontmatter `content:` string to match the body |
| **Line budget matches body** | Line budget references a different filename than the body | Align filenames; recalculate if body scope changed |
| **Helper reference is named** | "Call the shared repair helper" — which helper? | Use the actual function name |
| **Regex patterns are real** | Pseudocode patterns like `…votes…comments…` in a regex column | Replace with actual `re.compile(r"...", re.I)` patterns |
| **Tracking mechanism specified** | "Log once per run" but no mechanism for "once" | Specify: module-level set, document field check, etc. |
| **Async/sync boundary** | "Call sync helper from async endpoint" but no wrapper specified | Add `await asyncio.to_thread(...)` or equivalent |

## Example: a section that fails the audit

```markdown
### 7. Quote fix

**Commit:** fix quotes

Symptom: quotes have vote counts in them...
```

Fails: no `Files:` line, no Mode annotation, no test file, commit message too vague. A worker given only this section would have to search the codebase to find the relevant function and guess where tests belong.

## Example: a section that passes

```markdown
### 7. Quote contamination

**Commit:** `fix: strip vote/comment metadata from sanitized quotes`

**Files:** `app/services/text.py` (`modify-only`), `tests/test_text_clean.py` (`modify-only`)

...body with approach, regex patterns, edge cases...

**Tests:** `tests/test_text_clean.py` — add cases: "7.7K votes" tail stripped, "53 votes" orphan stripped, subreddit+votes combo stripped.
```

## Taxonomy of gaps found in practice

Patterns discovered during multi-section plan audits:

1. **Missing test file** — section has no `Tests:` line at all
2. **Unnamed helper reference** — "call the shared repair helper" without naming the function
3. **Sync/async ambiguity** — sync helper called from async endpoint with no wrapper
4. **Missing Mode annotations** — files listed with no `modify-only` / `create-only`
5. **Missing frontend test file** — frontend sections often omit the test file entirely
6. **Vague mechanism** — "log once per run" without specifying how to track "once"
7. **Filename mismatch** — line budget and body reference different filenames for the same file
8. **Missing `Files:` line** — section header has no file list at all
9. **Pseudocode regex** — `…votes…comments…` instead of real `re.compile()` patterns
10. **Frontmatter/body contradiction** — todo says "wire X" but body defers it
11. **Stale frontmatter** — todo still references removed functionality after body was updated
