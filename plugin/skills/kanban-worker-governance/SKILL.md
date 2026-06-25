---
name: kanban-worker-governance
description: Load when a worker hits evaluation-chain DENY, E-code block, or auth/smoke failure. Error codes E001–E023, worktree quick rows, recover.py — not happy-path steps.
version: 1.1.0
metadata:
  hermes:
    tags: [kanban, governance, reference, error-codes, pitfalls]
    related_skills: [kanban-advanced:kanban-worker]
---

# Kanban Worker Governance Reference

> Load on-demand when evaluation chain DENYs or block reason contains `E0`, `[escalation:`, or `protocol violation`. Happy path stays in `kanban-advanced:kanban-worker`.

**Router:** `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")` → symptom row → command → verify. Wiki optional if `wiki/` exists in repo root.

**Constitution (MUST / MUST NOT):**

- MUST dispatch via `terminal()` + `coding_agent_invoke.sh` — MUST NOT `execute_code` or code directly.
- MUST use `worktree_setup.sh` — MUST NOT raw `git worktree add`.
- MUST NOT soften script DENY or override gate exit codes.
- `[escalation:coding_agent:auth]` → T3 after one smoke retry with `HOME` set.
- MUST run evaluation chain before `kanban_complete`.

## Worktree provisioning (BB — no wiki required)

| Symptom | Tier | First command | Verify |
|---------|------|---------------|--------|
| E021 / missing invoke script | T1 | `worktree_setup.sh --task-id <id> --repo-root <repo>` | `.hermes/scripts/coding_agent_invoke.sh` in worktree |
| exit 127 on scripts | T1 | Resolve `BUNDLE` (index footer); Update Plugin | Script exists under `$HERMES_HOME/scripts/` |
| plan missing in WT | T1 | `git checkout origin/${working_branch} -- .hermes/kanban/plans/*{plan_id}*` | `read_file` / cat plan section |
| `.env` / venv missing | T3 | Operator adds to `.worktreeinclude` | `E003`/`E015` clear after provision |

## Error codes E001–E023

Canonical: `plugin/data/registry/error-codes.yaml`. **Tier:** T1=self-serve BB | T2=MBB | T3=Operator.

| Code | Sev | Tier | Recovery |
|------|-----|------|----------|
| E001 | error | T1 | Widen `--baseline` / set `KANBAN_EVAL_BASELINE=origin/staging` or `merge-base:origin/main`; `pre_existing: true` uses merge-base diff; `find_prior_commit` ALLOW. **Post-flight:** same rule clears Tier 1 `plan_file_zero_diff` — stamp `Commit:` on complete so final audit sees E001-equivalent evidence (`final-audit-sanity-check.md` § Tier 1 ↔ E001) |
| E002 | warn | T1 | Auto-reverted; add to `Files:` if intentional |
| E003 | error | T1 | Fix tests/imports/deps (`E015` if env) |
| E004 | error | T1 | Amend commit to match `Commit:` |
| E005 | warn | T1 | Superseded by E018 — log tokens exactly |
| E006 | error | T1 | Check worktree not scratch; agent auth; prompt |
| E007 | error | T3 | Free disk >1GB |
| E008 | error | T1 | Retry after network/rate-limit |
| E009 | error | T2 | Delete wrong remote branch; reset worktree branch |
| E010 | error | T3 | Terminate agent; clean worktree |
| E011 | error | T3 | Move repo off DrvFs/cross-mount |
| E012 | warn | T2 | Orchestrator re-runs preflight + attestation |
| E013 | error | T2 | Restore `kanban_evaluation_chain.py` from bundle |
| E014 | error | T1 | Verification: `Tests:` via terminal only — no agent |
| E015 | error | T1/T3 | `pip install -r requirements.txt` or operator provision |
| E016 | error | T2 | Salvage commits; merge to staging immediately |
| E017 | error | T2 | Escalate — split card or fix scope |
| E018 | error | T1 | Capture agent JSON; `token_tracker` source=agent |
| E019 | error | T1 | Per-hunk merge — no `--theirs`/`reset --hard` |
| E020 | error | T1 | `coding_agent_invoke.sh dispatch` with JSON capture |
| E021 | error | T1 | `worktree_setup.sh` — not raw `git worktree add` |
| E023 | error | T2 | Same error signature as prior run — escalate, do not retry |

## kanban_recover.py (retryable E only)

```bash
python3 scripts/kanban_recover.py --list
python3 scripts/kanban_recover.py <task_id> E003   # example
```

Do **not** use recover for auth (`[escalation:coding_agent:auth]`) or E021 (fix worktree first).

## Pitfalls (short)

- **`[unauthenticated]` in logs** — cosmetic Cursor indexer; use `coding_agent_invoke.sh smoke`.
- **`agent status` ≠ reachable** — run `agent -p "say ok" --trust` from worktree.
- **`CURSOR_API_KEY`** — ignored; OAuth at `~/.config/cursor/auth.json`.
- **Salvage before re-dispatch** on iteration-limit — see `plugin/data/references/salvage-pattern-iteration-exhausted-cards.md`.

Deep dive: `plugin/data/references/coding-agent-auth.md`, `wiki/troubleshooting.md` § Cursor OAuth.
