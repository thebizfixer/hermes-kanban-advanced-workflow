# Platform-neutral parsing (spec)

> **Status:** Implemented.  
> **Goal:** Eliminate **all** `grep -oP` (Perl-regex grep) from `scripts/` so kanban-advanced runs on **GNU grep, BSD grep (macOS), and Git Bash on Windows** without silent parse failures.  
> **Strategy:** **Option C** — shared **Python** parsers for plan markdown and CLI/process output; shell scripts become thin orchestrators.

---

## Problem

Eight scripts under `scripts/` use `grep -oP`, which is **GNU-only**. macOS ships BSD `grep` (no `-P`). Operators on Mac gateways or mixed CI images can see:

- Empty captures (`|| true` masks failures)
- Wrong branch names, task IDs, or card ordinals
- False passes on optimization/anchor gates

`scripts/sanity_check.sh` currently guards **only** `auto_unblock.sh`. The rest is undetected debt.

`scripts/lib/kanban_cli_parse.sh` solved task-id extraction for `auto_unblock.sh` using `grep -oE`. That pattern does **not** scale to plan markdown (nested sections, backticks, `**Files:**` blocks, anchor context windows).

---

## Goals

1. **Zero** `grep -oP` / `grep -P` in `scripts/` (enforced by sanity check).
2. **Single SSOT** for plan markdown parsing shared by decompose, gates, and memory checks.
3. **Single SSOT** for Hermes CLI / worktree / lightweight text extractions.
4. Preserve existing **CLI entrypoints** (`verify_anchors.sh`, `verify_optimization.sh`, `hermes kanban-advanced verify-optimization`, governance cron paths).
5. **Test coverage** with fixtures — no live `hermes` or `git` required for parser unit tests.

## Non-goals

- Rewriting entire `verify_optimization.sh` heuristic suite in one PR (phased migration).
- Replacing all bash governance scripts with Python (orchestration stays shell).
- Changing plan markdown authoring format or kanban card schema.
- Adding third-party dependencies beyond **PyYAML** (already required by decompose / goal cards).

---

## Architecture

```
scripts/lib/plan_parse.py          ← plan markdown SSOT (extract from kanban_decompose)
scripts/lib/cli_output_parse.py    ← hermes show / worktree / ps / commit / pytest lines
scripts/verify_anchors.py          ← anchor gate (Python; .sh wrapper)
scripts/verify_optimization.py     ← optimization gate (Python; .sh wrapper) [phased]

kanban_decompose.py ──imports──► plan_parse
plan_memory_gate_check.py ──imports──► plan_parse
verify_goal_cards.py  (unchanged; optional later merge of frontmatter helpers)

verify_anchors.sh ──exec──► verify_anchors.py
verify_optimization.sh ──exec──► verify_optimization.py (after parity)

board_keeper.sh, validate_board.sh, … ──python3 -c / cli_output_parse──►
```

### Design principles (Hermes / repo conventions)

- **Python 3.12+**, `from __future__ import annotations`, stdlib + existing PyYAML only.
- Libraries live under `scripts/lib/` (same as `plan_memory_gate_check.py`, `card_body.py`).
- Scripts add `scripts/` or repo root to `sys.path` the same way `kanban_decompose.py` and tests do today.
- Shell wrappers keep **governance_profile** loading, colored output, and exit codes; **parsing never in bash regex**.
- Prefer **structured JSON** on stdout from Python helpers when bash needs multiple values (`--json` flag); human text remains default for operator runs.

---

## Module 1: `scripts/lib/plan_parse.py`

**Extract and generalize** from `scripts/kanban_decompose.py` (do not duplicate). `kanban_decompose.py` becomes a thin importer:

```python
from lib.plan_parse import (
    parse_plan,
    parse_card_block,
    extract_optimization_section,
    split_card_blocks,
    ...
)
```

### Public API (minimum)

