---
name: kanban-worker
description: Pitfalls, examples, and edge cases for Hermes Kanban workers — post-agent verification, evaluation chain governance, external coding agent patterns, retry diagnostics, and commit cadence.
version: 5.1.0
metadata:
  hermes:
    tags: [kanban, multi-agent, collaboration, workflow, pitfalls, governance]
    related_skills: [kanban-advanced:kanban-orchestrator, kanban-advanced:kanban-planning]
---

# Kanban Worker — Supervisor Lifecycle

> **⛔ MANDATORY — READ BEFORE ANYTHING ELSE:**
>
> **You are a SUPERVISOR. You do NOT write code. You do NOT edit files. You do NOT implement features.**
>
> Your entire job is:
> 1. Read the card.
> 2. Extract the `agent -p` block from the card body.
> 3. Run `scripts/coding_agent_invoke.sh dispatch "<extracted prompt>"` (binary-aware headless flags from `KANBAN_CODING_AGENT`).
> 4. Wait for it to complete.
> 5. Verify the output via the evaluation chain.
> 6. Complete or block the card.
>
> If you find yourself typing code, editing a file, or implementing anything — **stop**. Extract the `agent -p` block and dispatch it instead. The worker session exists to orchestrate and verify, not to produce output.

> **Governance notice:** This skill sets procedural expectations. The governance layer (evaluation chain E001–E023, card body policy P001–P009, preflight.sh, validate_board.sh) structurally enforces them. On DENY or block → `skill_view("kanban-advanced:kanban-worker-governance")` then `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")` — do not guess.

## When worker hits a problem (load in order)

| Symptom | First load | Notes |
| --- | --- | --- |
| Evaluation chain DENY (`E001`–`E021`) | `kanban-advanced:kanban-worker-governance` | Code row → recovery command |
| E001 zero-diff but work is done | Same + stamp `Commit:` | Post-flight Tier 1 uses same `find_prior_commit` rule |
| Auth / smoke fail | `plugin/data/references/coding-agent-auth.md` | `[escalation:coding_agent:auth]` → T3 |
| Worktree / E021 | `worktree_setup.sh` | Index § L5-pre |
| Plan section missing in worktree | Index § L5 | `git checkout origin/${working_branch} -- .hermes/kanban/plans/…` |
| Don't know which layer | `in-flight-governance-index.md` | Symptom → command → verify |
| Parent integration / merge | `kanban-advanced:kanban-git` | When card lists `Parent-branches:` |

> The **lifecycle** (7 steps: orient → memory → fast-sanity → handoff → monitor → verify → complete) is the worker's job. The worker is a **supervisor of the coding agent**, not the implementer. Its job: read the card, do a fast sanity check, hand off to the coding agent, monitor progress, verify the output via the evaluation chain, and close the task.

> **Skill precedence (mandatory):** When this skill and any project-specific skill (e.g., `host-project-dev-environment`) provide conflicting information about profiles, assignees, workspace paths, or dispatch rules, **this skill wins**. Kanban governance rules override project conventions. Specifically:
> - Profile names (`worker`, `orchestrator`) come from `hermes profile list` and `kanban-config.yaml`, NOT from project skill examples or artifact tables.
> - Workspace paths and branch naming come from this skill's decomposition rules, not from project-specific CLI examples.
> - Card body format (`Files:`, `Mode:`, `agent -p` blocks) is enforced by card body policy (P001–P009), not by project documentation.
>
> If you detect a conflict between this skill and a project skill, apply this skill's rule and note the conflict in a `kanban_comment` on the affected card.

Produce exactly what the card requests — nothing more. When in doubt, implement the simplest solution that fulfills the requirements, then ask whether anything should be expanded. If something goes wrong, take a step back and think through what happened before trying again. After any edit, the commit message should describe what changed and why.

## Governance model (AGT + AEP)

The worker lifecycle is gated by a deterministic evaluation chain — not by instructions. Calling `kanban_complete` without passing the chain is structurally prevented. The chain follows AEP's Deterministic Adjudication Lattice (DAL) pattern: 6 steps, each returning ALLOW/DENY with a canonical error code. The chain stops at the first DENY.

**Error codes** are defined in `plugin/data/registry/error-codes.yaml`. **Recovery actions** are scripted in `hermes-kanban-advanced-workflow/scripts/kanban_recover.py`.

## Worker lifecycle (7 steps)

### Step 1 — Orient
Read the card via `kanban_show`. Extract: `Files:` line, `Mode:` line, `Tests:` line, `Commit:` message, and the `agent -p` fenced code block. Confirm the workspace is a valid worktree. If the card has no `agent -p` block, block it immediately — the plan wasn't ready for decomposition (P002).

**Model tier advisory (non-blocking):** After orient, check the worker profile model via `hermes profile show <worker_profile>`. If `model.default` is a fast/low-reasoning tier (e.g. Haiku, Flash, mini variants), log an advisory: stronger reasoning models catch more edge cases; when `policy_profile=strict`, governance waypoints (Step 3 E021, evaluation chain) compensate. See `docs/reference/coding-agents.md`. Do not block the card on tier alone.

## Escalation diagnostic path (triggered at Step 1 Orient)

If `hermes kanban show <task_id>` block reason contains `[escalation:coding_agent:attempt:N]`:

