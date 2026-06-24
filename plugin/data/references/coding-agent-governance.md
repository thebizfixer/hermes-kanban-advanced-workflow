# Coding Agent Governance Block

Prepend this to every coding agent dispatch prompt. The governance block is enforced post-hoc by the evaluation chain (E001–E006), but prompt-level guardrails reduce the remediation burden.

## Files boundary

You MUST ONLY modify files listed in `Files:` below. Do NOT install packages, modify configs, or touch files outside the `Files:` list. If you need a dependency that isn't installed, report it to the worker — do NOT run `pip install`, `npm install`, or any package manager.

## Mode constraint

The `Mode:` line declares the expected file operation:
- `modify-only` — edit existing files only; do NOT create new files
- `create-only` — create new files only; do NOT modify existing files
- `any` — create or modify as needed

## Pre-commit self-audit (mandatory, before git commit)

1. Run `git diff --stat` (include staged + unstaged: `git diff --stat HEAD` if needed)
2. Compare the diff against `Files:` — only listed paths may remain changed
3. Revert unlisted changes: `git checkout -- <path>` for modified tracked files not on `Files:`, and remove untracked files not on `Files:`
4. If any file on `Files:` shows 0 lines changed, stop and fix BEFORE committing
5. Mode check: `modify-only` → confirm no accidental file creation; `create-only` → confirm listed paths are new additions

## Issue reporting

If you hit an error, report the EXACT error message to the worker. Do NOT guess at a fix. Include: what you were doing, the exact error text, and which file/line.

## Prohibited actions

- Do NOT run `git add -A` — use `git add <specific files>`
- Do NOT push to any remote branch
  (a pre-push hook is installed in this worktree — the push will be blocked)
- Do NOT commit files outside the `Files:` list
  (a pre-commit hook is installed in this worktree — the commit will be rejected)
- Do NOT modify `.hermes/`, `.agent/`, vendor IDE local config trees, or project config files
- Do NOT change the build system, CI config, or package manifests
- Do NOT install packages or modify the environment

## Verification

After committing, the worker will run:
1. `git diff --stat <baseline>..HEAD` — every `Files:` path must show >0 changes
2. The test command from `Tests:`
3. The evaluation chain (E001–E021)

Your commit message must match the `Commit:` line. Token usage is extracted from your JSON output.

## delegate_task in Kanban Worker Sessions

Kanban worker sessions are short-lived (claim → work → complete → exit).
The `delegate_task` tool spawns subagents that require the parent session to
remain alive to collect results. On Windows, worker sessions terminate after
the agent's turn, killing subagents before they complete.

**Rule:** Workers must NOT use `delegate_task`. If a card requires multi-step
reasoning that would benefit from subagents, split the card into smaller
cards in the plan. This limitation will be lifted when the Hermes core
session lifecycle supports subagent result collection across turns.

**Affected:** All platforms, but crashes are silent on Linux/macOS (subagents
complete but results are discarded) and visible on Windows (worker process
terminated with `pid not alive`). The parallel subagent gate was removed from
the orchestrator runbook as a workaround — `kanban_handoff.py` always runs the
serial gate at handoff time.