| Function | Purpose | Replaces |
|----------|---------|----------|
| `load_plan_text(path: Path) -> str` | UTF-8 read with `errors="replace"` | repeated `cat` / `PLAN_CONTENT` |
| `parse_frontmatter(text: str) -> tuple[dict, str]` | YAML `---` block | ad-hoc grep in optimization checks |
| `extract_optimization_section(text: str) -> str` | `## Kanban optimization` … next `##` | `awk` in verify_optimization §15 |
| `split_card_blocks(section: str) -> list[str]` | `#### Card N` blocks incl. EOF card | `grep -oP '^#### Card \K\d+'` |
| `parse_card_block(block: str) -> dict \| None` | Single card fields | decompose (existing) |
| `parse_plan(path: Path \| str) -> dict` | `{plan_id, cards}` | decompose (existing) |
| `extract_plan_id(text: str) -> str \| None` | `plan_id:` in body/frontmatter | decompose (existing) |
| `extract_markdown_field(block, name: str) -> str \| None` | `**Field:** value` | verify_anchors `**File:**` |
| `extract_files_from_block(block: str) -> list[str]` | `**Files:** a.py, b.py` | `grep -oP 'Files:\s*\K[^.]*'` |
| `list_card_ordinals(section: str) -> list[int]` | `[1,2,3,…]` in file order | `grep -oP '^#### Card \K\d+'` |
| `validate_card_ordinals(ordinals: list[int]) -> str \| None` | Error message if not 1..N sequential | verify_optimization §15 loop |
| `iter_lines_with_line_numbers(text: str)` | `(lineno, line)` for anchors | shell `while read` + manual |

### Anchor-specific API (same module or `plan_parse/anchors.py`)

| Function | Purpose |
|----------|---------|
| `find_backtick_file_refs(line: str) -> list[str]` | `` `path/to/file.py` `` with allowed extensions |
| `find_line_number_refs(line: str) -> list[int]` | `L123`, `L123-456` → first line of range |
| `find_section_file_above(text: str, line_no: int, lookback: int = 50) -> str \| None` | Nearest file above anchor line: `**File:**` / `**Files:**`, `files:` YAML list, or plain `Files:` (agent block) |
| `find_anchor_symbol_above(text: str, line_no: int, lookback: int = 10) -> str \| None` | `def foo`, `class Bar`, `` `symbol` `` |
| `extract_anchors(plan_text: str) -> list[AnchorRef]` | Dataclass: `file`, `line`, `symbol_hint`, `source_line` |

`AnchorRef` verification (read file at HEAD, ±5 line stale threshold) stays in `verify_anchors.py` — **parsing only** in `plan_parse`.

### Test migration

- Move decompose parser tests to `tests/test_plan_parse.py` (or keep `test_kanban_decompose.py` importing `plan_parse`).
- Reuse fixtures: `tests/fixtures/plans/matrix_v5_sample.plan.md`, `markdown_files.plan.md`.
- Add fixtures:
  - `tests/fixtures/plans/anchors_sample.plan.md` — backtick paths, `**File:**`, `L42`, stale context
  - `tests/fixtures/plans/optimization_ordinals_gap.plan.md` — Card 1, Card 3 (gap) for ordinal validator

### Breaking-change guard

`parse_plan()` return shape and `parse_card_block()` keys **must not change** without updating:

- `scripts/kanban_decompose.py`
- `scripts/lib/plan_memory_gate_check.py`
- `tests/test_kanban_decompose.py`
- `plugin/skills/kanban-planning/SKILL.md` (behavioral contract)

---

## Module 2: `scripts/lib/cli_output_parse.py`

Portable replacements for **non-plan** `grep -oP` uses. Pure functions, no subprocess.

| Function | Input | Output | Replaces in |
|----------|-------|--------|-------------|
| `extract_task_ids(text: str) -> list[str]` | any stdout | `t_*` unique order | `validate_board.sh`, `board_keeper.sh` |
| `extract_first_integer(text: str) -> int \| None` | line | first number | `max-retries` parsing |
| `extract_parent_task_ids(show_text: str) -> list[str]` | `hermes kanban show` | parent `t_*` | `validate_board.sh` |
| `extract_max_retries(show_text: str) -> int \| None` | show output | int | `validate_board.sh`, `board_keeper.sh` |
| `extract_created_timestamp(show_text: str) -> str \| None` | show output | `YYYY-MM-DD HH:MM` | `board_keeper.sh` |
| `extract_worktree_branch(worktree_line: str) -> str` | `git worktree list` row | branch or `detached` | `worktree_audit.sh`, `git_safe_cleanup.sh` |
| `extract_commit_hash_from_body(body: str) -> str \| None` | card body | 7–40 hex | `verify_commits_reachable.sh` |
| `extract_pytest_commands(plan_text: str, limit: int = 5) -> list[str]` | plan md | `pytest …` commands | `post_merge_gate.sh` |

**Regex policy:** use `re` module only; patterns documented in docstrings; no lookbehind unless covered by tests.

**Shell integration pattern:**

