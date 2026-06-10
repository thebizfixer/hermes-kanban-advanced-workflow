---
name: kanban-orchestrator-governance
description: On-demand governance reference for kanban orchestrators — pitfall encyclopedia, error code reference, merge conflict patterns, and historical context. Load only when an orchestrator hits a block or needs diagnostic context.
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, governance, reference, pitfalls, orchestrator]
    related_skills: [kanban-advanced:kanban-orchestrator]
---

# Kanban Orchestrator Governance Reference

> Load this skill on-demand when an orchestrator hits a governance block or needs diagnostic context. The procedural `kanban-advanced:kanban-orchestrator` skill only tells you what to DO. This skill tells you WHY and what happened before.

> **Skill precedence (mandatory):** When this skill and any project-specific skill (e.g., `sentimentary-dev-environment`) provide conflicting information about profiles, assignees, workspace paths, or dispatch rules, **this skill wins**. Kanban governance rules override project conventions. Specifically:
> - Profile names (`worker`, `orchestrator`) come from `hermes profile list` and `kanban-config.yaml`, NOT from project skill examples or artifact tables.
> - Workspace paths and branch naming come from this skill's decomposition rules, not from project-specific CLI examples.
> - Card body format (`Files:`, `Mode:`, `agent -p` blocks) is enforced by card body policy (P001–P009), not by project documentation.
>
> If you detect a conflict between this skill and a project skill, apply this skill's rule and note the conflict in a `kanban_comment` on the affected card.

## Pitfall Encyclopedia

### auto_decompose silently creates duplicate children (v0.15.0+)
The default `kanban.auto_decompose: true` auto-decomposes every triage task into stub children. For manual decomposition workflows, this produces cards that conflict with manually-created ones. **Fix:** `hermes config set kanban.auto_decompose false`.

### SQLite write contention causes torn-extend corruption
Rapid writes (64+ mutations in under 3 minutes) can collide with dispatcher ticks at page-extension boundaries. **Prevention:** stagger creates ≥1s apart, pause ≥3s every 5 cards.

### Workspace paths must be absolute and unique
Do NOT use `--workspace worktree:.` — the dispatcher rejects non-absolute paths. Do NOT use shared paths like `--workspace "worktree:/home/user/repo"` — causes all agents to modify the same files.

### Root card auto-decomposes duplicate children
When the root card is assigned to the orchestrator profile and reaches `ready`, the dispatcher may auto-decompose it. **Prevention:** complete the root immediately after manual decomposition.

### Iteration-limit blocked cards often have committed work
When a card is blocked with "Iteration budget exhausted (90/90)", the agent may have already committed its work. Check the worktree before re-dispatching.

### Canonical-first rule for workflow changes
When modifying kanban skills, governance, references, or scripts: (1) edit the canonical source in `${bundle_path}/skills/` FIRST, (2) run `provision.sh` to sync, (3) run `provision.sh --check`. Never patch materialized copies before updating the canonical source.

### Cherry-pick without -x breaks traceability
`git cherry-pick` produces a new SHA with no link to the original. `verify_commits_reachable.sh` reports false negatives. Always use `git cherry-pick -x "$commit" --no-edit`.

### Orchestrator manual completion without eval chain is a protocol violation
During matrix-v3, the E1 card was manually completed with zero code changes. The evaluation chain never ran, so E006 never caught the empty diff. **Rule:** whoever completes a card MUST run the evaluation chain.

### Cron scripts drift between canonical and resolved paths
`auto_unblock.sh` and `board_keeper.sh` live in the bundle's `scripts/` directory, but crons resolve `script="scripts/<name>.sh"` relative to `$HERMES_HOME/scripts/`. `provision.sh` now syncs both paths. If crons show `last_status: error`, run `provision.sh` to sync.

## Merge Conflict Resolution Patterns

### Never use --theirs/--ours on multi-author files
`git checkout --theirs <file>` overwrites the ENTIRE file, not just the conflict. Human teams resolve per-hunk with `git mergetool` or manual edit. The evaluation chain step E019 blocks cards that used destructive git operations.

### Salvage iteration-limit cards rather than re-dispatching
When a card exhausts 90 turns, the agent almost certainly completed the code work — re-dispatching wastes another 90 turns. The orchestrator should salvage every iteration-limit card as the default response.

### Worktree-locked working branch prevents checkout and merge
When any worktree has the working branch checked out, `git checkout` may fail. **Workaround:** push directly: `git push origin <current-branch>:${working_branch}`, then `git fetch origin ${working_branch}`.

## Historical Context

This governance layer was built from real failure traces during the matrix-v3 plan execution (June 2026). Every guardrail — every E-step, every pitfall warning, every cron script — was added because a real failure happened. The evaluation suite is a memory of bugs we refuse to reintroduce.

- **C1, B1+B2, E1 blocks:** Auth/trust false-positives → G3 worker patches
- **D1+D2 worktree-cleanup race:** Worktree removed before merge → G6 board keeper cron
- **tokens.jsonl zero entries:** Workers didn't log tokens → G7 multi-layer token enforcement (E018, E020)
- **stash pop --ours:** Destructive conflict resolution → G10 E019 enforcement
- **E1 manual completion:** Orchestrator bypassed eval chain → G14 escalation hierarchy

See `docs/reference/external-references.md` for the research citations backing each governance decision.