1. This is a **DIAGNOSTIC run** — do NOT immediately spawn the coding agent.
2. Read the block reason and the eval chain output file referenced in it. (e.g. E003 → check test output; E002 → check which files were out of scope.) Do NOT open the codebase — the diagnosis comes from the error record, not code reading.
3. Diagnose root cause: was the `agent -p` prompt too broad? Ambiguous `Files:` path? Test command assumes a missing tool? Wrong approach for this card's scope?
4. Write a **REVISED** `agent -p` block: narrower scope, different strategy, explicit constraints. Do NOT write code. Do NOT edit files. You are revising the instructions, not the work.
5. Update the card body with the revised `agent -p` block.
6. Log: `bash scripts/kanban_intervention_inc.sh`
7. Proceed to Step 3 (Fast sanity) → worktree setup → Step 4 (spawn with revised prompt).
8. If coding agent fails again: retry internally (up to `escalation_max_attempts.worker` total).
9. After all worker retries exhausted: `kanban_block` with `[escalation:worker:attempt:N]` + diagnosis.

**Plan file availability (mandatory):** The full plan file must be accessible in the worktree for autonomous troubleshooting. The card body carries task-specific instructions, but when the cursor agent hits an unexpected failure, the worker needs the plan for root cause context, phase dependencies, and sad-path contingencies.

1. **Identify the plan file** — prefer `plan_file:` from the card body (stamped at decomposition). Else use `plan_id:` / `$HERMES_KANBAN_PLAN_ID` with the agent-neutral resolver (`.hermes/kanban/plans/` backup first, then `.agent/plans`, then `plan_search_dirs` from overlay):
```bash
PYTHONPATH=scripts/lib python3 -c "from plan_paths import resolve_plan_file; print(resolve_plan_file('.', '$PLAN_ID'))"
```

2. **Restore if missing** — checkout the resolved repo-relative path from `${working_branch}`:
```bash
git checkout origin/${working_branch} -- <plan_file_from_card_or_resolver>
```

3. **Verify readability** — confirm the plan has the expected sections (at minimum: frontmatter with `plan_id`, `## Fix design`, and `## Test plan`). If the plan is truncated or corrupted, block the card with reason "Plan file unavailable — cannot troubleshoot autonomously" and escalate to orchestrator.

**Why this matters:** Workers are autonomous supervisors. When a cursor agent fails a test, hits an import error, or produces code that doesn't match the `Files:` line, the worker reads the plan to decide: retry? block? salvage? Without the plan, every non-trivial failure becomes an intervention trigger — the worker has no context to self-heal. This check eliminates a class of unnecessary gateway notifications.

### Step 2 — Memory (fast path)
Check `.hermes/kanban/preflight_cache.json`. If timestamp < 30 min old:
- Auth is verified — skip auth check, skip smoke test
- Agent binary is known — skip ELF/shim debate
- Provider/model are known — skip provider discovery
- Branch prefix and repo root are known — skip branch discovery

Only check: disk space, git clean state, branch name matches card. **This step should take under 30 seconds.**

If the cache file is missing or stale (E012), run the full preflight (auth, shim, memory, branch) — but this is a degraded path that should only happen when the orchestrator skipped attestation.

**Plan memory (shared warm-up):** Load `.hermes/kanban/memory/<plan_id>.json` to skip re-discovering things other workers already learned. The memory follows the ordinal framework (questions 1–14) — positive space (1–8) for what IS needed, negative space (9–14) for what must NOT happen. The orchestrator seeds this at decomposition. Workers append discoveries on completion. This eliminates the 5–8 minute cold-start repeated across every card.

```bash
PLAN_ID="${HERMES_KANBAN_PLAN_ID:-}"
MEMORY_FILE=".hermes/kanban/memory/${PLAN_ID}.json"
if [ -f "$MEMORY_FILE" ]; then
  ORIENTATION=$(python3 -c "
import json
with open('$MEMORY_FILE') as f:
    d = json.load(f)
o = d.get('orientation', {})
print(f'worktree: {o.get(\"worktree\",{}).get(\"path_pattern\",\"?\")}')
print(f'auth: {o.get(\"auth\",{}).get(\"cursor_api_key_path\",\"?\")}')
pits = '; '.join(o.get('common_pitfalls', []))
print(f'pitfalls: {pits[:200]}')
" 2>/dev/null)
  echo "[memory] Plan orientation loaded"
fi
```

### Step 3 — Fast sanity (checklist waypoints)

Waypoint order: (1) heartbeat, (2) governed `worktree_setup.sh`, (3) kanban scripts present (E021), (4) scope file, (5) integration freshness, (6) coding-agent smoke. Raw `git worktree add` alone fails at waypoint 3.

- Confirm branch exists and matches card's `--branch`
- `git status --short` — should be clean or contain only expected artifacts
- Disk space > 1 GB (E007 if not)
- Working directory matches repo root (E011 if cross-mount)
- **Verification-only (takes precedence):** If the card has `Type: verification`, `Commit: N/A`, or `verification only` in the commit line — **even when an `agent -p` block is present** — this is a supervisor-worker card. Do NOT run `coding_agent_invoke.sh` smoke or dispatch. Run `Tests:` via `terminal()`, then run the evaluation chain (mandatory before `kanban_complete`). Set `metadata.verification` to the test command on complete. Skip Step 3 smoke for verification cards.
- **Agent block guard (E014):** If the card has **neither** an `agent -p` block **nor** a `Files:` line (and is not verification-only above), this is an orchestrator-only card (gate, audit, root) — do NOT spawn an agent; `kanban_complete(summary="Orchestrator-only card — no agent work to do.")`.

