# Vanilla Hermes Agent Kanban — Known Issues & Workarounds

> **Purpose:** Map known vanilla `hermes kanban` bugs to workarounds so the orchestrator can plan around them before dispatching cards. Updated as new issues are discovered or fixed upstream.

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

### Parents don't block child dispatch (#24489)

**Upstream ref:** [nousresearch/hermes-agent#24489](https://github.com/nousresearch/hermes-agent/issues/24489)

**Symptom:** Cards with parent dependencies dispatch and run before their parents complete. `hermes kanban link` added after creation cannot retroactively prevent dispatch — the dispatcher claims `ready` cards in <1 second.

**Exposure:** Any plan that creates dependent cards as `ready` and links parents afterward.

**Workaround:**
1. Create all dependent cards with `--triage` (parks them, not `ready`)
2. Link all parent-child relationships
3. Unblock dependent cards only after all links are established
4. For large plans: use the **gate pattern** — create a gate card (blocked), link everything, unblock the gate last

**Detection:** During preflight, check if any `ready` cards have `todo` parents. Flag as degraded.

```bash
# Quick check for cards that dispatched before parents completed
hermes kanban list | awk '/▶.*ready/ {print $2}' | while read tid; do
  hermes kanban show "$tid" | grep -q 'parents:.*t_' && echo "WARN: $tid has parents but is ready"
done
```

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

**Workaround:** Never use `--parents`. Always create the card first, then use `hermes kanban link <parent> <child>` separately. Verify with `hermes kanban show <child>` that `parents:` lists the expected IDs.

**Detection:** After any `hermes kanban create --parents`, immediately run `hermes kanban show <child>` and grep for `parents:`. If empty, the flag was ignored — block the card and link manually.

---

## Workspace Isolation

### Concurrent agents corrupt each other's work (shared worktree)

**Symptom:** Multiple agents modifying the same files in the same directory. Files created by one agent are deleted by another. Changes to shared files (e.g., `tinyfish.py`) are lost. Iteration budget wasted on conflict recovery.

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

**Symptom:** Creating a root card with `--triage` assigns it to the orchestrator profile. The dispatcher treats it as a work card and spawns an agent that auto-decomposes it into stub children, duplicating manually-created cards.

**Exposure:** Using `--triage` on any root/summary card for a manually-decomposed plan.

**Workaround:**
1. Create the root card without `--triage`
2. Complete it immediately after all children are created and linked: `hermes kanban complete <root_id> --summary "Root complete — N cards dispatched manually."`
3. If duplicates appear from auto-decomposition: archive them before they reach `running`

**Detection:** After creating all cards, check `hermes kanban list` for any cards not created by the orchestrator. Archive unexpected cards immediately.

---

## Integration with kanban-advanced

### Preflight (kanban-preflight)

The preflight script should check for exposure to these issues:

| Check | What it catches |
|---|---|
| Stuck `ready` cards >2 min | Dispatcher stall, provider saturation |
| `ready` cards with `todo` parents | Dependency gating bypass |
| Shared worktree paths | Workspace contention |
| Code-gen cards with `scratch` workspace | Zero-output risk |
| Orphaned agent processes | Provider slot exhaustion |

### Orchestrator (kanban-orchestrator)

During Step 0d (card body policy validation) and Step 1 (understand the goal):

1. Verify all dependent cards were created `blocked`/`triage`, not `ready`
2. Confirm all parent-child links via `hermes kanban link`, never `--parents`
3. Check every card has a unique absolute `worktree:<path>`
4. Set `max-retries: 2` on every card
5. Complete the root card immediately after manual decomposition

### Planning (kanban-planning)

During the 12-item checklist:

- Item 9 (same-provider staggering): also verify workspace isolation
- Item 12 (iteration budget): also verify no card exceeds the retry circuit-breaker threshold
- New implicit check: every agent-prompt block must target a worktree-isolated card

---

## Version tracking

| Date | Issue | Upstream status | Workaround effective? |
|---|---|---|---|
| 2026-05-27 | #24489 (parent gating) | Open | Yes — gate pattern |
| 2026-05-27 | #30417 Bug 3 (archive promotion) | Open | Yes — don't archive parents |
| 2026-05-27 | Workspace contention | Not filed | Yes — unique worktree paths |
| 2026-05-27 | `--parents` flag broken | Confirm in #24489 | Yes — use `kanban link` |
| 2026-05-27 | Root auto-decomposition | May relate to decompose flow | Yes — don't use `--triage` |
| 2026-05-29 | #29320 (no circuit-breaker) | **✅ Resolved (v0.15.0)** — `failure_limit` built-in | N/A (upstream fix) |
| 2026-05-29 | #30908 (DB corruption) | **⚠️ Mitigated (v0.15.0)** — SQLite hardening | Partially |
| 2026-05-29 | #30213 (stuck dispatch) | Open — worker visibility endpoints added in v0.15.0 help diagnosis | Yes — show diagnostics |
| 2026-05-29 | Agent processes survive archive | **✅ Resolved (v0.15.1)** — SIGTERM fix + workspace cleanup | N/A (upstream fix) |

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
