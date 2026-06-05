## Coding Agent Governance (Ordinal Contract)

The coding agent (Cursor CLI) operates under an idempotent ordinal contract. Every
positive instruction has a corresponding negative boundary. The worker injects this
block before every `agent -p` handoff. Violations are caught post-hoc by the
evaluation chain (E001–E006).

---

### 1. What is Needed?

Implement the task described below. Produce exactly what is requested — no
additional features, creative extensions, or "improvements." Follow instructions
to the letter.

### 2. How is it Needed?

Modify ONLY the files listed in `Files:` below. Use the specified `Mode:` (modify-only
or create-only). Create exactly one commit with the exact `Commit:` message below.

### 3. What is Wanted?

All `Tests:` pass. `git diff --stat` shows ONLY files in the `Files:` list. The
commit message matches `Commit:` exactly. Zero scope violations.

### 4. How is it Wanted?

1. Read the files listed in `Files:` to understand context.
2. Make the minimal changes needed.
3. Run `Tests:` and confirm all pass.
4. Run `git diff --stat` and confirm only `Files:` files changed.
5. Commit with `git add <Files: files> && git commit -m "<Commit: message>"`.

### 5. Where does it belong?

In the git worktree at the current working directory. Commit to the worktree branch
only. Do NOT push to any remote.

### 6. How does it belong there?

Isolated to the files in `Files:`. Do not cross module boundaries unless the
`Files:` list explicitly includes the boundary module.

---

### 9. What is NOT Wanted? (failure modes → E001–E006)

- E001: Files in `git diff` that are NOT in `Files:` → will be auto-reverted.
- E003: Tests that fail → task will be blocked.
- E004: Commit message that doesn't match `Commit:` → task will be blocked.

### 10. How is it NOT Wanted? (sad paths → recovery)

If you hit an error, missing import, or unexpected behavior:
1. Report the **exact error message**.
2. Do **NOT** guess, work around, or skip.
3. Do **NOT** touch files outside `Files:` to fix it.
4. The worker will triage and provide updated instructions.

### 11. Where does it NOT belong? (restricted paths → E002/E009/E011)

Do **NOT** modify:
- `.agent/plans/` — plan files (or `.cursor/plans/` for Cursor users)
- `.cursor/rules/` — governance rules
- `docs/` — documentation
- `CHANGELOG.md` — release notes
- `.git/config` — repository configuration
- Any file not in the `Files:` list

### 12. How does it NOT belong there? (boundary enforcement → P001–P004)

Do **NOT**:
- Run package managers (`npm install`, `pip install`, `yarn`, `pnpm`)
- Install dependencies or modify `package.json` / `requirements.txt`
- Create new files unless `Mode: create-only` and the file is in `Files:`
- Change git remotes, branches, or configuration
- Push to any remote

### 13. When is it NOT received? (environmental failures → E007/E008)

If the worktree is missing, a dependency is unavailable, or the test runner can't
be found: report the issue to the worker. Do NOT attempt to install, configure, or
work around environmental gaps.

### 14. How will it NOT be received? (governance → E013)

If you cannot complete the task within the specified constraints, report:
- What you tried
- The exact error
- What file/line the error occurred on

Do NOT produce partial work. Do NOT commit incomplete changes. A blocked task is
better than a wrong task.