```bash
PARENTS=$(python3 "$SCRIPT_DIR/lib/cli_output_parse.py" parents --text "$(hermes kanban show "$tid" 2>/dev/null)")
```

Or module CLI:

```bash
python3 -m lib.cli_output_parse parents --file /tmp/show.txt
```

Prefer **`python3 "$SCRIPT_DIR/lib/cli_output_parse.py"`** with subcommands for Git Bash on Windows (no reliance on `python3 -m` package layout).

### Overlap with `kanban_cli_parse.sh`

| Approach | Action |
|----------|--------|
| `kanban_cli_parse.sh` | **Keep** for bash-only callers (`auto_unblock.sh`); implementations stay `grep -oE`. |
| Duplication | **Acceptable** — Python and bash parsers must share **test vectors** in `tests/fixtures/cli_output/` (`.txt` snippets) validated by both `test_cli_output_parse.py` and a small `tests/test_kanban_cli_parse.sh` (optional). |
| Long-term | Optional: generate bash from Python test vectors doc — **not required** for v1. |

---

## Module 3: `scripts/verify_anchors.py`

Replace inline logic in `verify_anchors.sh`.

### CLI

```bash
python3 scripts/verify_anchors.py --plan <plan.md> [--strict] [--profile advisory|balanced|strict] [--json]
```

### Behavior parity

- Load governance profile (import `lib.governance_profile` or duplicate minimal loader — prefer **shared** `governance_profile.py` already used from shell via source).
- `extract_anchors()` → verify each against repo root.
- Exit codes: `0` pass, `1` fail/warn-in-strict, `2` usage.
- Human output: keep `✓` / `⚠ WARN` / `✗ FAIL` lines so `verify_optimization.sh` check §1 (`grep -c '✗ FAIL'`) still works during transition.

### `verify_anchors.sh` (after)

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/verify_anchors.py" "$@"
```

---

## Module 4: `scripts/verify_optimization.py` (phased)

Full port of 15 checks is large; **grep -oP elimination** is the hard requirement. Phased delivery:

### Phase A (required for “no grep -oP”)

| Check | Today | Python |
|-------|-------|--------|
| §1 Anchors | subprocess `verify_anchors.sh` | subprocess `verify_anchors.py` |
| §6 Cross-section files | `grep -oP 'Files:\s*\K…'` | `extract_files_from_block` per workstream section |
| §15 Card ordinals | `grep -oP '^#### Card \K\d+'` | `list_card_ordinals` + `validate_card_ordinals` |

Remaining checks stay bash **grep -E / awk / python3 verify_goal_cards** (already portable).

### Phase B (optional consolidation)

Port heuristic checks (agent blocks, `--model`, contingencies table, …) into `verify_optimization.py` as named functions `check_agent_blocks()`, etc. Single `python3 verify_optimization.py --plan` runs all checks. `verify_optimization.sh` becomes `exec` wrapper.

**Shipped (2026-06):** Checks **19–21** (presentation acceptance, `ui_stack` / Surface-slots, motion+a11y) live in `verify_optimization.sh` and `scripts/lib/verify_optimization_presentation.py` — not yet folded into a single Python module. Total bash gate count is **21** checks; Phase B consolidation remains optional.

**Recommendation:** Ship **Phase A** in first PR; Phase B as follow-up when parity tests pass.

---

## Shell script migration matrix

| Script | `grep -oP` count | Migration |
|--------|------------------|-----------|
| `verify_anchors.sh` | 6 | **→ `verify_anchors.py`** (full) |
| `verify_optimization.sh` | 2 | **→ `plan_parse`** for §6, §15; §1 calls `verify_anchors.py` |
| `validate_board.sh` | 3 | **`cli_output_parse`** |
| `board_keeper.sh` | 3 | **`cli_output_parse`** |
| `worktree_audit.sh` | 1 | **`cli_output_parse.extract_worktree_branch`** |
| `git_safe_cleanup.sh` | 1 | same |
| `verify_commits_reachable.sh` | 1 | **`extract_commit_hash_from_body`** |
| `post_merge_gate.sh` | 1 | **`extract_pytest_commands`** |
| `sanity_check.sh` | 0 (reference only) | **extend guard** (below) |

After migration: `rg 'grep -oP|grep -P' scripts/` → **no matches**.

---

## Sanity check enforcement

Replace narrow check with repo-wide guard:

```bash
# scripts/sanity_check.sh (new)
echo "=== Platform-neutral parsing ==="
if rg -q 'grep -oP|grep -P' scripts/ 2>/dev/null; then
  echo "  [no grep -P in scripts/] FAIL"
  rg 'grep -oP|grep -P' scripts/ || true
  FAIL=$((FAIL + 1))