**Correct sequence within Step 3 (mandatory order):**

```bash
# 1. Start heartbeat thread FIRST — before worktree creation, before any I/O that can hang
start_heartbeat_thread

# 2. Call worktree_setup.sh from main repo / HERMES_HOME (never cwd-relative inside worktree)
REPO_ROOT="${HERMES_KANBAN_REPO_ROOT:-$(git rev-parse --show-toplevel)}"
# shellcheck source=scripts/lib/kanban_bundle.sh
source "${HERMES_HOME:-$HOME/.hermes}/scripts/lib/kanban_bundle.sh" 2>/dev/null \
  || source "$REPO_ROOT/hermes-kanban-advanced-workflow/scripts/lib/kanban_bundle.sh"
WORKTREE_SETUP="$(_resolve_kanban_script worktree_setup.sh "$REPO_ROOT")"
[ -n "$WORKTREE_SETUP" ] || WORKTREE_SETUP="$REPO_ROOT/hermes-kanban-advanced-workflow/scripts/worktree_setup.sh"
WORKTREE_OUTPUT=$(bash "$WORKTREE_SETUP" \
  --task-id "$HERMES_KANBAN_TASK" \
  --repo-root "$REPO_ROOT")
eval "$WORKTREE_OUTPUT"
cd "$WORKTREE_PATH"

# Waypoint 3: worktree-local kanban scripts prove worktree_setup / .worktreeinclude ran
if [ ! -f "$WORKTREE_PATH/.hermes/scripts/coding_agent_invoke.sh" ]; then
  echo "[E021] Worktree incomplete — re-run worktree_setup.sh (git worktree add alone is insufficient)"
  hermes kanban block "$HERMES_KANBAN_TASK" \
    "E021_WORKTREE_INCOMPLETE: missing kanban scripts — run worktree_setup.sh, not raw git worktree add"
  exit 1
fi

# 4. Write .kanban-scope to the worktree root (pre-commit hook reads this at commit time)
FILES_LIST=$(hermes kanban show "$HERMES_KANBAN_TASK" 2>/dev/null \
  | grep -E '^Files:' | sed 's/^Files: *//')
printf '%s\n' $FILES_LIST > "$WORKTREE_PATH/.kanban-scope"

echo "[worker] Worktree ready: $WORKTREE_PATH (pre-push + pre-commit hooks installed, scope written)"
```

> **Pre-push hook installed by `worktree_setup.sh`:** The hook prevents the coding agent from pushing to any branch other than the card's own worktree branch (`wt/<task_id>`). `working_branch` is always protected; `trigger_branch` is protected too when set in `kanban-config.yaml`. Branch names are read at install time — not hardcoded. This is infrastructure enforcement — the agent cannot bypass it regardless of what its prompt says.

- **Integration freshness check (mandatory):** Before spawning the agent, verify the worktree is based on the latest `${working_branch}`. If the parent card completed >1hr ago, the integration branch may have advanced with other cards' changes — the agent would work on stale code.

```bash
WORKTREE_BASE=$(git merge-base HEAD "origin/${working_branch}")
INTEGRATION_HEAD=$(git rev-parse "origin/${working_branch}")
if [ "$WORKTREE_BASE" != "$INTEGRATION_HEAD" ]; then
    echo "[worker] ${working_branch} has advanced — rebasing worktree before agent spawn"
    git fetch "origin/${working_branch}"
    git merge "origin/${working_branch}" --no-edit || {
        echo "[worker] Merge conflict with ${working_branch} — blocking for manual resolution"
        exit 1
    }
fi
```

- **Coding-agent smoke (mandatory, replaces log-grep):** Do NOT check for `[unauthenticated]` in worker logs — this is the Cursor background indexing service (cosmetic, not blocking). Do NOT rely on `agent status` alone — it shows OAuth state but not execution capability. Verify the configured binary can run a one-line prompt from the worktree using **`terminal()`** (not `execute_code`):

```bash
# Resolve plugin bundle (ordered fallbacks)
BUNDLE=""
for candidate in \
  "$(grep -E '^bundle_path:' .hermes/kanban-overrides/kanban-config.yaml 2>/dev/null | head -1 | sed 's/^bundle_path: *//; s/^[\"'\'']//; s/[\"'\'']$//')" \
  "${HERMES_HOME}/plugins/kanban-advanced" \
  "${HERMES_KANBAN_REPO_ROOT:-.}/hermes-kanban-advanced-workflow"; do
  [ -n "$candidate" ] && [ -f "$candidate/scripts/coding_agent_invoke.sh" ] && BUNDLE="$candidate" && break
done
[ -n "$BUNDLE" ] || BUNDLE="hermes-kanban-advanced-workflow"
INVOKE="$BUNDLE/scripts/coding_agent_invoke.sh"
[ -x "$INVOKE" ] || INVOKE="${HERMES_HOME}/scripts/coding_agent_invoke.sh"

# Smoke: allow up to 180s (cold Cursor start + JSON). Uses --trust for agent.
# coding_agent_invoke.sh sources scripts/lib/coding_agent_env.sh (sets HOME if missing).
cd "$WORKTREE_PATH"
timeout 180 bash "$INVOKE" smoke
```

