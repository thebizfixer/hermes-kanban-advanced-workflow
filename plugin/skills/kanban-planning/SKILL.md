---
name: kanban-planning
description: How to write implementation plans optimized for Kanban decomposition — file-level granularity, section structure, agent-prompt blocks, ordinal card body templates, and dependency graphs. Distinguishes Harden (WHAT — content completeness, sanity check, gap closure) from Optimize (HOW — formatting for decomposition, agent blocks, budgets, graphs).
version: 5.3.0
metadata:
  hermes:
    tags: [kanban, planning, decomposition, governance]
    related_skills: [kanban-advanced:kanban-orchestrator, kanban-advanced:kanban-preflight, kanban-advanced:kanban-worker]
---
# Kanban Planning

> **Skill precedence (mandatory):** When this skill and any project-specific skill (e.g., `host-project-dev-environment`) provide conflicting information about profiles, assignees, workspace paths, or dispatch rules, **this skill wins**. Kanban governance rules override project conventions. Specifically:
> - Profile names (`worker`, `orchestrator`) come from `hermes profile list` and `kanban-config.yaml`, NOT from project skill examples or artifact tables.
> - Workspace paths and branch naming come from this skill's decomposition rules, not from project-specific CLI examples.
> - Card body format (`Files:`, `Mode:`, `agent -p` blocks) is enforced by card body policy (P001–P009), not by project documentation.
>
> If you detect a conflict between this skill and a project skill, apply this skill's rule and note the conflict in a `kanban_comment` on the affected card.

Write implementation plans that decompose cleanly into Kanban task graphs. The quality of decomposition depends entirely on plan structure — start by separating what the plan needs to deliver from what would be nice to have, then work out where each change belongs and how it fits into the codebase before writing a single task.

## Governance model (AGT + AEP)

Plans are gated by policy before decomposition. The orchestrator runs `kanban_card_policy.py` on every card body before dispatch. Cards without `Files:`, `agent -p` block, or `Mode:` are blocked (P001/P002/P003) **except** carve-outs: `Type: orchestrator-handoff`, `Type: verification` / `verification-local`, and `Type: verification-deploy` (test/deploy gates — no `Files:` or agent block). Plans without agent-prompt blocks are rejected at the attestation gate (Step 0c) unless every card is a carve-out type. See `kanban-advanced:kanban-orchestrator` § Step 0c and 0d.

**Verification card template:**
```
Type: verification
Tests: {command}
Commit: N/A (verification only)
Mode: read-only
```
No `Files:` line and no ` ```agent` block.

## Plan file format (markdown + preview)

Plans must use **markup-safe placeholders** — many renderers treat `<word>` as HTML-like tags and break preview or hide sections. **Never use angle-bracket placeholders** (`<plan_id>`, `<card2-branch>`, `<command>`). Use **`{placeholder}`** or backticks instead.

Full SSOT: `plugin/data/references/plan-file-format.md` (also loaded via `skill_view("kanban-advanced:kanban-planning", "references/plan-file-format.md")` after init).

**Quick rules:**
- Agent blocks: single ` ```agent ` fence only — no outer ` ````markdown ` wrapper.
- Non-trivial cards: include `Spec:`, `Call-sites:`, `Forbidden:`, `Acceptance:`, `Self-audit:` per §Card body agent-prompt template.
- Shared symbols: `Contracts:` block in `## Kanban optimization`, copied into every card that touches those symbols.
- Paths in prose: `.hermes/kanban/memory/{plan_id}.json`, not `<plan_id>.json`.

**Self-check before Optimize attestation:** `grep -nE '<[A-Za-z_/]' <plan>.md` — fix placeholder matches (allow `<=` / `>=` only).

## Planning stage order (mandatory)

The planning phase proceeds through five stages in this exact order. Do not skip ahead or reorder. The critical distinction: **Sanity check finds gaps** (read-only audit). **Harden closes gaps in WHAT the plan is for** (content completeness, correctness, coverage). **Optimize closes gaps in HOW the plan will execute on Kanban** (formatting, decomposition readiness, agent blocks, budgets).

| Stage | Trigger phrase | What happens | Output |
|-------|---------------|-------------|--------|
| **Draft** | `"Plan this out"` or link to a plan file | Draft from goal (IDE-native path OK). Canonical kanban SSOT is `.hermes/kanban/plans/` after Harden | Plan file (first draft) |
| **Sanity check** | `"Do a sanity check"` or `"sanity check the plan"` | Read-only audit: run `audit_anchors.py` + `verify_anchors.py` on declared pins; cross-reference code claims; identify gaps; flag prose-only `L` refs; note when plan is not in canonical `.hermes/kanban/plans/` (copy is Harden, not sanity). No edits ? output is a findings list. | Gap report (what needs hardening) |
| **Harden** | `"Harden the plan"` | Apply the hardening checklist to close gaps discovered during sanity check (or self-discovered). Tier-gated pass: Critical -> Important -> Nice-to-have. | Hardened plan (content-complete) |
| **Revise** | `"Revise section X"` | Edit in-place, return to review — conversational updates to plan content | Revised plan |
| **Optimize** | `"Optimize for Kanban"` | Close execution-formatting gaps: add agent-prompt blocks, draw dependency graph, estimate iteration budgets, add Files:/Mode: lines, plan same-provider staggering, pre-write commit messages. See §Optimize checklist below. | Decomposition-ready plan |
| **Execute** | `"Execute the plan"` | **Orchestrator profile only.** Decompose into kanban cards, dispatch workers. Non-orchestrator profiles prefer the **board-mediated handoff**: `python3 scripts/kanban_handoff.py --plan <plan.md>` creates one hardened handoff card the dispatcher runs under the orchestrator profile (idempotent; checks its own preconditions). **Fallback only** (no gateway): start a new orchestrator session — `/profile` does **not** switch — via `hermes -p orchestrator chat`. See `plugin/data/references/profile-switching.md`. | Decomposed board |

