# In-flight governance index

**Load:** `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")`  
**Worktree:** resolve `BUNDLE` below, then `cat "$BUNDLE/plugin/skills/kanban-advanced/references/in-flight-governance-index.md"`

**Format (Rootly 5 A's):** Keywords | Layer | Tier | Belt | First command | Verify | Deep dive  
**Tiers:** T1=BB self-serve | T2=MBB | T3=Operator  
**Matrices:** `wiki/governance.md#full-pre-execution-governance-stack` (MBB / repo root only)

## Bundle resolution

```bash
BUNDLE=""
for candidate in \
  "$(grep -E '^bundle_path:' .hermes/kanban-overrides/kanban-config.yaml 2>/dev/null | head -1 | sed 's/^bundle_path: *//; s/^[\"'\'']//; s/[\"'\'']$//')" \
  "${HERMES_HOME}/plugins/kanban-advanced" \
  "${HERMES_KANBAN_REPO_ROOT:-.}/hermes-kanban-advanced-workflow"; do
  [ -n "$candidate" ] && [ -f "$candidate/scripts/coding_agent_invoke.sh" ] && BUNDLE="$candidate" && break
done
```

## L0 — Goal cards (MBB)

| Keywords | Layer | Tier | Belt | First command | Verify | Deep dive |
|----------|-------|------|------|---------------|--------|-----------|
| `goal_card` attestation fail | L0 | T2 | MBB | `python3 "$BUNDLE/scripts/verify_goal_cards.py" --plan <plan>.md` | Exit 0 | `goal-card-selection.md` |
| `G003` goal budget | L0 | T2 | MBB | Fix plan `###` sections + `Acceptance:` | `verify_goal_cards.py` pass | `wiki/governance.md` § L0 |

## L1–L2 — Preflight / gate (MBB)

| Keywords | Layer | Tier | Belt | First command | Verify | Deep dive |
|----------|-------|------|------|---------------|--------|-----------|
| preflight fail | L1 | T2 | MBB | `bash "$BUNDLE/scripts/preflight.sh"` | JSON `status` pass/degraded | `kanban-preflight` skill |
| `A001`/`A002` attestation | L1 | T2 | MBB | `python3 "$BUNDLE/scripts/kanban_attestation.py" <plan_id>` | PASS stamped | `wiki/governance.md` § L1 |
| `A003` tamper | L1 | T3 | Op | Re-run preflight + attestation from clean state | New attestation checksum | T3 — investigate |
| gate FAIL | L2 | T2 | MBB | `bash "$BUNDLE/scripts/pre_dispatch_gate.sh" <plan_id>` | 0 failures | `wiki/governance.md` § L2 |
| subagent gate timeout / E022 | L2 | T2 | MBB | Serial fallback: `pre_dispatch_gate.sh` | Match or fix domain | `parallel-subagent-gate.md` |
| model ping / stepfun silent | L1 | T2 | MBB | `preflight.sh`; fix profile model YAML | `model_reachability` pass | `coding-agent-auth.md` |
| `Unknown provider nous portal` | L1 | T3 | Op | Set `model.provider: nous` in profile config | Worker chat responds | `wiki/troubleshooting.md` |

## L3 — Handoff (MBB / default chat)

| Keywords | Layer | Tier | Belt | First command | Verify | Deep dive |
|----------|-------|------|------|---------------|--------|-----------|
| handoff exit 2–4 | L3 | T2/T3 | MBB/Op | Follow `kanban_handoff.py` printed fix | Handoff card created | `decomposition-workflow.md` § handoff |
| handoff `ready` 10+ min | L3 | T2 | MBB | Restart gateway; `kanban.dispatch_in_gateway` | Orchestrator spawned | `decomposition-workflow.md` |
| decompose `--plan` fail | L3 | T2 | MBB | `--cards-yaml .hermes/kanban/memory/<id>.yaml` | Cards have worktree | `kanban_handoff.py` |
| read full 958-line plan | L3 | T1 | MBB | Runbook only — skip `read_file` Plan | Gate + crons from body | handoff runbook |
| `worker_context` noise | L3 | T1 | MBB | Ignore archived done cards | Fresh decompose proceeds | orchestrator skill L64 |
| wrong profile decompose | L3 | T2 | MBB | `python3 "$BUNDLE/scripts/kanban_handoff.py" --plan …` | Dispatcher spawns orch | `profile-switching.md` |

## L4 — Decompose / crons (MBB)

| Keywords | Layer | Tier | Belt | First command | Verify | Deep dive |
|----------|-------|------|------|---------------|--------|-----------|
| scratch workspace | L4 | T2 | MBB | `validate_board.sh`; re-decompose `--cards-yaml` | `worktree` on impl cards | `wiki/troubleshooting.md` |
| duplicate gate | L4 | T2 | MBB | `kanban_decompose.py --gate-id <id>` | One gate card | orchestrator § Standard process |
| crons missing | L4 | T2 | MBB | `provision_kanban_crons.sh --check` | auto-unblock + keeper | `wiki/troubleshooting.md` § crons |
| `validate_board` fail | L4 | T2 | MBB | `bash "$BUNDLE/scripts/validate_board.sh"` | Exit 0 | P-codes in governance skill |
| `P001`–`P009` | L4 | T2 | MBB | `kanban_card_policy.py` on card body | Policy pass | `error-codes.yaml` |

## L5-pre — Worktree provisioning (BB → Op)

| Keywords | Layer | Tier | Belt | First command | Verify | Deep dive |
|----------|-------|------|------|---------------|--------|-----------|
| `E021`, exit 127 | L5-pre | T1 | BB | `worktree_setup.sh --task-id <id> --repo-root <repo>` | `.hermes/scripts/coding_agent_invoke.sh` in WT | `operator-provisioning.md` |
| plan file missing | L5-pre | T1 | BB | `git checkout origin/${working_branch} -- .hermes/kanban/plans/*{plan_id}*` | Plan readable | worker skill orient |
| `.env` / venv missing | L5-pre | T3 | Op | Add paths to `.worktreeinclude`; operator provisions | Tests run in WT | `operator-provisioning.md` |
| stale materialized skill | L5-pre | T2 | MBB | Update Plugin + gateway restart | SKILL mtime fresh | `handoff-regression-checklist.md` |

## L5 — Worker pre-exec / dispatch (BB)

| Keywords | Layer | Tier | Belt | First command | Verify | Deep dive |
|----------|-------|------|------|---------------|--------|-----------|
| `[escalation:coding_agent:auth]`, HOME | L5 | T1→T3 | BB | `coding_agent_invoke.sh smoke` with `HOME` set | JSON stdout | `wiki/troubleshooting.md` § OAuth |
| worker codes directly | L5 | T1 | BB | `terminal()` + `coding_agent_invoke.sh dispatch` | Agent subprocess in log | worker-governance |
| stale `devops/kanban-worker` | L5 | T2 | MBB | Update Plugin; qualified skill names | Plugin skill path | `wiki/troubleshooting.md` |
| `--output-format json` exit 1 | L5 | T1 | BB | Use invoke script (`--trust`) | Smoke pass | `coding-agent-cli-invocation.md` |
| `E014` verification | L5 | T1 | BB | Run `Tests:` via `terminal()` only | No agent dispatch | worker skill Step 3 |
| `verification-local` / legacy `Type: verification` | L5 | T1 | BB | `Tests:` only — no `Files:` / agent block | `validate_board.sh` pass | `plan-file-format.md` § Verification taxonomy |
| `verification-deploy` unattested | L5 | T2 | MBB | Orchestrator writes `.hermes/kanban/card-attestations/{plan_id}-{card_key}.json` | JSON exists before archive | `frontend-neutrality.md` § Attestation |

## L6 — Evaluation chain (BB)

| Keywords | Layer | Tier | Belt | First command | Verify | Deep dive |
|----------|-------|------|------|---------------|--------|-----------|
| `E001` salvaged / HEAD~1 | L6 | T1 | BB | `kanban_evaluation_chain.py --baseline HEAD~20` | ALLOW or re-dispatch | `plugin/data/references/salvage-pattern-iteration-exhausted-cards.md` |
| `E003`/`E006` retry | L6 | T1 | BB | `kanban_recover.py --list`; fix + retry | Chain ALLOW | worker-governance |
| `E018`/`E020` tokens | L6 | T1 | BB | Capture agent JSON stdout; `token_tracker` | Exact log entry | worker-governance |
| `E028` layout acceptance | L6 | T1 | BB | Fix route shell per `Acceptance (layout):`; re-run chain | ALLOW | `frontend-neutrality.md` |
| `E029` a11y acceptance | L6 | T1 | BB | Add reduced-motion guard per `Acceptance (a11y):` | ALLOW | `frontend-neutrality.md` |
| iteration limit 90/90 | L6 | T2 | MBB | Salvage commits — do not re-dispatch | Merge to staging | salvage reference |

## L7 — Final audit / post-flight remediation (MBB)

| Keywords | Layer | Tier | Belt | First command | Verify | Deep dive |
|----------|-------|------|------|---------------|--------|-----------|
| final audit exit 2 | L7 | T2 | MBB | Read stderr; fix plan/git/DB | Re-run `--tier all` exit 0 | `final-audit-sanity-check.md` |
| tier1/tier2 violations | L7 | T2 | MBB | `python3 "$BUNDLE/scripts/final_audit_sanity.py" --plan-id <id> --tier all` | Exit 0 or spawn | `final-audit-sanity-check.md` |
| plan_file_zero_diff after E001 | L7 | T2 | MBB | Fix done card `Files:` + `Commit:`; re-run tier 1 | No violation | `final-audit-sanity-check.md` § Tier 1 ↔ E001 |
| remediation wave stuck | L7 | T2 | MBB | `hermes kanban list --parent <audit_tid>` | No running/blocked children | `final-audit-sanity-check.md` § sad-path |
| max rounds exceeded | L7 | T2/T3 | MBB/Op | Review tier JSON; operator triage | Audit blocked + escalation | `wiki/configuration.md` § final audit |
| gave_up remediation | L7 | T3 | Op | Escalation tracker output on audit card | Violations marked `escalated` in tier JSON | governance § completeness loop |
| doc coverage false positive | L7 | T2 | MBB | Add `final_audit_overrides` in overlay | `approved_skip` in tier2 JSON | `final-audit-doc-coverage.md` |
| check13 fail | L7 | T2 | MBB | Close or archive remediation children | `validate_board.sh` exit 0 | orchestrator skill § Final audit |
| verification-deploy archived without attestation | L7 | T2 | MBB | Write card-attestation JSON; re-open card | `final_audit_sanity.py` clean | `plan-file-format.md` § Card attestation |

## Recover + regression

```bash
python3 "$BUNDLE/scripts/kanban_recover.py" --list
python3 "$BUNDLE/scripts/kanban_recover.py" <task_id> <code>   # retryable E only
python3 "$BUNDLE/scripts/kanban_recover.py" --cascade <plan_id>  # MBB pause/resume
```

**Handoff regression:** `plugin/data/references/handoff-regression-checklist.md`  
**Historical `.hermes/docs/kanban-*`:** promote symptoms into this index (DMAIC Improve — `kanban-postmortem`).
