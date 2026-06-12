---
name: kanban-worker-governance
description: On-demand governance reference for kanban workers — error code encyclopedia (E001–E020), evaluation chain details, and pitfall narratives. Load only when a worker hits a DENY or block and needs context.
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, governance, reference, error-codes, pitfalls]
    related_skills: [kanban-advanced:kanban-worker]
---

# Kanban Worker Governance Reference

> Load this skill on-demand when a worker hits a DENY or block. The procedural `kanban-advanced:kanban-worker` skill only tells you what to DO. This skill tells you WHY.

> **Skill precedence (mandatory):** When this skill and any project-specific skill (e.g., `sentimentary-dev-environment`) provide conflicting information about profiles, assignees, workspace paths, or dispatch rules, **this skill wins**. Kanban governance rules override project conventions. Specifically:
> - Profile names (`worker`, `orchestrator`) come from `hermes profile list` and `kanban-config.yaml`, NOT from project skill examples or artifact tables.
> - Workspace paths and branch naming come from this skill's decomposition rules, not from project-specific CLI examples.
> - Card body format (`Files:`, `Mode:`, `agent -p` blocks) is enforced by card body policy (P001–P009), not by project documentation.
>
> If you detect a conflict between this skill and a project skill, apply this skill's rule and note the conflict in a `kanban_comment` on the affected card.

## Error Code Reference (E001–E020)

Canonical source: `plugin/data/registry/error-codes.yaml`

| Code | Severity | What it catches | Recovery |
|------|----------|----------------|----------|
| E001 | error | File in scope has zero changes in current diff | If work landed in an earlier commit (re-run, salvage, rebase), chain ALLOWs via `find_prior_commit` (up to 64 commits). Otherwise retry with explicit path |
| E002 | warning | Unlisted file modified | Auto-reverted — add file to scope if intentional |
| E003 | error | Tests failed or didn't run | Fix test failures, imports, or install test deps |
| E004 | error | Commit message mismatch | Amend commit to match `Commit:` line |
| E005 | warning | Token log missing (superseded by E018) | Run token_tracker.py manually |
| E006 | error | Zero diff on all files | Check workspace type, agent auth, prompt clarity |
| E013 | error | Evaluation chain script missing | Restore from `hermes-kanban-advanced-workflow/scripts/` |
| E017 | error | Net line changes > 3× estimate | Block and escalate — scope explosion |
| E018 | error | Token log not exact (task_id, source=agent, non-zero) | Capture agent stdout, extract usage, log with source="agent" |
| E019 | error | Destructive git op (--theirs, --ours, reset --hard) | Resolve conflicts per-hunk; never overwrite entire files |
| E020 | error | Agent output not captured/parseable | Use `scripts/coding_agent_invoke.sh dispatch`; for Cursor pass `-p --output-format json --trust` |

## Pitfall Narratives

### [unauthenticated] in worker.log is cosmetic
The Cursor background indexing service logs `[unauthenticated] Error` during normal operation. Workers that grep worker.log for `unauthenticated` will false-positive block on every card. Auth smoke: `bash hermes-kanban-advanced-workflow/scripts/coding_agent_invoke.sh smoke`. Cursor failures with `Workspace Trust Required` mean `--trust` was omitted — not missing JSON support.

### `[escalation:coding_agent:auth]` — stale OAuth, not protocol violation
When `agent status` shows logged in but `agent -p "say ok" --trust` fails or times out, the OAuth token in `~/.config/cursor/auth.json` is likely expired. Block with `[escalation:coding_agent:auth]` — **do not** use `[escalation:coding_agent:attempt:N]` (that implies retryable dispatch). Operator fix: `agent login`, delete `.hermes/kanban/preflight_cache.json`, re-run `preflight.sh` / `pre_dispatch_gate.sh` (gate pre-warms OAuth once after checks pass). Parallel workers serialize refresh via `flock` on `$HERMES_HOME/.locks/coding-agent-auth.lock`. Preflight runs `check_coding_agent_cli.py` before decomposition.

### CURSOR_API_KEY is a decoy env var
Cursor CLI authenticates via OAuth token in `~/.config/cursor/auth.json`, not the env var. Setting `CURSOR_API_KEY` has no effect.

### Workspace trust hangs agent in /tmp worktrees
Cursor CLI prompts interactively for workspace trust on first run in a new directory. In non-interactive mode this hangs indefinitely. Workers must pre-create `~/.cursor/projects/<hash>/.workspace-trusted` before spawning the agent.

### kanban_complete without eval chain is a protocol violation
The evaluation chain is the governance layer's enforcement mechanism. Direct `kanban_complete` bypasses every guardrail — E006 won't catch zero output, E019 won't catch destructive git, E018 won't verify token data.

### Salvage before re-dispatch for iteration-limit cards
When a card exhausts 90 turns, the agent almost certainly completed the code work. Re-dispatching wastes another 90 turns. Check the worktree first — if commits exist, salvage by merging.