If smoke fails, classify before blocking:

| Smoke signal | Block tag | Operator action |
|--------------|-----------|-----------------|
| `Authentication required`, `authentication`, timeout (exit 124), or hang with no output | `[escalation:coding_agent:auth]` | **Do not** use `attempt:N` retry ladder — auth is an operator fix. Operator runs `agent login` on the gateway host (Cursor), then deletes `.hermes/kanban/preflight_cache.json`, re-runs preflight / attestation, and unblocks. |
| `Workspace Trust Required` | `[escalation:coding_agent:trust]` | Confirm `coding_agent_invoke.sh` passes `--trust`; re-run `worktree_setup.sh` if trust files missing. |
| Other non-zero / empty JSON | E020 or `[escalation:coding_agent:attempt:1]` | Environment fix + one retry only if not auth/trust. |

```bash
# Example — auth failure (no 3× retry loop)
kanban_block "$HERMES_KANBAN_TASK" \
  "[escalation:coding_agent:auth] Cursor CLI OAuth expired — operator must run: agent login"
```

Do **not** fall back to direct coding on smoke failure.

Per-binary flags: `plugin/data/references/coding-agent-cli-invocation.md`. **Cursor (`agent`):** `-p --output-format json --trust` (the invoke script adds these). Exit 1 with `Workspace Trust Required` means `--trust` was omitted — not missing JSON support. The Cursor CLI ignores `CURSOR_API_KEY`; it authenticates via OAuth in `~/.config/cursor/auth.json`. **`agent status` is not sufficient** — it can show logged-in while `agent -p "say ok" --trust` still fails when the token is stale (~9+ days).

