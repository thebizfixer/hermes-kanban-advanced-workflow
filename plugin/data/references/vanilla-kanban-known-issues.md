# Vanilla Hermes Agent Kanban — Known Issues & Workarounds

> **Purpose:** Map known vanilla `hermes kanban` bugs to workarounds so the orchestrator can plan around them before dispatching cards. Updated as new issues are discovered or fixed upstream.

**Sibling:** [`planned-features.md`](planned-features.md) — deferred capabilities that need upstream Hermes APIs or unfinished plugin work (not live bugs).

## How to use

The orchestrator loads this document during **Step 0b (Preflight)** and again during **Step 1 (Understand the goal)**. For each issue, check whether the current plan is exposed. If yes, bake the workaround into the plan's decomposition strategy, card creation order, and workspace configuration.

Each issue entry includes:
- **Upstream ref:** Link to the Hermes Agent GitHub issue
- **Symptom:** What the operator sees when the bug hits
- **Exposure:** Conditions that trigger it
- **Workaround:** Structural fix to bake into the plan
- **Detection:** How preflight or the orchestrator can detect exposure before dispatch

---

## Dependency Gating

### Dispatcher claims `ready` cards before parent links exist (block-on-create required)

**Upstream context:** [nousresearch/hermes-agent#16102](https://github.com/NousResearch/hermes-agent/issues/16102) (Kanban RFC) — dispatcher atomically claims `ready` tasks via compare-and-swap; promotion is `todo → ready` when all parents are `done`.

**Symptom:** Dependent cards dispatch and run before parent links are established, or before parents complete. `hermes kanban link` added after creation cannot retroactively stop a card the dispatcher already claimed — typically **<1 second** after create.

**Exposure:** Any plan that creates cards without immediate blocking and links parents afterward.

**Workaround (kanban-advanced standard):**
1. `hermes kanban create` (lands `ready` in v0.15.x)
2. **`hermes kanban block <id>` immediately** — same turn, before stagger sleep
3. Link all parent-child relationships with `hermes kanban link`
4. Start `auto_unblock.sh` cron (every 1m) — unblocks each card when all parents are `done`
5. **Gate pattern:** gate card blocked on create; all impl cards link to gate; orchestrator completes gate after `validate_board.sh`; cron releases wave 1

**Do NOT use `--triage` as the workaround** when `kanban.auto_decompose=false` (kanban-advanced default) — triage cards never promote. See triage stuck entry below.

**Detection:** `validate_board.sh` check 5; preflight: any `running` card whose parents are not `done`.

```bash
# Quick check for cards that dispatched before parents completed
hermes kanban list | awk '/▶.*ready/ {print $2}' | while read tid; do
  hermes kanban show "$tid" | grep -q 'parents:.*t_' && echo "WARN: $tid has parents but is ready"
done
```

**Agent FAQ:** `wiki/decomposition-workflow.md`

### Running parent blocks child promotion (#24489)

**Upstream ref:** [nousresearch/hermes-agent#24489](https://github.com/NousResearch/hermes-agent/issues/24489)

**Symptom:** Child tasks linked to a parent stay in `todo` forever while the parent is `running`. Dispatcher only promotes `todo → ready` when **all** parents are `done` — a `running` orchestrator parent does not satisfy that check. `link_tasks()` also demotes children linked to non-`done` parents from `ready → todo`.

**Exposure:** Parent-child graphs where the parent orchestrator stays `running` while coordinating children (War Room pattern). Less common in kanban-advanced because root/gate cards are **completed** immediately after decomposition, not left `running`.

**Workaround:**
1. Complete orchestrator placeholder cards (root, gate) promptly — do not leave them `running` as dependency parents
2. Use the gate as a `done` dependency root: complete gate after validation to release wave 1
3. Avoid linking implementation children to a long-lived `running` orchestrator task

**Detection:** `hermes kanban show <child>` shows parent `status: running` while child is `todo` with no dispatch.

### link_tasks() demotes blocked children with multi-parent links (#24489 — same bug, different trigger)

**Upstream ref:** [nousresearch/hermes-agent#24489](https://github.com/NousResearch/hermes-agent/issues/24489)

**Symptom:** Cards created via block-on-create (kanban-advanced standard) unblock to `todo` instead of `ready` when they have multiple parents. The card was created `ready`, immediately blocked, then linked to multiple parents — at least one not yet `done`. `link_tasks()` demotes it from `ready` → `todo` despite the card being `blocked`. When later unblocked, it returns to `todo` and never dispatches (stuck with `auto_decompose: false`).

**Exposure:** Any card with **2+ parents** where at least one parent is not `done` at link time. Single-parent cards are unaffected because the single parent (Gate) is blocked at link time — `link_tasks()` only triggers on non-`done` parents, and a blocked parent isn't `running`, so the demotion path may not fire. Multi-parent cards link to an implementation parent that IS `running` or in an intermediate state, triggering the demotion.

Observed in kanban-standard-smoke-test:
- Card 2 (parents: Card 1 + Gate) → unblocked to `todo`
- Card 5 (parents: Cards 3 + 4) → unblocked to `todo`
- Cards 1, 3, 4 (single parent: Gate) → unblocked to `ready` ✓

**Workaround:**
1. **Auto-unblock recovery (preferred):** After unblocking a card, check its status. If it landed in `todo`, use `hermes kanban promote <id>` to move it to `ready`. The `auto_unblock.sh` script should do this automatically.
2. **Decompose ordering:** Create and link single-parent cards first. For multi-parent cards, wait until all implementation parents are `done` before linking — but this breaks block-on-create (dispatcher race).
3. **Post-decompose fix-up:** After all cards are created and linked, the orchestrator runs a final pass: for every blocked card with all parents `done`, unblock → check status → promote if `todo`.

**Detection:** After gate completion, `hermes kanban list` shows `◻ todo` for cards that should be `▶ ready`. Run: `hermes kanban show <id>` — if `parents:` are all `done` but status is `todo`, the demotion fired.

**Fix target:** `auto_unblock.sh` (or `auto_unblock_core.sh`) — add a post-unblock status check and promote `todo` → `ready`.

### `--initial-status blocked` can race to `ready` (observed)

**Upstream ref:** Not filed upstream as of 2026-06-10. Related reliability surface: [#35986](https://github.com/NousResearch/hermes-agent/issues/35986).

**Symptom:** Card created with `--initial-status blocked` appears in `ready` or is claimed by the dispatcher before dependency links exist.

**Exposure:** Any script or orchestrator using `--initial-status blocked` instead of a separate block call.

**Workaround:** Create normally, then `hermes kanban block <id>` in the same turn. `kanban_decompose.py` uses `block_after=True` (separate block call). Never pass `--initial-status blocked`.

### `hermes kanban block` only applies to `ready` (v0.15.0+)

**Upstream ref:** [Hermes v0.15.x upgrade notes](hermes-v0.15.0-upgrade.md); [kanban docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban).

**Symptom:** `hermes kanban block` fails or no-ops on `todo` or `triage` cards.

**Exposure:** Workflows that try to create in `todo` then block.

**Workaround:** Default create lands `ready` — block immediately. Do not rely on creating in `todo` first.

### Archived parents silently promote children (#30417 Bug 3)

**Upstream ref:** [nousresearch/hermes-agent#30417](https://github.com/nousresearch/hermes-agent/issues/30417)

**Symptom:** Archiving a parent card causes its children to silently promote from `todo` → `ready`, bypassing dependency checks. The dispatcher then claims them.

**Exposure:** Archiving any card that is a parent of other cards.

**Workaround:**
1. Never archive a parent card until all its children have completed
2. If a parent must be removed, block it (not archive) and add a comment explaining why
3. Archive only after all children are `done`

**Detection:** Before archiving any card, run `hermes kanban show <id>` and check `children:` line. If non-empty, abort the archive.

### `--parents` flag silently ignored

**Symptom:** `hermes kanban create ... --parents <id>` returns success but the parent link is not established. The card dispatches immediately with no dependency gating.

**Exposure:** Whenever `--parents` is used during card creation.

**Workaround:** Never use `--parents`. Always create the card first, **block immediately**, then use `hermes kanban link <parent> <child>` separately. Verify with `hermes kanban show <child>` that `parents:` lists the expected IDs.

**Detection:** After any `hermes kanban create --parents`, immediately run `hermes kanban show <child>` and grep for `parents:`. If empty, the flag was ignored — block the card and link manually.

### `kanban.auto_decompose` duplicates manually-created cards (v0.15.0+)

**Upstream ref:** v0.15.0 config default; [umbrella #35986](https://github.com/NousResearch/hermes-agent/issues/35986) Gap 3 (orphaned triage).

**Symptom:** Unexpected stub child cards appear after creating a root or triage card. Manually-created implementation cards duplicate or conflict.

**Exposure:** `kanban.auto_decompose: true` (Hermes default) while using kanban-advanced manual decomposition from an optimized plan.

**Workaround:**
```bash
hermes config set kanban.auto_decompose false
```
kanban-advanced init sets this automatically. Never run `hermes kanban decompose <root_id>` on pre-optimized plans.

**Detection:** `hermes kanban list` shows cards not present in the plan's Kanban optimization section.

### `--triage` dependent cards stuck when `auto_decompose=false`

**Symptom:** Cards in `triage` never promote. `hermes kanban promote` fails: "promote only applies to 'todo' or 'blocked'."

**Root cause:** Triage exit requires dispatcher + `kanban_decomposer` aux path. With `auto_decompose=false`, nothing promotes triage cards.

**Workaround:** Archive and recreate with block-on-create (see first entry in this section). Never use `--triage` for dependent implementation cards.

**Detection:** Cards stuck in `triage` >5 minutes with `auto_decompose=false` in `hermes config show`.

---

## Workspace Isolation

### Concurrent agents corrupt each other's work (shared worktree)

**Symptom:** Multiple agents modifying the same files in the same directory. Files created by one agent are deleted by another. Changes to shared files (e.g., `large_module.py`) are lost. Iteration budget wasted on conflict recovery.

**Exposure:** Any two cards that use the same `--workspace` path. Especially dangerous when cards touch the same file.

**Workaround:**
1. Give every card a **unique absolute worktree path**: `--workspace "worktree:/tmp/wt-<card-name>"`
2. Never use the main repo path (`/home/user/project`) as a workspace for multiple cards
3. Never use relative paths (`worktree:.`) — the dispatcher requires absolute paths
4. If omitting `--workspace`, the dispatcher defaults to `scratch` — no source code, zero output

**Detection:** During preflight, check `git worktree list`. Flag if any two active cards share the same worktree path.

### Scratch workspace produces zero output

**Symptom:** Agent runs to completion (or iteration limit) but produces no file changes. All `Files:` targets show zero diff.

**Exposure:** Creating a code-generation card without `--workspace worktree:<abs-path>`. The dispatcher defaults to `scratch`.

**Workaround:** Always specify `--workspace worktree:<abs-path>` for every code-generation card. The only exception is report/analysis cards with no codebase dependency.

**Detection:** Evaluation chain Step 6 (E006_ZERO_OUTPUT) catches this post-hoc. Preflight can check: any code-gen card without `worktree` in its workspace config is at risk.

---

## Dispatcher Resilience

### No circuit-breaker for repeated bails (#29320) — ✅ resolved in v0.15.0

**Upstream ref:** [nousresearch/hermes-agent#29320](https://github.com/nousresearch/hermes-agent/issues/29320)

**Status:** Resolved upstream. Hermes v0.15.0 added `kanban.failure_limit` (default: 2), which auto-blocks a task after N consecutive non-success attempts for the same task/profile (spawn_failed, timed_out, or crashed). This is a built-in circuit-breaker.

**Symptom (pre-v0.15.0):** A worker hits the same failure on every retry. The dispatcher keeps re-dispatching it, burning tokens on each cycle.

**Current behavior (v0.15.x):** After `failure_limit` consecutive failures, the dispatcher blocks the card automatically. No additional workaround needed — the built-in circuit-breaker handles this. The orchestrator's salvage pattern still handles iteration-limit cards with committed work.

### Gateway restart risks DB corruption (#30908) — ⚠️ substantially mitigated in v0.15.0

**Upstream ref:** [nousresearch/hermes-agent#30908](https://github.com/nousresearch/hermes-agent/issues/30908)

**Status:** Substantially mitigated upstream. Hermes v0.15.0 added multiple SQLite hardening layers: `secure_delete` + `cell_size_check` + `synchronous=FULL` to prevent torn-write corruption, corrupt-db detection that refuses auto-init on corrupted databases, content-addressed backup filenames for corrupt-DB quarantine, post-commit page_count invariant checks, and Windows init lock guards. The underlying race may still exist, but the probability of silent corruption is drastically reduced.

**Symptom (pre-v0.15.0):** After frequent gateway restarts, `kanban.db` develops index corruption. The dispatcher permanently disables itself for the board.

**Current guidance (v0.15.x):** Minimize gateway restarts as before, but the SQLite hardening makes corruption far less likely. If dispatch stalls, the corrupt-board detection will quarantine rather than silently operate on a damaged database.

### Dispatcher doesn't surface why cards are stuck (#30213)

**Upstream ref:** [nousresearch/hermes-agent#30213](https://github.com/nousresearch/hermes-agent/issues/30213)

**Symptom:** Cards sit in `ready` state for minutes with no dispatch and no explanation. The operator sees `spawned=[]` with no reason.

**Exposure:** Any time multiple cards are `ready` on the same provider.

**Workaround:**
1. Run `hermes kanban show <id>` on stuck cards to check for `spawn_failed` events
2. Check provider rate limits — same-provider cards serialize automatically
3. Kill orphaned agent processes from archived cards that are still holding provider slots
4. If truly stuck: restart gateway (with the DB corruption caveat above)

**Detection:** Preflight check: if any card has been `ready` for >2 minutes, flag as degraded and investigate.

---

## Root Card Management

### Root card `--triage` triggers auto-decomposition

**Symptom:** Creating a root card with `--triage` assigns it to the orchestrator profile. With `auto_decompose=true`, the dispatcher spawns decomposer work and produces stub children that duplicate manually-created cards. With `auto_decompose=false`, the root stays stuck in `triage`.

**Exposure:** Using `--triage` on any root/summary card for a manually-decomposed plan.

**Workaround:**
1. Create the root card **without** `--triage`
2. Set `kanban.auto_decompose false` before decomposition
3. Complete root immediately after all children are created and linked: `hermes kanban complete <root_id> --summary "Root complete — N cards dispatched manually."`
4. If duplicates appear: archive them before they reach `running`

**Detection:** After creating all cards, check `hermes kanban list` for any cards not in the plan. Archive unexpected cards immediately.

### Gate card is orchestrator-only (not human checkpoint)

**Symptom (misconfiguration):** Operator waits to manually unblock gate; or gate assigned to worker profile → protocol violation loop.

**Design:** Gate is a dependency root for the orchestrator. Workers never execute it. Flow: block on create → link all impl cards to gate → `validate_board.sh` → orchestrator **`complete`** gate (not human unblock) → `auto_unblock.sh` releases wave 1.

**Workaround:** Assign gate to orchestrator profile, no `agent -p` block. Complete after validation. See `wiki/decomposition-workflow.md`.

---

## Integration with kanban-advanced

### Preflight (kanban-advanced:kanban-preflight)

The preflight script should check for exposure to these issues:

| Check | What it catches |
|---|---|
| Stuck `ready` cards >2 min | Dispatcher stall, provider saturation |
| `ready` cards with `todo` parents | Dependency gating bypass |
| Shared worktree paths | Workspace contention |
| Code-gen cards with `scratch` workspace | Zero-output risk |
| Orphaned agent processes | Provider slot exhaustion |

### Orchestrator (kanban-advanced:kanban-orchestrator)

During Step 0d (card body policy validation) and Step 1 (understand the goal):

1. Verify `kanban.auto_decompose` is `false`
2. Verify all dependent cards were **blocked immediately after create** (not left `ready`, not `--triage`)
3. Confirm all parent-child links via `hermes kanban link`, never `--parents`
4. Check every card has a unique absolute `worktree:<path>`
5. Complete root immediately; complete gate after `validate_board.sh` (orchestrator-only)
6. Confirm `auto_unblock` + `board_keeper` crons are running before gate completion

**Agent FAQ:** `wiki/decomposition-workflow.md`

### Planning (kanban-advanced:kanban-planning)

During the 12-item checklist:

- Item 9 (same-provider staggering): also verify workspace isolation
- Item 12 (iteration budget): also verify no card exceeds the retry circuit-breaker threshold
- New implicit check: every agent-prompt block must target a worktree-isolated card
- Decomposition method: block-on-create + gate pattern — not `--triage`, not vanilla `hermes kanban decompose`

---

## Upstream umbrella

[hermes-agent#35986](https://github.com/NousResearch/hermes-agent/issues/35986) maps the open Kanban orchestration reliability surface (stale detection defaults, silent blocked cards, orphaned triage, circuit-breaker gaps, subagent supervision). kanban-advanced's block-on-create + cron auto-progression design directly addresses Gaps 2–3 (mechanical unblock, no LLM polling) and complements upstream fixes where they exist.

---

## Version tracking

| Date | Issue | Upstream status | Workaround effective? |
|---|---|---|---|
| 2026-05-27 | #16102 (RFC — atomic `ready` claim) | Merged / shipped | Yes — block-on-create |
| 2026-05-27 | #24489 (running parent blocks children) | Open | Yes — complete root/gate promptly |
| 2026-05-27 | #30417 Bug 3 (archive promotion) | Open | Yes — don't archive parents |
| 2026-05-27 | Workspace contention | Not filed | Yes — unique worktree paths |
| 2026-05-27 | `--parents` flag broken | Not filed separately | Yes — use `kanban link` |
| 2026-05-27 | Root auto-decomposition | v0.15 `auto_decompose` | Yes — `auto_decompose false` + no `--triage` |
| 2026-05-29 | #29320 (no circuit-breaker) | **✅ Resolved (v0.15.0)** — `failure_limit` built-in | N/A (upstream fix) |
| 2026-05-29 | #30908 (DB corruption) | **⚠️ Mitigated (v0.15.0)** — SQLite hardening | Partially |
| 2026-05-29 | #30213 (stuck dispatch) | Open — worker visibility endpoints added in v0.15.0 help diagnosis | Yes — show diagnostics |
| 2026-05-29 | Agent processes survive archive | **✅ Resolved (v0.15.1)** — SIGTERM fix + workspace cleanup | N/A (upstream fix) |
| 2026-05-31 | #35986 (orchestration umbrella) | Open | Yes — crons + block-on-create |
| 2026-06-10 | `--initial-status blocked` race | Not filed | Yes — separate `kanban block` call |
| 2026-06-10 | `--triage` stuck when `auto_decompose=false` | By design interaction | Yes — block-on-create |
| 2026-06-10 | `kanban block` only on `ready` (v0.15+) | Documented upstream | Yes — block immediately after create |

## Agent Process Management

### Goal-mode turn budget exhausted (v0.15.2+)

**Symptom:** Card blocked with a message that the goal loop exhausted `goal_max_turns` without `kanban_complete`.

**Behavior:** Upstream blocks for human review rather than silently marking done. This is expected when acceptance criteria were too vague or the lane should have been split.

**Guidance:** Refine `Acceptance:` in the plan, increase `goal_max_turns` only with operator approval, or split into one-shot cards. See `references/goal-card-selection.md`.

### Agent processes survive card archive — ✅ resolved in v0.15.1

**Status:** Resolved upstream. Hermes v0.15.0 added automatic scratch workspace and tmux session release on task completion. v0.15.1 fixed the worker SIGTERM handler so workers can actually be terminated (#34045). Archiving or completing a card should now cleanly kill the associated agent process.

**Symptom (pre-v0.15.x):** Archiving a card does not kill the spawned agent process. The agent continues running, consuming provider slots and preventing new cards from dispatching.

**Current guidance (v0.15.x):** If orphaned processes are still observed (unlikely), the preflight check for orphaned agent PIDs remains valid as a safety net.

### `worktree:.` relative path rejected

**Symptom:** Cards created with `--workspace worktree:.` fail with "non-absolute worktree path '.'".

**Exposure:** Any card using a relative workspace path.

**Workaround:** Always use absolute paths: `--workspace "worktree:/tmp/wt-<card-name>"`.

### `--trust` flag required for new worktrees

**Symptom:** Agent fails with "workspace trust failure" in freshly-created worktrees.

**Exposure:** First agent run in a new worktree directory.

**Workaround:** Worker should detect the trust failure and retry with `--trust` flag automatically. Add to worker Step 4 (Handoff).

## Extraction Side Effects

### Monkeypatch paths break when functions move modules

**Symptom:** After extracting a function from module A to module B, tests that monkeypatch the function on module A (the facade) don't affect internal callers in module B (the source).

**Exposure:** Any module extraction where tests use `monkeypatch.setattr` or `@patch` on the extracted function.

**Workaround:**
1. During planning: grep tests for `monkeypatch.setattr.*<function_name>` and `@patch.*<function_name>`
2. Add dual-patch instructions to the agent-prompt block
3. Example: `monkeypatch.setattr(tf, "_fn", ...)` AND `monkeypatch.setattr("app.services.new_module._fn", ...)`
4. Add to planning 12-item checklist: item "Monkeypatch paths verified"
