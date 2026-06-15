# Plan file format (markdown + YAML)

SSOT for how agents write `.agent/plans/*.plan.md` (and optional `plan_search_dirs` paths). Applies during **Draft**, **Harden**, **Optimize**, and any edit that touches plan markdown.

Cross-refs: `kanban-advanced:kanban-planning` (structure + checklists), `worker-actionability-audit.md` (per-section gates).

## Markup-safe placeholders (mandatory)

Many markdown renderers (and HTML-like preview pipelines) treat angle-bracket placeholders as **tags**. That breaks plan preview and can hide content.

| Avoid | Use instead | Example |
|-------|-------------|---------|
| `<plan_id>` | `{plan_id}` or backticks | `{plan_id}_kpi.json` |
| `<card2-branch>` | `{card2-branch}` | placeholder `{card2-branch}` |
| `<one-line task>` in prose | `{one-line task}` | Spec template slots |
| `` `<30 min`old `` | words or `under 30 minutes` | cache freshness |
| `<>=1` | `>= 1` or `≥ 1` | example counts |
| Nested ` ````markdown` wrapping ` ```agent ` | Single ` ```agent ` fence only | see below |

**Rule:** In plan **prose**, **tables**, **YAML `content:` strings**, and **agent blocks**, never use `<word>` as a replaceable slot. Use `{word}`, ALL_CAPS placeholders, or backticks.

**Comparisons are OK:** `<=`, `>=`, `wall <= 1.5x` — the character after `<` is `=`, not a tag name.

### Code fences

- One fence per block: ` ```agent ` … ` ``` `.
- Do **not** wrap an agent block in an outer ` ````markdown ` fence (nested fences break some parsers and leak inner angle-bracket slots if the outer fence fails).
- Mermaid (` ```mermaid `) and JSON (` ```json `) are fine; keep node labels in double quotes if they contain special characters.

## YAML frontmatter

1. `todos:` — 2-space indent; each item has `id`, `content`, `status` (when used).
2. Quote `content:` when it contains `:`, `#`, `{`, `}`, or comparison operators that confuse YAML.
3. Do **not** put angle-bracket placeholders in `content:` — use `{plan_id}` style.
4. After implementation, sync `status` with reality when the plan tracks execution.

Kanban plans also use: `name`, `plan_id`, `overview`, `line_budget`, `contingencies`, `optimization_checklist`, optional goal-card fields — see `kanban-planning` § Plan structure.

## Card-body contract (`Spec:` block)

Non-trivial code-gen cards carry a **`Spec:`** section inside the ` ```agent ` block. This is the SSOT the coding CLI reads; it removes "explore the codebase to figure it out" turns.

**Trivial carve-out:** single-symbol rename, one-line constant, or pure config — may omit `Spec:` / `Anchor:` / `Examples:`.

**Non-trivial:** new/changed function signature, 2+ files, or branching/parsing/transform logic.

### Template (canonical shape)

```agent
agent -p "Implement {one-line task}.
plan_id: {plan_id}
Files: {path} ({mode}), …
Mode: modify-only
Anchor: {class/function + approx line}
Spec:
- Signature: {exact def/types; raised exceptions}
- Constants: {NAME = value}
- Data shape: {field names + types}
- Behavior: {numbered steps; edge cases}
- Examples: {>=1 happy; 1 edge}
Call-sites: {path:symbol, …} or none
Forbidden: {never-tier boundaries — paths, deps, signature freeze}
Acceptance:
- Done when: {observable assertion / test name}
- Verify: {exact rg/pytest command}
Self-audit: before commit, confirm each Spec/Acceptance bullet; revert files not in Files:
Tests: {command}
Commit: {message}
Diff cap: if >150 net lines, STOP and report.
Do NOT push to ${working_branch} — worktree branch only."
```

### Two precision rules

1. **Contract-first for shared symbols** — Any symbol in `Call-sites:` MUST be pinned once in a `Contracts:` block under `## Kanban optimization` and copied verbatim into every card that defines or calls it.
2. **Precision verbs** — Ban vague integration verbs (`wire`, `hook up`, `integrate`, `handle`, `support`) unless followed by the concrete operation (`call X from Y at Z`, `add field F to dict D`).

### Three-tier boundaries (plan vs card)

| Tier | Where | Example |
|------|-------|---------|
| **Always** | Plan / `AGENTS.md` | test commands, project structure |
| **Ask-first** | Plan sad-path table | operator deploy steps |
| **Never** | Per-card `Forbidden:` | do-not-touch paths, no new deps |

## Acceptance surfaces (decompose discipline)

Before Optimize completes:

1. **One YAML todo → one surface or explicit checklist** — If a todo bundles pytest + operator script + deploy, split cards or numbered `Acceptance:` items.
2. **`Call-sites:`** — `rg` all callers; list every path:symbol that must change.
3. **`Files:` completeness** — `rg` helper symbols across repo; all subscriber-facing call sites in `Files:` or a follow-up card.
4. **Verification taxonomy** — `verification-local` (pytest) vs `verification-deploy` (operator + deploy); never mark deploy todos `completed` on merge alone.
5. **Same-file graph** — Cards touching the same production file: serialize via `wave_parent`, not parallel gate-only siblings.
6. **Multi-parent cap** — Test/doc cards: max **2** production parents unless `Mode: read-only`.

## Plan memory paths

Use brace notation in prose:

- `.hermes/kanban/memory/{plan_id}.json`
- `{plan_id}_kpi.json` beside postmortem markdown

Not `<plan_id>.json`.

## Self-check before "plan optimized"

```bash
# No angle-bracket placeholders in plan body (outside allowed <= >=)
grep -nE '<[A-Za-z_/]' .agent/plans/your-plan.plan.md && echo "FIX: use {placeholder} not <placeholder>"

bash hermes-kanban-advanced-workflow/scripts/verify_optimization.sh --plan .agent/plans/your-plan.plan.md
```

## External grounding

- [GitHub Spec Kit / SDD](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/) — specs as executable contracts
- [Osmani — good spec for agents](https://addyosmani.com/blog/good-spec/) — six areas, three-tier boundaries, self-verification
- [Anthropic — context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — right altitude, curated examples, progressive disclosure