else
  echo "  [no grep -P in scripts/] PASS"
  PASS=$((PASS + 1))
fi
check "plan_parse.py exists" "test -f scripts/lib/plan_parse.py"
check "cli_output_parse.py exists" "test -f scripts/lib/cli_output_parse.py"
check "verify_anchors.py exists" "test -f scripts/verify_anchors.py"
```

Fallback when `rg` missing: `grep -rE 'grep -oP|grep -P' scripts/` (portable).

Keep existing `kanban_cli_parse.sh` / `auto_unblock` checks.

---

## Tests

| File | Coverage |
|------|----------|
| `tests/test_plan_parse.py` | optimization section, card blocks, ordinals, files extraction, frontmatter, anchor lookback (`**Files:**`, YAML `files:`, agent `Files:`) |
| `tests/test_cli_output_parse.py` | task ids, worktree branch, commit hash, pytest lines, show output fields |
| `tests/test_verify_anchors.py` | integration with temp repo + fixture plan (git optional mock) |
| `tests/test_kanban_decompose.py` | **unchanged behavior** after import refactor |

Fixture directory:

```
tests/fixtures/cli_output/
  kanban_show_parents.txt
  kanban_show_max_retries.txt
  git_worktree_list.txt
  card_body_commit.txt
  plan_pytest_snippet.md
```

---

## Rollout plan

| Phase | Deliverable | grep -oP remaining |
|-------|-------------|-------------------|
| **1** | `plan_parse.py` + refactor `kanban_decompose.py` + tests | 18 |
| **2** | `verify_anchors.py` + shell wrapper | 12 |
| **3** | `verify_optimization` §6 + §15 via `plan_parse` | 10 |
| **4** | `cli_output_parse.py` + migrate 5 scripts | 0 |
| **5** | Sanity guard + docs + `llms.txt` | 0 (enforced) |

Each phase must pass:

```bash
bash scripts/sanity_check.sh
python -m unittest discover -s tests -q
```

---

## Documentation updates (on implementation)

| Doc | Change |
|-----|--------|
| `docs/reference/scripts.md` | `verify_anchors.py`, `plan_parse` SSOT, platform note |
| `wiki/troubleshooting.md` | “BSD grep / macOS” → resolved by Python parsers |
| `PLATFORM_NOTES.md` | Remove grep -oP caveat after phase 5 |
| `llms.txt` | Link this spec + new modules |
| `plugin/skills/kanban-planning/SKILL.md` | `verify_optimization.sh` unchanged invocation |

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Parser drift vs `kanban_decompose` | Single `plan_parse.py` SSOT; decompose imports only |
| `verify_optimization` subprocess grep on anchor output | Keep stable log format; contract test in `test_verify_anchors.py` |
| Windows path separators in plan files | `plan_parse` normalizes with `Path` / forward slashes for display |
| PyYAML missing on gateway | Same as today — decompose already requires it; preflight can advise |
| Performance on large plans | Python line scan O(n); plans are small (<500KB); acceptable |

---

## Implementation checklist

- [ ] `scripts/lib/plan_parse.py` — extract from `kanban_decompose.py`
- [ ] Refactor `kanban_decompose.py` to import `plan_parse`
- [ ] Update `plan_memory_gate_check.py` import path if needed
- [ ] `scripts/verify_anchors.py` + thin `verify_anchors.sh`
- [ ] `verify_optimization.sh` §6 + §15 → `plan_parse` CLI hooks
- [ ] `scripts/lib/cli_output_parse.py` + CLI entrypoint
- [ ] Migrate `validate_board.sh`, `board_keeper.sh`, `worktree_audit.sh`, `git_safe_cleanup.sh`, `verify_commits_reachable.sh`, `post_merge_gate.sh`
- [ ] Extend `scripts/sanity_check.sh` — ban `grep -P` repo-wide
- [ ] Tests + fixtures
- [ ] Docs (`scripts.md`, `llms.txt`, troubleshooting)

---

## Future (out of scope)

- Full `verify_optimization.py` Phase B (all 15 checks in Python).
- Merge `verify_goal_cards.py` frontmatter helpers into `plan_parse`.
- `post_merge_gate.sh` backend-specific pytest paths — separate host-app coupling issue.