**Critical ordering rule:** Sanity check, Harden, and Revise iterate BEFORE Optimize. Sanity check is read-only — it finds gaps. Harden closes them. Optimize formats for execution. The interaction model is: **Draft -> Sanity check -> Harden -> Revise -> repeat -> Optimize -> execute**. Never Optimize before Harden — formatting a plan with content gaps wastes tokens on cards that will be blocked or produce wrong code.

**Walk-away point:** After drafting but before execute. After Harden, the canonical copy sits in `.hermes/kanban/plans/` ? the user can return hours or days later and say "execute this plan."

### Harden checklist (WHAT — content completeness)

Run this during the Harden stage, after the initial sanity check. These items verify the plan's content is complete, correct, and well-researched. See `plugin/data/references/plan-hardening-methodology.md` for the tier-gated approach (Critical -> Important -> Nice-to-have) and verification grep suite.

0. **Canonical plan location** ? If the plan is not already at `.hermes/kanban/plans/{plan_id}.plan.md`, copy it there before other Harden edits (from the draft path, `plan_search_dirs`, or the path the user linked). Use `PYTHONPATH=scripts/lib python3 -c "from plan_paths import ensure_canonical_plan; print(ensure_canonical_plan('.', '{plan_id}', '{hint}'))"` when helpful. Sanity check should flag a missing canonical copy; Harden performs the copy and continues from the canonical file only.
1. **Declared anchors** ? Run `audit_anchors.py --strict` then `verify_anchors.py` on the canonical plan. Non-trivial code-gen cards must include `Anchor: path::symbol@Lline` in agent blocks (see `plan-file-format.md` § Declared anchors). Use `plan_parse.py suggest-anchors` for rg-backed suggestions ? paste into the plan; do not infer file?line pairing from prose. Prose-only `L123` in signal maps: sanity-check manually.
2. **No-deletions policy confirmed** — If the plan requires preserving existing code, every quarantined block has a marker tag. If the plan deletes code, the deletion is intentional and documented.
3. **Marker tag strategy** — Every commented-out or quarantined block has a consistent marker so a single search can discover all sites. If no code is being commented out (additive/restorative plan), note that marker tags are not needed.
4. **Test strategy defined** — Each section names a specific test file and assertion pattern. What behavior is being verified, not just which test file to run. **Before reporting tests as missing, try at least three discovery patterns:** `find . -name 'test_*' -o -name '*_test.*'`, `grep -rl 'def test_'`, and check `pytest --collect-only` or the project's test runner. Test files often use naming conventions you don't expect — a single narrow grep produces false negatives.
5. **Edge cases covered** — Sad-path contingencies table addresses the failure modes that matter for this plan's scope. Risks not listed are assumed BLOCKING by the orchestrator.
6. **Auto-research grounded** — Plan assumptions verified against real-world implementations, API docs, or current codebase behavior. No "probably works" assumptions. When the plan makes claims about framework/library behavior (e.g., thread cancellation, proxy timeouts, database performance) without citations, websearch the specific claim and validate it against external sources.
7. **Redundant change detection, already-shipped scan, and compaction** — For each section, check whether the desired end state already exists in `HEAD`. **Already-shipped detection:** grep the CHANGELOG and `docs/DEFERRED_FEATURES.md` for related keywords; if a plan item's fix is already live (e.g., a constant's helper function already returns 0.0 unconditionally), mark the todo as `completed` with the ship date. **Compaction:** when plan prose says "trace finalize paths to understand X" but `grep` shows the function doesn't write that field at all (e.g., `serialize_snapshot` doesn't write `retained_count`), the tracing step is unnecessary — compact the plan item to the minimal change ("one line"). Document what exists vs. what needs to be added so the worker targets the minimal change.
8. **Scope-appropriateness confirmed** — The plan doesn't bundle "nice to have" work. Deferred items are explicitly scoped out with a v2 target. Non-goals are stated.
9. **Monkeypatch paths verified** — When extracting functions from a god module to a new module, grep the test tree for `monkeypatch.setattr` and `@patch` targeting any moved function. If the plan moves a function `old_module.foo()` to `new_module.foo()`, verify the test strategy accounts for dual-patching: the internal caller in `new_module` needs its own patch. See Pitfalls § Module extraction breaks test monkeypatches.
10. **Goal-card suitability** — For each code workstream, set `goal_card: false` (default) or `goal_card: true` with `goal_rationale:` and `goal_scenario:` (`D1`–`D10`, `A1`–`A10`, or `none`). Scan `plugin/data/references/goal-card-selection.md` § Scenario index. If any workstream is `true`, set plan-level `goal_card_budget` (default **2**). Document which table row matched or which **A*** anti-pattern forced `false`. Do not mark `true` for exploration/spikes (A3) or splittable parallel lanes (A2).
11. **Simplification scan** — After verifying anchor points but before the tier-gated hardening pass, scan every plan todo item and ask: "Could this be simpler than the plan describes?" Look for: (a) analysis steps that `grep` renders unnecessary (e.g., "trace finalize paths" when the function doesn't write the field), (b) multi-step fixes where the first step invalidates later steps (e.g., discovering a constant is already 0 makes the gate logic moot), (c) prose descriptions that overstate complexity. For each simplification found, update the todo content to the minimal change and add a note explaining what was compacted.
12. **Holistic vs Surgical classification** — Every fix must be explicitly classified as **holistic** (addresses a problem globally, minimal blast radius, few files, no schema changes) or **surgical** (complex, scoped to a specific owner, may affect event buses or cross-cutting concerns). This classification guides decomposition ordering: holistic fixes run first because they unblock surgical work and reduce the blast radius for later cards. Add a classification column to the signal map or a dedicated classification section.

### Optimize checklist (HOW — kanban execution readiness)

Run this during the Optimize stage, after the plan content is hardened. These items verify the plan is formatted for decomposition and dispatch. A plan that passes Harden but fails Optimize has correct content that can't be executed.

1. **Agent prompt blocks present** — Every code-generation workstream section includes an executable `agent -p` fenced code block. Verify: `grep -c '```agent' <plan>.md` equals the number of code workstreams. Plans without these blocks are rejected at the orchestrator's attestation gate (P002).
2. **No `--model` in card bodies** — Agent-prompt blocks must not include `--model` when the assignee profile has model preferences in `config.yaml` (i.e., `model.default` is set). The profile determines the model; the card body specifies only the task. Card body policy P005 blocks cards that override profile model config at dispatch.
3. **Iteration budget estimated** — Each card's happy-path operations must fit within **35 turns**, leaving 55 for debugging within the 90-turn default. Formula: `(functions Ã 3) + (test_runs Ã 2) + (consumer_checks Ã 2) + (import_fixes Ã 2) + 2 buffer`. Cards exceeding 35 estimated turns **must be split** regardless of line count. Code relocation offers no exemption — 19 function extractions burn ~57 turns before tests even run.
4. **Files:/Mode: lines present** — Every workstream header declares `Files:` (which files the card touches) and `Mode:` (modify-only, create-only, or any). The evaluation chain verifies these at steps E001 and E002.
5. **Commit granularity aligned** — One atomic commit per kanban card. Commit messages pre-written in each section's agent block (`Commit:` line).
6. **Dependency graph drawn** — ASCII-art dependency graph with parent-child link table, parallel dispatch waves, and same-provider serialization noted. The orchestrator uses this to run `hermes kanban link`. A prose "implementation order" sentence is not sufficient — draw the graph.
7. **Card order finalized, then labeled** — **Arrange first, label second.** Use the dependency graph to lock dispatch order (gate -> holistic fixes -> parallel waves -> tests -> audit). Only after order is final, write the `## Kanban optimization` section with sequential ordinals `#### Card 1`, `#### Card 2`, â¦ `#### Card N`. Do not label while still reordering. Forbidden in the optimization section: letter labels (A, B, C), draft workstream names (`Workstream 2a`, `WS3`), or non-contiguous numbers (Card 3, Card 6, Card 2). Draft-phase `###` sections may keep descriptive names; **Kanban optimization** is the canonical dispatch sequence. See §Kanban optimization section.
8. **Same-provider staggering planned** — Cards on the same provider serialized via parent-child links (or documented as auto-serialized by the dispatcher). See the provider-strategy wiki page for multi-provider fan-out and fallback configuration.
9. **Line budget computed** — Total net line changes estimated across all cards. No single card exceeds 200 net lines. The `line_budget` field in the frontmatter summarizes the plan total.
10. **Card granularity verified** — No card bundles more than 2 distinct file-level changes. Cards with 3+ files are split regardless of line count. Same-file cards that touch the same file are serialized via parent-child links.
11. **Same-file merge verification** — When a card touches a file that a prior card also modified, the card body MUST include instructions to rebase on the prior card's branch before working. Card 10 removed `_merge_fetch_scope_exhausted` that Card 2 added because Card 10 was created from staging (which didn't have Card 2's commits yet). The dependency graph specified Card 2 -> Card 10 parent-child ordering, but the child must still merge the parent's changes. Add to card body: `**Before modifying {file}, rebase on {parent-card-branch}: git fetch origin {parent-branch} && git merge {parent-branch}.**`
12. **Cross-section contradictions checked** — No two sections modify the same file in conflicting ways. If section A creates function X and section B deletes function X, flag as contradiction. If section A modifies lines 100–200 and section B modifies lines 150–250, flag as overlapping.
13. **Optimization attestation** — All checklist items recorded in the plan frontmatter under `optimization_checklist` with `status: pass`. The orchestrator's Step 0c reads this for attestation.
14. **Plan committed and pushed to `${working_branch}`** ? The hardened, optimized plan is committed to `${working_branch}` and pushed to `origin/${working_branch}`. Workers branch their worktrees from `${working_branch}` and need the full plan file for autonomous troubleshooting. Verify: `git log --oneline -1 -- .hermes/kanban/plans/<plan>.md` shows a recent commit on `${working_branch}` AND `git fetch origin ${working_branch} --dry-run` confirms the push.
15. **Card body self-containment verified** — Every agent-prompt block includes inline code for function bodies, types, and constants the worker can't derive from file paths alone. Section references (`§3b`) are acceptable for narrative context but NOT for implementation details. If a card says "implement curiousPresentationComplete per plan §3b", the function body MUST be included in the agent-prompt block. Workers without plan file access will block on "plan detail missing."
16. **Diff cap present** — Every agent-prompt block over 50 lines includes an explicit scope guard: `"If your diff exceeds 150 lines net, STOP and report what's remaining."` This prevents scope explosion (observed: 1654-line diff on a 91-line card). Smaller cards don't need this.
17. **Goal-card acceptance encoded** — For each `goal_card: true` workstream: add an **`Acceptance:`** subsection (judge-facing; use template in `plugin/data/references/goal-card-selection.md`); optional `goal_max_turns` in frontmatter (default **20**, must not exceed `goals.max_turns`). Run `python3 hermes-kanban-advanced-workflow/scripts/verify_goal_cards.py --plan <plan>.md` before attestation.
18. **Executive summary documentation-ready** — For plans that serve double-duty as implementation plans AND documentation artifacts (linked from `docs/` or referenced by other plans), the executive summary must be self-contained: a reader who never opens the evidence matrix must understand the problem, root causes, what's already fixed, what each phase delivers, and target metrics. Anti-pattern: a flat severity table. Required structure: (a) one-sentence opening, (b) root causes table with fix-complexity column, (c) already-shipped items, (d) remediation-at-a-glance phase table, (e) key performance targets in before/after format, (f) closing line with blast radius.
19. **Acceptance surface audit** — Each YAML todo -> list every deliverable (code path, test file, operator script, deploy step). If more than one surface, split the todo or add numbered `Acceptance:` items in the agent block.
20. **Call-site audit** — For any "wire X to Y" todo, `rg` all callers; agent block lists every `Call-sites: path:symbol` or names a shared resolver both paths must use.
21. **Files completeness** — For UX/helper changes, `rg` the symbol across the repo; all subscriber-facing call sites appear in `Files:` or an explicit follow-up card.
22. **Verification taxonomy** — `verification-local` (pytest only) vs `verification-deploy` (operator + deploy); never mark deploy todos `completed` on merge to staging alone.
23. **Same-file graph** — Mark cards that touch the same production file; planner sets `wave_parent` chain (not parallel gate-only siblings) for those files.
24. **Multi-parent cap** — Test/doc cards: max **2** production parents unless `Mode: read-only`; otherwise split fixtures by file.
25. **Spec precision** — Non-trivial agent blocks include `Spec:` + `Anchor:` + `Examples:`; `Contracts:` in `## Kanban optimization` pins every `Call-sites:` symbol; ban vague integration verbs unless followed by a concrete operation (see `plan-file-format.md`).
26. **Plan memory seed** — At end of Optimize, write `acceptance_matrix` (or equivalent) into plan frontmatter or `.hermes/kanban/memory/{plan_id}.json` for decompose to expand.
27. **Markup-safe placeholders** — No `<word>` slots anywhere in the plan file; use `{word}` per §Plan file format.

### Frontend decomposition (route micro-cards)

When a workstream changes subscriber-visible layout or motion:

1. **`{feature}-ux-helpers`** — pure functions/hooks with unit tests (no route shell edits).
2. **`{feature}-route-wiring`** — wire helpers into the route shell (`Files:` includes `{ui_stack.page_glob}`).
3. **`{feature}-route-layout`** — DOM order + `Acceptance (layout):` grep bullets (line order before/after slot anchors).
4. **`integration-verify`** — `Type: verification-local` card after the route-layout group; runs pytest + `kanban_layout_acceptance.sh` paths.
5. **Deploy smoke** — `Type: verification-deploy` with `Deploy:` line; requires `.hermes/kanban/card-attestations/{plan_id}-{card_key}.json` before archive.

Declare `Surface-slots:` in the plan and mirror host paths in overlay `ui_stack` (`frontend-neutrality.md`). `verify_optimization.sh` checks 19–21 enforce presentation acceptance at Optimize time.

### System-agnostic path convention

All documentation, skill files, and wiki pages MUST use system-agnostic paths. Never write platform-specific paths:

| Avoid | Use | Rationale |
|-------|-----|-----------|
| IDE-native draft paths in host tools | `.cursor/plans/`, `.agent/plans/`, etc. | Draft anywhere; **Harden** copies to `.hermes/kanban/plans/` (kanban SSOT). Extend resolver via `plan_search_dirs` in overlay |
| `~/.hermes/` | `$HERMES_HOME/` | Hermes state directory is an environment variable — supports custom installs |
| `/mnt/c/`, `/mnt/e/` | Native filesystem paths | WSL DrvFs paths are platform-specific and blocked by preflight |

The trigger phrase table in the interaction model, the adoption protocol, and all script invocations must follow this convention. Historical plan files and changelogs are exempt — they're immutable records of what was built.

**CLI Agent terminology:** In KPI/metrics sections, use **CLI Agent** (vendor-neutral). In coding-agent install rosters, use the vendor product name for the configured binary (e.g. the display name from `plugin/coding_agent.py`). Metrics stay portable across coding agents; rosters tell operators what to install.

**README formatting pitfalls:** After any markdown edit, check for URL-encoded HTML artifacts (`%3C` wrappers), HTML entities (`&gt;`/`&lt;`), broken code fences, triple blank lines, and mixed table formatting. See `plugin/data/references/readme-formatting-pitfalls.md` for the full checklist.

### Scope-appropriateness gate

Before planning, check whether the kanban-advanced workflow is even the right tool. See the README § Why NOT Kanban — the workflow is overkill for single-file fixes, research tasks, no-code plans, small repos, and sub-2-minute latency needs. If the task falls into any of those categories, recommend `/goal` or direct agent invocation instead.

**Three-tier scope gate:**

| Scope | Tool |
| --- | --- |
| Tiny / no board | `/goal` or `agent -p` |
| Multi-lane, governed delivery | kanban-advanced (default **one-shot** cards) |
| One stubborn outcome lane on a board | kanban-advanced + `--goal` on **0–2** cards after Harden (`plugin/data/references/goal-card-selection.md`) |

Requires **Hermes â¥ 0.16.0** for `--goal` on `hermes kanban create`.

## Plan optimization (summary)

The Harden and Optimize checklists above replace the older single "12-item checklist." See §Harden checklist for content-completeness verification (anchor points, edge cases, redundant changes, auto-research) and §Optimize checklist for kanban-execution-readiness verification (agent blocks, iteration budgets, dependency graphs, Files:/Mode:).

### User gate

Confirm the plan's scope with the user (or product brief) before any decomposition:

- Does the plan address the *minimal* viable change, or does it bundle "nice to have" work?
- Are there any sections that should be deferred to a later plan?
- If the plan was generated from operator prose, does it accurately reflect the user's intent?

If the user gate reveals scope creep or misalignment, trim the plan *before* spawning cards. It is cheaper to edit a markdown plan than to abort five in-flight kanban tasks.

## Plan structure

Every plan must have:

1. **YAML frontmatter** with `name`, `plan_id`, `overview`, `line_budget`, `contingencies`, and `todos` list. Optional: `goal_card_budget` (default 2), per-workstream `goal_card`, `goal_scenario`, `goal_max_turns`, `goal_rationale` (see `plugin/data/references/goal-card-selection.md`).
2. **Clear section-per-change.** Each fix or feature gets its own `###` section with:
  - File path(s) — where the change belongs and how it integrates
  - Implementation approach — what's needed to fulfill the requirement
  - **`agent -p` fenced block** — the exact command the worker executes (see template below)
  - Test strategy
  - Edge cases
3. **File-level granularity.** Never describe a change that spans 3+ files in one section — split it.
4. **Explicit dependencies.** If section B depends on section A, say so. The orchestrator uses this for parent-child linking.

Build what's needed first. Flag what's wanted as optional. When in doubt, implement the simplest solution that fulfills the requirements — and ask before adding anything beyond them.

### Card body agent-prompt template

Every code-generation card body must end with a fenced `agent -p` block. This is what the worker extracts and executes directly.

**Non-trivial cards** (new/changed signatures, 2+ files, or non-trivial logic) use the full contract shape below. **Trivial cards** (rename, one-line constant, config-only) may omit `Spec:` / `Anchor:` / `Examples:`.

```agent
agent -p "Implement {one-line task}.
plan_id: {plan_id}
Files: {path} ({mode}), â¦
Mode: modify-only
Anchor: {class/function + approx line}
Spec:
- Signature: {exact def/types; raised exceptions}
- Constants: {NAME = value}
- Data shape: {field names + types}
- Behavior: {numbered steps; edge cases}
- Examples: {>=1 happy; 1 representative edge}
Call-sites: {path:symbol, â¦} or none
Forbidden: {never-tier — paths, deps, no signature changes elsewhere}
Acceptance:
- Done when: {observable assertion / passing test name}
- Verify: {exact rg/pytest command}
Self-audit: before commit, list each Spec/Acceptance item and confirm met; revert any file not in Files:
Tests: {test command}
Commit: {commit message}
Diff cap: if >150 net lines, STOP and report.
Do NOT push to ${working_branch} — commit to worktree branch only."
```

The worker's Step 4 extracts this block via regex, executes it, and monitors the agent. No prompt construction, no re-reading the body, no debating what model to use.

> **Model selection belongs to the profile, not the card body.** Do NOT add `--model` or `--output-format` flags. The profile's `config.yaml` determines the model. Card body policy P005 blocks cards that attempt to override profile model config.
> **Model name requirement:** If the valid model set is unknown, omit `--model` entirely — the CLI auto-selects.

### Ordinal card body template (AEP cardinal analysis pattern)

For complex tasks (sad-path recovery, policy enforcement, infrastructure changes), use the 8-question ordinal format. Each "not" variant maps to a specific evaluation chain step:

```markdown
### Task: {title}

**What is Needed?** {outcome description}
**How is it Needed?** {happy path}

**What is Wanted?** {desired outcome}
**How is it Wanted?** {happy path for desired}

**Where does it belong?** {file paths, workspace}
**How does it belong there?** {integration points}

**When is it received?** {environmental conditions}
**How will it be received?** {verification steps}

**What is NOT Wanted?** {failure modes -> maps to error codes E001-E006}
**How is it NOT Wanted?** {sad paths -> maps to recovery actions}

**Where does it NOT belong?** {restricted paths -> maps to E002/E009/E011}
**How does it NOT belong there?** {boundary enforcement -> maps to card policy P001-P004}

**When is it NOT received?** {environmental failures -> maps to E007/E008/E012}
**How will it NOT be received?** {governance infra failures -> maps to A001-A003/E013}

Files: path/to/file.py
Mode: modify-only
Tests: {command}
Commit: {message}
```

## Policy profiles

The orchestrator runs `kanban_card_policy.py` with one of three profiles:

| Profile | Behavior | Use case |
|---------|----------|----------|
| `advisory` | Warn on violations, allow dispatch | Human-supervised runs, trusted plans |
| `balanced` (default) | Block violating cards | Normal operations |
| `strict` | Block + notify operator via gateway | Walk-away / unattended runs |

Set at init (CLI or dashboard) as `policy_profile` in `kanban-config.yaml` and `KANBAN_POLICY_PROFILE` in `.env`. Override per-run with `--profile` on `kanban_card_policy.py` or `KANBAN_POLICY_PROFILE` in the shell.

| Gate | `advisory` | `balanced` | `strict` |
|------|------------|------------|----------|
| Card body policy | Warn, allow dispatch | Block card | Block + log to `interventions.jsonl` |
| Evaluation chain | Warn, allow complete | Block task | Block + log to `interventions.jsonl` |
| Board / plan validation | Failures -> warnings | Warnings pass with review | Warnings -> block |

Strict profile logs governance blocks to `.hermes/kanban/logs/interventions.jsonl` and bumps the intervention counter. Gateway push still requires `kanban-advanced:kanban-notify` delivery setup.

## Filesystem coherence

The agent's working copy must live on a single coherent filesystem. Cross-mount paths, network mounts, OS-translation boundaries (e.g. WSL DrvFs `/mnt/` mounts, macFUSE, SSHFS), and symlinks that cross filesystem boundaries can cause silent state corruption during long-running multi-agent workflows.

**Rule:** Confirm `pwd` resolves to a native filesystem path before running any kanban operation. If the working copy is on a translated or mounted path, clone it to a native location first. This check is part of the preflight checklist (see `kanban-advanced:kanban-preflight` § Filesystem coherence check).

## Commit cadence

After completing every section of a plan, commit and push before starting the next. This rule ensures that a runtime crash, gateway timeout, or agent restart loses at most one section of work — not the entire plan run.

## Sad-Path Contingencies

Before decomposition, every plan must include a contingencies table. If a risk is not listed here, the orchestrator assumes it is BLOCKING and will halt on first failure.

| Risk | Probability | Impact | Mitigation | Auto-retry |
|---|---|---|---|---|
| `preflight` hard-fail | Low | BLOCKING | Fix environment, re-run preflight.sh | No — manual fix required |
| `preflight` degraded | Medium | DEGRADED | Warn, proceed with reduced parallelism | Yes — 1 retry with fresh session |
| Agent auth failure | Low | BLOCKING | Check CURSOR_API_KEY / auth.json | No — re-auth required |
| Agent timeout (>900s) | Medium | BLOCKING | Split card into smaller chunks | Yes — 1 retry before block |
| Test failure post-commit | Medium | BLOCKING | Revert, re-plan, re-execute | No — fix code first |
| Same-file collision (no parent link) | Low | BLOCKING | Add `hermes kanban link` in plan | No — plan edit required |
| Token tracking failure | Low | BLOCKING | Verify `scripts/token_tracker.py` import | No — fix imports first |
| Gateway notification unreachable | Low | DEGRADED | Log to file, continue silently | Yes — 2 retries with backoff |
| Evaluation chain missing (E013) | Low | BLOCKING | Restore kanban_evaluation_chain.py | No — restore file first |
| Attestation stale (A002) | Medium | BLOCKING | Re-run preflight + attestation | Yes — 1 retry |

### Gating rules

- **BLOCKING impact** -> Halt decomposition. Notify user with specific fix required. Do NOT auto-retry.
- **DEGRADED impact** -> Log warning, reduce parallelism or skip non-critical steps, continue. Auto-retry once if pattern supports it.
- **Probability estimates** must be grounded in prior postmortems (`kanban-advanced:kanban-postmortem.md`).

## Line budget analysis

Before decomposing a plan into cards, compute the expected net line changes AND the estimated agent iterations. See `plugin/data/references/iteration-budget-estimation.md` for the formula, hard ceiling of 35 turns, and real Phase 2 outcomes.

1. **Count additions** — new lines the card will introduce.
2. **Count deletions** — existing lines the card will remove.
3. **Count rewrites** — lines modified in-place (count as 1 addition + 1 deletion).
4. **Estimate iterations** — count distinct operations: function extractions (~3 turns each), test runs (~2 turns), consumer verifications (~2 turns), import fixes (~2 turns), commits (~1 turn). The happy path should consume no more than **40 turns**, leaving 50 for debugging within the default **90-turn budget**.

Net change = additions + deletions + rewrites.

| Net lines | Iterations (est.) | Action |
|---|---|---|
| â¤ 50 | â¤ 15 | Preferred — review for bundling with sibling changes |
| 51–100 | 15–30 | Normal — proceed |
| 101–200 | 30–50 | Warning — verify granularity; split if touching >2 files |
| > 200 | > 50 | **FLAG — must split.** Either line count or iteration estimate exceeds safe bounds. |

> **Code relocation is NOT exempt from splitting.** Moving 300 lines of existing code (add+del=600, net=30) is still a large card. The agent must read, understand, copy, verify imports, remove, re-export, test, and commit — each step consumes iterations. A 19-function extraction with full test suite easily burns 60+ happy-path turns and exhausts the 90-turn budget on any failure. Split relocation cards the same way you split greenfield cards. See `plugin/data/references/iteration-budget-case-study.md` for a worked example (WS9: 19 functions, 72 happy-path turns, exhausted 90-turn budget).

## Section template

```markdown
### Job name (Priority)

**File:** `path/to/file.py` L{line range}

**Approach:**
{concrete implementation steps}

**Tests:**
{test file and specific cases}

**Card body:**

(Single `agent` fence — see §Card body agent-prompt template; use {placeholders}, not angle brackets.)
```

## Kanban optimization section (mandatory output)

After the Optimize checklist passes, append (or rewrite) a **`## Kanban optimization`** section. `kanban_decompose.py` reads **only** this section — draft `###` headings elsewhere are not dispatch ordinals.

**Workflow: arrange first, label second**

1. **Arrange** — Order cards by the dependency graph (gate -> holistic fixes -> parallel waves -> tests -> audit). Resolve merges and splits before naming.
2. **Label** — Renumber in that order as `#### Card 1 — {title}`, `#### Card 2 — {title}`, â¦ through `#### Card N`. Integers only, contiguous from 1, no gaps, no out-of-order appearance in the file.
3. **Cross-reference** — Agent blocks and `wave_parent` / `ordinal_parent` fields use `Card N`, not draft names (`Workstream 2a`, `WS3`, letter labels).

**Forbidden in `## Kanban optimization`:** `#### Card A`, `#### Workstream 3`, `#### WS2b`, or numeric labels that skip or scramble order (e.g. Card 3, Card 6, Card 2, or file order G, C, A).

**Minimal shape:**

```markdown
## Kanban optimization

### Dependency graph
â¦ASCII graph + parent-child table (dispatch order)â¦

#### Card 1 — Gate (manual)
plan_id: â¦
wave: 1
â¦

#### Card 2 — {first implementation card}
plan_id: â¦
files:
  - path/to/file.py
mode: modify-only
wave: 2
wave_parent: card1
(agent-prompt fenced block here)

#### Card 3 — {next card in dispatch order}
â¦
```

Run `bash hermes-kanban-advanced-workflow/scripts/verify_optimization.sh --plan <plan>.md` — check **15** enforces sequential `Card N` labeling.

## Decomposition rules the orchestrator will apply

- One section = one card (unless bundled changes touch the same single file)
- Same-file sections get serialized via parent-child links
- Disjoint-file sections run in parallel
- Tests section always gates on all implementation sections
- Final audit section always gates on tests

## Pitfalls

- **Too coarse.** "Fix all extraction issues" -> 3+ cards. Split by file.
- **Too fine.** "Change variable name from x to y" -> merge with sibling changes to same file.
- **Missing dependencies.** If section B reads a function section A creates, mark it as dependent.
- **No file paths.** "Modify the orchestrator" -> the decomposer can't route it. Always include concrete paths.
- **No agent -p block.** Cards without `agent -p` blocks are blocked by card body policy (P002). Every code-gen card must have one.
- **Working copy on a cross-mount path.** Silent write corruption; preflight blocks before any cards are created.
- **No per-section commits.** A gateway timeout wipes the whole run; commit cadence limits loss to one section.
- **Plan file not on worktree branches.** Commit the hardened plan to `${working_branch}` before dispatching.
- **Wrong tool for the job.** Not every task needs kanban. See the scope-appropriateness gate above and the README § Why NOT Kanban for guidance.
- **Module extraction breaks test monkeypatches.** When a function is moved from a god module (e.g., `large_module.py`) to a new extracted module, any test that uses `monkeypatch.setattr(tf, "moved_function", ...)` on the original module will silently fail — the patched facade re-export doesn't reach internal callers in the new source module. The fix is dual-patching: add a matching `monkeypatch.setattr("new.module.moved_function", ...)` alongside the original. During planning, grep for `monkeypatch.setattr` or `@patch` targeting any function being extracted, and note the dual-patch requirement in the test strategy for that workstream.
- **`--model` in card bodies bypasses profile config.** The profile's `config.yaml` determines which model to use — the card body specifies only WHAT to do, not HOW. Putting `--model` in an agent-prompt block overrides the user's model preferences. Card body policy P005 blocks these cards at dispatch. Always omit `--model` from agent-prompt blocks. The worker uses the profile's configured model.
- **`hermes kanban create --parents` flag is broken.** The `--parents` flag on `kanban create` does not work. Create cards without it, then wire dependencies with `hermes kanban link <parent> <child>` after all cards exist. Verify links with `hermes kanban show <child>`.
- **Code relocation is not free.** Moving functions between files still consumes agent iterations — reading, copying, verifying imports, removing, re-exporting, testing, committing. Estimate iterations per operation (see Line Budget Analysis) and split accordingly. A 19-function extraction is easily 3+ cards.
- **Plan lacks holistic vs surgical classification.** When a plan lists all fixes at equal priority without classifying them as holistic (global, few files) vs surgical (complex, cross-cutting), the decomposition can't optimize ordering — holistic fixes should dispatch first because they unblock surgical work and reduce blast radius. Add a classification column to the signal map before optimizing for Kanban.
- **Labels before order.** Assigning `Card A` / `Workstream 2a` / `WS3` while still reordering produces scrambled dispatch (`G, C, A` or `3, 6, 2`). Finalize execution order in the dependency graph first, then write `## Kanban optimization` with `#### Card 1` â¦ `#### Card N` in that order.
- **Angle-bracket placeholders.** Using `<plan_id>`, `<command>`, or `<card2-branch>` in plan prose — breaks markup preview; use `{plan_id}` per `plan-file-format.md`.
- **Grep calibration produces false negatives for test discovery.** A single `find . -name 'test_*.py'` won't match `*_test.py`, `tests/`, `spec/`, or non-Python test runners. Before concluding tests are missing, try at least three patterns: `find . \( -name 'test_*' -o -name '*_test.*' -o -name '*_spec.*' \)`, `grep -rl 'def test_'`, and `pytest --collect-only --quiet 2>/dev/null`. A false-negative test report wastes time and erodes trust in the hardening pass.

## References

- `plugin/data/references/plan-file-format.md` — markup-safe placeholders, `Spec:` contract block, acceptance surfaces, fence rules
- `plugin/data/references/plan-anchor-verification-pitfalls.md` — common inaccuracy patterns when verifying plan claims against the codebase
- `plugin/data/references/worker-actionability-audit.md` — per-section actionability checklist before decomposition
- `plugin/data/references/single-coherent-filesystem.md` — filesystem coherence and commit cadence incident analysis
- `plugin/data/references/documentation-style.md` — system-agnostic paths, CLI Agent vs vendor binary naming, wiki table formatting, user-authored prose preservation
- `plugin/data/references/documentation-sanity-check.md` — stale reference detection, code fence integrity, table formatting, package tree maintenance
- `plugin/data/references/readme-formatting-pitfalls.md` — URL-encoded HTML artifacts, HTML entities, broken code fences, triple blanks, user-authored prose preservation
- `plugin/data/references/vanilla-kanban-known-issues.md` — upstream Hermes Agent kanban bugs mapped to structural workarounds (dependency gating, workspace isolation, dispatcher resilience, root card anti-patterns)
- `plugin/data/references/iteration-budget-case-study.md` — worked example: WS9 19-function extraction exhausted 90-turn budget; how to calculate operation counts and split correctly
- `plugin/data/references/governance-sad-path-audit.md` — full flowchart trace of every transition with 23 sad paths, governance coverage assessment, and prioritized gaps (kanban-advanced:kanban-orchestrator reference)
- `plugin/data/references/plan-hardening-checklist.md` — 11-item first-pass hardening checklist (Critical -> Important -> Nice-to-have) + redundant change detection pattern; runs between sanity check and optimization
- `plugin/data/references/phase-transition-hardening.md` — re-verifying line numbers, fleshing out placeholder workstreams, dependency graphs, and verification gates when reactivating a deferred plan phase
- `plugin/data/references/plan-hardening-methodology.md` — tier-gated hardening pass (Critical -> Important -> Nice-to-have) after a sanity check; verification grep suite; before/after report template
- `plugin/data/references/dependency-graph-format.md` (kanban-advanced:kanban-orchestrator) — ASCII-art dependency graph format for parent-child link planning
- **Wiki: provider-strategy** — multi-provider fan-out, rate-limit prevention, fallback configuration (for same-provider staggering decisions in checklist item 9)
- **Wiki: Why NOT Kanban** (README § Why NOT Kanban) — when to skip the workflow entirely (scope-appropriateness gate before planning begins)