- **Workspace trust:** `worktree_setup.sh` pre-trusts the worktree using a cross-platform hash (Windows drive-letter paths: strip colon, replace `\` and `/` with `-`; Unix paths: strip leading `/`, replace `/` with `-`). Still pass `--trust` on every Cursor headless call.

### Step 4 — Handoff to coding agent

**Skip Step 4 entirely for verification-only cards** (`Type: verification`, `Commit: N/A`, or `verification only` in commit line) — even if an `agent -p` block is present. Run `Tests:` via `terminal()`, then the evaluation chain, then `kanban_complete`. Do not dispatch the coding agent.

**Dispatch mechanism (mandatory for code-gen cards):** Use the **`terminal()`** tool to run the coding CLI. Do **not** use `execute_code` (cannot host 900s subprocesses). Do **not** call bare `coding_agent_invoke.sh` without a resolved path (exit 127). If dispatch fails, `kanban_block` with evidence — **never** fall back to direct coding.

Do NOT construct the prompt from scratch. Extract the fenced `agent` block from the card body, prepend governance + memory brief, then dispatch via the shared invoke script. Start the heartbeat thread before the agent call.

**Coding agent governance block (mandatory):** Prepend `plugin/data/references/coding-agent-governance.md` before the extracted prompt. The governance block is enforced post-hoc by the evaluation chain (E001–E006), but prompt-level guardrails reduce remediation burden.

```bash
# The card body contains:
# ```agent
# agent -p "Implement WS3 per plan §Phase 1, Workstream 3. ..."
# ```
BUNDLE=""
for candidate in \
  "$(grep -E '^bundle_path:' .hermes/kanban-overrides/kanban-config.yaml 2>/dev/null | head -1 | sed 's/^bundle_path: *//; s/^[\"'\'']//; s/[\"'\'']$//')" \
  "${HERMES_HOME}/plugins/kanban-advanced" \
  "${HERMES_KANBAN_REPO_ROOT:-.}/hermes-kanban-advanced-workflow"; do
  [ -n "$candidate" ] && [ -f "$candidate/scripts/coding_agent_invoke.sh" ] && BUNDLE="$candidate" && break
done
[ -n "$BUNDLE" ] || BUNDLE="hermes-kanban-advanced-workflow"
INVOKE="$BUNDLE/scripts/coding_agent_invoke.sh"
[ -x "$INVOKE" ] || INVOKE="${HERMES_HOME}/scripts/coding_agent_invoke.sh"

GOVERNANCE=$(cat "$BUNDLE/plugin/data/references/coding-agent-governance.md" 2>/dev/null)
if [ -z "$GOVERNANCE" ]; then
  GOVERNANCE="## Governance
### Files boundary
You MUST ONLY modify files listed in Files: below. Do NOT install packages,
modify configs, or touch files outside the Files: list.
### If blocked: report exact error to worker. Do NOT guess."
fi
AGENT_PROMPT="$(extract_agent_block_from_body)"

# Step 4 preamble — inject prior context (last 5 completed_cards)
memory_file=".hermes/kanban/memory/${PLAN_ID}.json"
brief=""
if [ -f "$memory_file" ]; then
  brief=$(python3 -c "
import json
with open('$memory_file') as f:
    data = json.load(f)
cards = data.get('completed_cards', [])[-5:]
if cards:
    lines = ['Prior context (do not re-read the codebase — this is the summary):']
    for c in cards:
        lines.append(f\"- {c.get('title','')}: {c.get('state_left','')}\")
        for constraint in c.get('constraints', []):
            lines.append(f'  constraint: {constraint}')
    print('\\n'.join(lines) + '\\n')
" 2>/dev/null)
fi

FULL_PROMPT="$GOVERNANCE

---

${brief}${AGENT_PROMPT}"

# terminal() example — run from worktree; allow up to 900s for the coding agent
cd "$WORKTREE_PATH"
timeout 900 bash "$INVOKE" dispatch "$FULL_PROMPT" \
  > "${KANBAN_TEMP:-${TMPDIR:-/tmp}}/agent_output_${HERMES_KANBAN_TASK}.json" 2>&1
AGENT_OUTPUT=$(cat "${KANBAN_TEMP:-${TMPDIR:-/tmp}}/agent_output_${HERMES_KANBAN_TASK}.json")

# Extract token data when the CLI returns JSON (Cursor / Claude):
if echo "$AGENT_OUTPUT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if not d.get('is_error'):
    usage = d.get('usage', {})
    print(usage.get('inputTokens', 0))
    print(usage.get('outputTokens', 0))
" 2>/dev/null; then
    echo "[worker] Agent output captured for token extraction"
fi
```

> **Model injection (config, not card body):** `KANBAN_CODING_AGENT` and `KANBAN_CODING_AGENT_MODEL` come from `kanban-config.yaml` / `.env` (dashboard **Save** or init). Do **not** put `--model`, `--output-format`, or `--trust` in the card body's fenced block — P005 blocks model overrides in the card; the invoke script injects headless flags at dispatch time. Hermes profile `model.default` governs **Hermes** sessions only, not the external coding agent.

### Step 5 — Monitor

Heartbeat every 3 minutes during agent execution. If no file changes in 5 minutes, investigate.

**Salvage before crash (mandatory):** When the agent exits (regardless of exit code), BEFORE deciding it crashed, check for commits:

```bash
# Agent exited — check for work BEFORE blocking
NEW_COMMITS=$(git log --oneline HEAD~5..HEAD 2>/dev/null | wc -l)
AGENT_COMMIT=$(git log --oneline -1 --grep="$(echo $COMMIT_MSG | head -c 30)" 2>/dev/null)

if [ -n "$AGENT_COMMIT" ] || [ "$NEW_COMMITS" -gt 0 ]; then
  echo "[worker] Agent produced commits — proceeding to verification"
  # Go to Step 6 (Verify), do NOT block
else
  echo "[worker] No commits found — agent produced no output"
  # Worker tracks coding-agent retries; tag encodes attempt count at coding_agent level
  kanban_block "$TASK_ID" "[escalation:coding_agent:attempt:1] Agent exited without producing commits"
  exit 1
fi
```

If the agent produced commits but exited without calling `kanban_complete` (protocol violation), that's a salvage path — proceed to verification, run the eval chain, and complete the card. Do NOT block a card that has committed work. Only block if there are genuinely zero commits AND the agent crashed/timed out.

### Step 6 — Verify (mandatory, post-agent, gated by evaluation chain)

**The worker must run the deterministic evaluation chain. Calling `kanban_complete` directly without running the chain is a protocol violation. The chain is a hard gate — no path to Step 7 without ALLOW on every step.**

```bash
python hermes-kanban-advanced-workflow/scripts/kanban_evaluation_chain.py <task_id> <workspace> --baseline HEAD~1
```

The evaluation chain runs deterministic steps (AEP DAL pattern). Each returns ALLOW or DENY. **The chain stops at the first DENY.** No step is optional. No step is a warning — every DENY blocks the card.

| Step | Code | What it checks | On DENY |
|------|------|---------------|---------|
| 1. Files: compliance | E001 | Every file in `Files:` has >0 changes in diff **or** `find_prior_commit` ALLOW (prior commit touched full `Files:` list) | Block — widen baseline or fix `Commit:` stamp so post-flight Tier 1 can clear the same path |
| 2. Unlisted changes | E002 | **Hard gate.** Auto-revert files modified outside `Files:`. If revert fails, DENY. | Block — agent modified files it wasn't authorized to touch. Orchestrator investigates. |
| 3. Test pass | E003 | Run `Tests:` command, all must pass | Block — fix code or split card |
| 4. Commit match | E004 | `git log -1 --format=%s` matches `Commit:` line | Block — commit message mismatch |
| 5. Token log written | E018 | `tokens.jsonl` has an entry with matching `task_id`, source=`agent`, and non-zero token count | Block — cannot attribute burn to plan. Fix token_tracker import. |
| 6. Zero-output check | E006 | At least one `Files:` file has >0 diff | Block — agent produced no code |
| 7. Agent output capture | E020 | Agent's JSON output saved and parseable | Block — can't verify what agent did |
| 8. Excessive churn | E017 | Net line changes < 3× estimate | Block — agent rewrote more than expected. Orchestrator reviews. |

**E002 is a hard gate.** The auto-revert MUST succeed. If `git checkout HEAD~1 -- <unlisted_file>` fails (merge conflict, file didn't exist before), the card blocks. The orchestrator must investigate why the agent modified files outside its scope — this is a governance violation, not a cleanup task.

**E018 is a hard gate.** The token log entry MUST exist for this task. If `tokens.jsonl` has no entry with matching `task_id`, source=`agent`, and non-zero tokens, the card blocks. The orchestrator can manually add the entry and unblock, but the worker must not complete without token attribution.

**Acceptance / Call-sites verify (standard for code-gen cards):** After the evaluation chain returns ALLOW, compare the worktree against the card's `Acceptance:` and `Call-sites:` lines. If any surface is unmet, **re-dispatch the coding agent** on the same card (do not `kanban_complete`) until satisfied or iteration budget is exhausted. Load `kanban-advanced:kanban-git` before Step 3 when the card lists `Parent-branches:` or parent integration prose. See `wiki/governance.md` § Role-based completeness loop (worker catch vs orchestrator remediation).

**Lattice memory (AEP attractor pattern):** After successful completion, the chain writes a lattice memory entry with files + tests hash. Subsequent workers with matching attractor_hash skip cold-path validation for steps 1, 3, and 4. Steps 2, 5, and 6 always run — scope enforcement and token attribution are never cached.

**Retry-safe verification (--check-only pattern):**

Run the evaluation chain with `--check-only` first to avoid premature blocking:

```bash
python3 scripts/kanban_evaluation_chain.py <task_id> <workspace> --check-only
```

**Retry ladder (up to 3 attempts — matches `kanban.failure_limit` default of 2 + initial):**
1. First run → DENY: diagnose the error code, apply fix, retry.
2. Second run → DENY: deeper diagnosis, apply fix, retry.
3. Third run → DENY: `kanban_block` with the final error code. Do NOT retry further.

On ALLOW at any attempt: call `kanban_complete` with summary and metadata.

**STOP AFTER BLOCKING:** Once `kanban_block` is called, the worker session MUST stop. Do not continue troubleshooting a blocked card — the orchestrator handles blocked cards via the board keeper and escalation pipeline.

| Error | Retryable? | Fix before retry |
|-------|-----------|------------------|
| E001  | Yes | Widen baseline or stamp Commit: |
| E003  | Yes | Fix import path, test command, or deps |
| E004  | Yes | Amend commit message |
| E006  | Yes | Check worktree, auth, prompt |
| E018  | Yes | Capture agent JSON; write token log |
| E020  | Yes | Re-dispatch with JSON capture |
| E023  | NO | Escalate immediately — repeated identical error |

If the chain script is missing (E013), block the task immediately — governance cannot proceed.

### Goal-mode dispatch (`HERMES_KANBAN_GOAL_MODE`)

When the dispatcher sets `HERMES_KANBAN_GOAL_MODE=1`, the worker may run **multiple Hermes turns** in the same session. The upstream judge re-checks card title + body (`Acceptance:`) after each turn until done, budget exhausted, or `kanban_block` / `kanban_complete`.

**Worker rules:**

- After **each** coding-agent handoff, run Steps 5–6 (monitor → evaluation chain) before `kanban_complete`.
- Do **not** skip the evaluation chain because the Hermes judge said continue or done.
- Log tokens on every coding-agent invocation (Step 6 token log still applies per turn).
- Long `running` state is expected; do not treat as a stall until `goal_max_turns` or block.
- If budget exhausts, upstream blocks the card — escalate via `kanban-advanced:kanban-notify`; do not silently exit.

See `plugin/data/references/goal-card-selection.md` and `docs/how-to/goal-cards.md`.

### Step 7 — Complete

**`kanban_complete` is gated. Do not call it unless Step 6 returned ALLOW on every step.** If any step returned DENY, the card is already blocked — do not complete it. Salvage paths (agent produced commits but worker crashed) run the full eval chain before completing.

```python
# Only after eval chain passes ALL steps:
kanban_complete(
    summary="<one-line description of what shipped>",
    metadata={
        "changed_files": [...],
        "tests_run": N,
        "tests_passed": N,
        "commit": "<sha>",
        "evaluation_chain": "passed",
        "token_log_written": True,  # E005 verified
    },
)
```

**Append plan memory (`completed_cards`):** After successful completion, append structured coding-agent output context to `.hermes/kanban/memory/<plan_id>.json` so subsequent workers can inject a brief in Step 4. Keep ≤5 bullets across `decisions` + `constraints`.

```python
import json, os, datetime, subprocess

plan_id = os.environ.get("HERMES_KANBAN_PLAN_ID", "")
task_id = os.environ.get("HERMES_KANBAN_TASK", "")
memory_file = f".hermes/kanban/memory/{plan_id}.json"
title = os.environ.get("HERMES_KANBAN_TASK_TITLE", task_id)

changed = subprocess.run(
    ["git", "diff", "--name-only", "HEAD~1..HEAD"],
    capture_output=True, text=True,
).stdout.strip().splitlines()

entry = {
    "task_id": task_id,
    "title": title,
    "completed": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "files_changed": changed,
    "decisions": [],  # fill from card metadata if available
    "constraints": [],  # forward-looking notes for the next card's agent
    "state_left": "evaluation chain passed",
}

if os.path.exists(memory_file):
    with open(memory_file) as f:
        data = json.load(f)
else:
    data = {"orientation": {}, "discoveries": [], "completed_cards": []}

data.setdefault("completed_cards", []).append(entry)
data["last_updated"] = entry["completed"]
with open(memory_file, "w") as f:
    json.dump(data, f, indent=2, default=str)
```

If verification fails at any point, `kanban_block` with the specific error code and escalation tag when retries are exhausted, e.g. `[escalation:worker:attempt:N] E003: tests still failing after retry`. Do NOT complete a task that didn't pass the evaluation chain.

## Commit cadence

**After completing each section of a plan, commit and push before moving to the next.** This is not optional — it is the single most effective protection against losing work to a gateway timeout or runtime crash.

**Rule:** When the orchestrator merges a section's worktree branch into `${working_branch}`, it immediately pushes `${working_branch}`. Workers never push directly to `${working_branch}` — they commit to their own worktree branch (`wt/<card-name>`) and signal `kanban_complete`. The orchestrator handles the merge.

## Workspace handling

**All code-generation cards must use `worktree` workspace.** `scratch` workspaces have no project files — agents cannot find the repo and will complete with zero changes. The only exception is cards that generate standalone output (reports, analysis) with no dependency on the codebase.

| Kind | When to use |
|------|-------------|
| `worktree:<repo-path>` | **Default for all code-gen cards.** Agents commit to `wt/<card-name>` branch. |
| `dir:<path>` | Shared data that outlives a single task. |
| `scratch` | Report generation or analysis with no codebase dependency. Never for code changes. |

If a code-gen card was created with `scratch` workspace, block it immediately: the agent will produce zero output.

## Good summary + metadata shapes

**Coding task:**
```python
kanban_complete(
    summary="shipped rate limiter — token bucket, keys on user_id with IP fallback, 14 tests pass",
    metadata={
        "changed_files": ["rate_limiter.py", "tests/test_rate_limiter.py"],
        "tests_run": 14,
        "tests_passed": 14,
        "decisions": ["user_id primary, IP fallback for unauthenticated requests"],
        "evaluation_chain": "passed",
    },
)
```

## Mandatory post-agent verification

After an external coding agent completes, run the evaluation chain — not manual checks. See Step 6 above.

## Token observability (mandatory — worker fails without it)

Token attribution from planning through cleanup is a **hard requirement**. Every token burned by Hermes sessions and external coding agents must be attributed to a plan. Project managers use this data to budget token burn per sprint and scope project waterfalls.

After the external agent completes and before `kanban_complete`, log token usage. The worker MUST call `log_token_run()` on EVERY completion path — success, salvage, and protocol-violation recovery. If the import fails, the worker blocks the card with reason "Token tracker unavailable — cannot attribute burn to plan."

### Import (with fallback)

```python
import json, os, sys

# Try project-local token_tracker first, fall back to hermes-kanban-advanced-workflow
try:
    sys.path.insert(0, os.environ.get("HERMES_KANBAN_REPO_ROOT", os.getcwd()))
    from scripts.token_tracker import log_token_run
except ImportError:
    try:
        repo = os.environ.get("HERMES_KANBAN_REPO_ROOT", "")
        bundle = os.path.join(repo, "hermes-kanban-advanced-workflow")
        sys.path.insert(0, bundle)
        from scripts.token_tracker import log_token_run
    except ImportError:
        kanban_block(
            task_id=os.environ["HERMES_KANBAN_TASK"],
            reason="Token tracker unavailable — cannot attribute burn to plan",
        )
        sys.exit(1)
```

### Log both cursor and Hermes tokens

Cursor CLI `--output-format json` exposes `usage.inputTokens`, `usage.outputTokens`, `usage.cacheReadTokens`, `usage.cacheWriteTokens`.

For Hermes session tokens, the worker captures its own token burn by reading the session state. The `/usage` slash command or `hermes sessions stats` provides token totals. If programmatic access isn't available, estimate from turn count × system prompt size (3,000 tokens/turn), and mark the estimate.

```python
agent_usage = {}
agent_duration_ms = 0
try:
    agent_output = json.loads(result.stdout)
    agent_usage = agent_output.get("usage", {})
    agent_duration_ms = agent_output.get("duration_api_ms", 0)
except (json.JSONDecodeError, KeyError):
    pass

# Hermes tokens: try exact from session, fall back to turn-count estimate
hermes_turns = int(os.environ.get("HERMES_KANBAN_TURNS", "3"))
hermes_token_estimate = hermes_turns * 3000  # system prompt + tool schemas ≈ 3K/turn
hermes_total = int(os.environ.get("HERMES_SESSION_TOKENS", str(hermes_token_estimate)))

log_token_run(
    plan_id=os.environ.get("HERMES_KANBAN_PLAN_ID", ""),
    task_id=os.environ.get("HERMES_KANBAN_TASK", ""),
    cursor_input_tokens=agent_usage.get("inputTokens", 0),
    cursor_output_tokens=agent_usage.get("outputTokens", 0),
    cursor_cache_read_tokens=agent_usage.get("cacheReadTokens", 0),
    cursor_cache_write_tokens=agent_usage.get("cacheWriteTokens", 0),
    cursor_model="<model-name>",
    duration_seconds=agent_duration_ms / 1000.0 if agent_duration_ms else 0,
    hermes_input_tokens=0,
    hermes_output_tokens=0,
    hermes_total_tokens=hermes_total,
    hermes_turns=hermes_turns,
    status="completed",
)
```

### Log on every completion path

| Path | What to log |
|------|-------------|
| Agent success → `kanban_complete` | Full cursor + hermes token data |
| Salvage (commit exists, worker crashed) | Cursor tokens from agent output + hermes estimate |
| Protocol violation (no commit) | Hermes tokens only (session overhead) + `status: "protocol_violation"` |
| Blocked (environment failure) | Hermes tokens only + `status: "blocked"` |

The orchestrator reads `tokens.jsonl` during reconciliation and the postmortem generator uses it for §7 Token Economics. **Zero token entries for a plan = failed postmortem.** The orchestrator must investigate which worker/script didn't write to the log and harden the gap before the next plan run.

## External coding agent patterns

### Decide: agent or terminal?

Agents are for **code generation** only. Use **terminal commands directly** for pipeline execution (test suites, benchmarking, schema regeneration, git merges).

- ✓ Agent: `"add foo_helper function to utils.py"`
- ✗ Agent: `"re-run test suite and record results"` → use terminal

### Heartbeat pattern (mandatory)

Heartbeat every 3-5 minutes during agent execution to prevent the 15-minute reclaim cycle:

```python
import threading, time, os, subprocess

stop = threading.Event()
task_id = os.environ["HERMES_KANBAN_TASK"]

def _heartbeat_loop():
    start = time.time()
    while not stop.is_set():
        elapsed = int(time.time() - start)
        kanban_heartbeat(
            task_id=task_id,
            note=f"Agent running — {elapsed//60}m elapsed"
        )
        stop.wait(timeout=180)

hb = threading.Thread(target=_heartbeat_loop, daemon=True)
hb.start()
from plugin.coding_agent import build_dispatch_argv

coding_agent = os.environ.get("KANBAN_CODING_AGENT", "agent")
coding_model = os.environ.get("KANBAN_CODING_AGENT_MODEL", "auto")
try:
    result = subprocess.run(
        build_dispatch_argv(coding_agent, prompt, coding_model),
        capture_output=True, text=True, timeout=900, cwd=workspace
    )
finally:
    stop.set()
    hb.join(timeout=5)
```

### Do NOT

- Modify files outside `$HERMES_KANBAN_WORKSPACE` unless the task body says to.
- Create follow-up tasks assigned to yourself.
- Complete a task you didn't actually finish. Block it instead.
- Call `kanban_complete` directly — always go through the evaluation chain (Step 6).
- Push only to your assigned worktree branch — never to `${working_branch}` (E009 applies when `trigger_branch` is set in config).
- Use `git add -A` — use `git add <specific files>` to avoid staging unrelated changes.

## Provider/model fallback chain (Hermes sessions only)

This section applies to **Hermes** worker/orchestrator turns (`hermes chat`, heartbeats, eval tooling) — **not** the external coding CLI. Coding-agent binary and model come from `KANBAN_CODING_AGENT` / `KANBAN_CODING_AGENT_MODEL` and `coding_agent_invoke.sh` (see Step 4).

For Hermes sessions, the profile's configured model from `config.yaml` applies (not hardcoded in the card body — see P005_MODEL_OVERRIDES_PROFILE). When the configured provider fails, follow the same SOP as Hermes Agent:

1. **Primary:** Use the profile's `model.default` and `model.provider` from `config.yaml`.
2. **Profile fallbacks:** If the primary provider fails (HTTP 429, connection error, timeout), try `fallback_providers` configured in the profile's `config.yaml`. Retry once per fallback provider before escalating.
3. **Global fallback:** If all profile-level providers are exhausted, fall back to the **primary `config.yaml`** (`$HERMES_HOME/config.yaml` or `~/.hermes/config.yaml`).
4. **Escalate:** If the primary config also fails, block the task with the error code and trigger intervention per `kanban-advanced:kanban-notify`.

**Applicable error codes:** E008 (network down — retryable, triggers fallback). **Non-applicable:** PR001 (no `config.yaml`) is a config issue, not a provider failure; auth failures are caught before handoff.

## Retry scenarios

If `kanban_show` returns prior runs, you're a retry. Don't repeat the failed path:

- `timed_out` — chunk the work or shorten it.
- `crashed` — OOM or segfault. Reduce memory footprint.
- `spawn_failed` — usually a profile config issue. Block with evidence.
- `protocol_violation` — worker exited cleanly without signaling. Common causes: (a) agent -p block missing from card body (orchestrator-only card assigned to worker) — guard this in Step 3; (b) agent crashed but worker didn't catch the signal. Check `git log` — agent may have already committed everything needed.

## Startup optimization (fast-path)

Workers waste 5–8 minutes per task running identical pre-flight checks. Use the fast path: check `.hermes/kanban/preflight_cache.json`. If < 30 min old, skip auth/shim/memory. Always check disk space, branch, git clean state.

## Pitfalls

> **Full error code reference + pitfall narratives → `kanban-advanced:kanban-worker-governance`.** Load the governance reference skill when you hit a DENY or need diagnostic context.

**Key procedural pitfalls (see governance ref for full context):**
- Always heartbeat during agent execution (15-minute reclaim cycle).
- Never push to `${working_branch}` — commit to worktree branch only.
- `git reset --hard` destroys plan files — restore with `git checkout ${working_branch} -- .hermes/kanban/plans/`.
- Agent `-p` is for code generation only — pipeline execution uses terminal commands.
- Never call `kanban_complete` directly — always run the evaluation chain (E001–E023).
- Cursor `[unauthenticated]` in logs is cosmetic — use Step 3 `coding_agent_invoke.sh smoke` for auth.
- `CURSOR_API_KEY` is a decoy env var — Cursor CLI uses OAuth in `~/.config/cursor/auth.json`.
- Pre-create `.workspace-trusted` before spawning agent in `/tmp` worktrees.
- Salvage iteration-limit cards before re-dispatching — check the worktree for commits.
- Hung-agent detection: investigate after 5 minutes with zero file changes.
