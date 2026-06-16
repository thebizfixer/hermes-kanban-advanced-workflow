# Kanban-Advanced Governance — Full Sad-Path Audit

> **Date:** 2026-05-27 · **Scope:** Every transition in the README flowchart, traced for leakproofness.
> **Method:** For each transition, ask: "What happens if this step fails silently? What if the orchestrator skips it? What if the environment changes mid-step?"

---

## Flowchart Trace

```
DRAFT → HARDEN → REVISE → OPTIMIZE → PREFLIGHT → ATTEST → DECOMPOSE → EXECUTE → VERIFY → AUDIT → RECONCILE → POSTMORTEM → CLEANUP
```

---

## 1. DRAFT → HARDEN

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Plan has no file paths | Medium | BLOCKING | Planning skill § Plan structure requires file paths | ⚠️ Manual — no structural check |
| Plan scope too large for kanban | Medium | WASTED | Scope-appropriateness gate in planning skill | ⚠️ Manual — orchestrator must self-assess |
| User writes plan externally, no Draft step | Low | DEGRADED | Orchestrator says "Plan this out" to generate | ✅ Covered |
| Plan references stale line numbers | High | WASTED | 13-item checklist §1 (anchor points) | ⚠️ Manual — no script verification |
| Plan contains contradictory sections | Low | WASTED | Redundant change detection (§8) catches some | ❌ No contradiction detector |

**Gap to fix:** No automated anchor-point verification. Could add a pre-hardening script that greps plan line numbers against HEAD.

---

## 2. HARDEN ↔ REVISE (iterative loop)

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Infinite revision loop | Low | WASTED | User must say "optimize" to exit | ✅ User-gated |
| Revisions introduce contradictions | Medium | WASTED | Redundant change detection | ❌ No contradiction detection between sections |
| Hardening identifies a risk but no mitigation written | Medium | BLOCKING | Sad-path contingencies template in planning skill | ⚠️ Manual — template can be skipped |
| User hardens but doesn't optimize before executing | Medium | BLOCKING | Optimize is mandatory gate (agent-prompt blocks required) | ⚠️ Manual — orchestrator must remember ordering |

**Gap to fix:** Add contradiction detection to 13-item checklist: "If section B modifies a file section A creates, verify the dependency is stated and the order is correct."

---

## 3. REVISE → OPTIMIZE

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| 13-item checklist partially skipped | Medium | CASCADING | Checklist is in planning skill | ❌ No enforcement — all 13 items are manual |
| Model names not verified (item 11) | Low | BLOCKING | P005 blocks at dispatch | ✅ Structural |
| Iteration budget not estimated (item 12) | High | BLOCKING | P009 warns at dispatch | ⚠️ P009 declared but logic not implemented |
| Monkeypatch paths not checked (item 13) | Low | BLOCKING | Manual grep | ❌ No enforcement |
| User says "optimize" but plan was never hardened | Medium | BLOCKING | Planning stage order rule | ⚠️ Manual — orchestrator must remember order |

**Gap to fix:** Add a pre-optimize gate: run a script that verifies all 13 checklist items were addressed. Or at minimum, count agent-prompt blocks and verify anchor points.

---

## 4. OPTIMIZE → PREFLIGHT

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Preflight fail (missing secrets) | Low | BLOCKING | preflight.sh exit 1 | ✅ Structural |
| Preflight degraded (API down) | Medium | DEGRADED | Operator must acknowledge | ✅ Manual gate |
| Preflight pass but env overrides not propagated to workers | Medium | BLOCKING | Preflight env persistence section in orchestrator | ⚠️ Manual — orchestrator must export vars |
| Skills not provisioned (drift) | Low | DEGRADED | Preflight §0b checks skill provisioning | ✅ Structural |
| Working copy on /mnt/ (WSL DrvFs) | Low | BLOCKING | Preflight §0 blocks cross-mount | ✅ Structural |

**Gap to fix:** None critical. Preflight is the strongest gate in the system.

---

## 5. PREFLIGHT → ATTEST

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Attestation file not generated | Low | BLOCKING | A001 — decomposer refuses | ✅ Structural |
| Attestation stale (>120 min TTL) | Low | BLOCKING | A002 — re-run required | ✅ Structural |
| Attestation tampered | Very Low | BLOCKING | A003 — checksum mismatch | ✅ Structural |
| Attestation degraded (invalid profile) | Medium | DEGRADED | Proceed with acknowledgment | ⚠️ Manual — operator must approve |
| Preflight result not passed to attestation script | Low | BLOCKING | Script requires --preflight-result | ✅ Structural |

**Gap to fix:** None. Attestation is well-gated.

---

## 6. ATTEST → DECOMPOSE (card creation)

This is where most of our Phase 2 failures occurred. Each sad path now has a structural gate.

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Root with --triage → auto-decompose | Medium | WASTED | Pitfall + orchestrator Step 2 rule | ⚠️ Manual |
| Dependent cards created ready | High | CASCADING | Gate pattern mandate (create blocked→link→unblock) | ⚠️ Manual |
| --parents flag used (silently ignored) | Medium | BLOCKING | P008 (card body policy) | ❌ P008 declared but NOT IMPLEMENTED |
| Workspace hardcoded to main repo | High | CATASTROPHIC | validate_board.sh §3 (shared workspace check) | ✅ Structural via board keeper |
| Scratch workspace | Medium | BLOCKING | validate_board.sh §2 (scratch check) + P006 | ✅ Structural |
| Cards too large (>35 turns) | High | BLOCKING | Planning §12 + board keeper §6 (heuristic) | ⚠️ Heuristic only (function count) |
| Model in card body | Medium | BLOCKING | P005 (card body policy) | ✅ Structural (implemented) |
| No max-retries set | High | WASTED | Orchestrator pitfall "MANDATORY default" | ⚠️ Manual — no enforcement |
| Card body missing required fields | Low | BLOCKING | P001-P004 (card body policy) | ✅ Structural |
| Assignee profile doesn't exist | Low | BLOCKING | Preflight §5 (profile availability) | ✅ Structural |

**Gap to fix:** P008 needs implementation in kanban_card_policy.py to detect --parents usage. Max-retries needs enforcement.

---

## 7. DECOMPOSE → EXECUTE (dispatch + worker lifecycle)

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Gateway not running | Low | BLOCKING | Preflight §4 (gateway health) | ✅ Structural |
| Dispatcher stuck (ready cards not claimed) | Medium | BLOCKING | board_keeper.sh §3 (stuck detection + gateway restart) | ✅ Structural via board keeper |
| Provider rate-limited (429) | Medium | DEGRADED | Same-provider staggering via parent-child links | ⚠️ Reduces but doesn't eliminate |
| Agent auth failure | Low | BLOCKING | Preflight §5c (`coding_agent_cli_reachability` via `check_coding_agent_cli.py`) | ✅ Structural |
| Agent OOM / segfault crash | Low | BLOCKING | Dispatcher retries; board keeper detects blocked | ⚠️ No prevention, only detection |
| Agent produces zero output | Medium | BLOCKING | Evaluation chain E006 (zero-output check) | ✅ Structural |
| Worktree creation fails (disk full) | Low | BLOCKING | Preflight E007 (disk space) | ✅ Structural |
| Agent runs in wrong directory | Low | BLOCKING | Workspace path validated by board keeper | ✅ Structural |
| Old agents survive card archive | High | WASTED | board_keeper.sh §1 (orphan detection + kill) | ✅ Structural via board keeper |
| Heartbeat forgotten → 15-min reclaim | Medium | DEGRADED | Worker skill mandates heartbeat | ⚠️ Manual — worker must implement |

**Gap to fix:** Agent OOM prevention — could add memory budget per card. Provider rate-limiting — could add dispatch staggering.

---

## 8. EXECUTE → VERIFY (evaluation chain)

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Evaluation chain script missing | Low | BLOCKING | E013 — block immediately | ✅ Structural |
| File not in diff (E001) | Medium | BLOCKING | Chain stops at first DENY | ✅ Structural |
| Unlisted file changes (E002) | Medium | WARNING | Auto-revert | ✅ Structural |
| Test failure (E003) | Medium | BLOCKING | Chain stops | ✅ Structural |
| Commit message mismatch (E004) | Low | BLOCKING | Chain stops | ✅ Structural |
| Token log missing (E005) | Medium | WARNING | Chain flags, doesn't block | ⚠️ Warning only — tokens lost |
| Zero output (E006) | Medium | BLOCKING | Chain stops | ✅ Structural |
| Worker calls kanban_complete directly | Low | PROTOCOL | Governance model "structurally prevents" | ⚠️ Claimed structural but depends on worker compliance |
| Worker forgets kanban_complete | Medium | BLOCKING | Dispatcher reclaim after timeout | ⚠️ Timeout-based, not prevention |

**Gap to fix:** Token log E005 is warning-only — should block in strict mode. Direct kanban_complete prevention is claimed structural but actually depends on worker following the skill.

---

## 9. VERIFY → AUDIT

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Some cards done, others blocked → audit can't start | High | DELAY | Orchestrator monitors board for completion | ⚠️ board_keeper.sh detects blocked but doesn't fix non-iteration-limit blocks |
| Done cards have unmerged worktree branches | High | DELAY | Salvage SOP in orchestrator | ⚠️ Manual — orchestrator must check each worktree |
| Merge conflicts between completed cards | Medium | BLOCKING | Final audit checks merge conflicts | ⚠️ Manual — audit card must resolve |
| Card completed but branch deleted | Low | BLOCKING | Can't merge → work lost | ❌ No prevention or detection |
| Card pushed to wrong branch (trigger_branch when set) | Low | BLOCKING | E009 when trigger_branch configured + pre-push hook from worktree_setup.sh | ✅ Infrastructure enforced |

**Gap to fix:** Automated merge of completed worktrees. Board keeper could do this for done cards with unmerged branches. Branch deletion detection.

---

## 10. AUDIT → RECONCILE

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Audit finds missing work (zero-diff) | Medium | BLOCKING | Re-plan and re-execute | ⚠️ Manual recovery |
| Audit finds broken tests | Medium | BLOCKING | Fix tests or revert | ⚠️ Manual recovery |
| Token logs missing → KPIs incomplete | Medium | DEGRADED | Estimate from agent logs | ⚠️ Fallback is manual |
| No token_tracker.py configured | High | DEGRADED | Our run had none | ❌ No default configuration |

**Gap to fix:** Bundle token_tracker.py with kanban-advanced and configure by default. Add a preflight check for token log path.

---

## 11. RECONCILE → POSTMORTEM

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Postmortem generator script fails | Low | DEGRADED | Manual postmortem | ⚠️ No automated fallback |
| Postmortem written but not committed | Medium | DEGRADED | Lost on next cleanup | ❌ No enforcement |

---

## 12. POSTMORTEM → CLEANUP

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Cron jobs not removed | Medium | WASTED | kanban-advanced:kanban-cleanup §2 | ⚠️ Manual — cleanup checklist |
| Worktree branches accumulate | High | DISK | kanban-advanced:kanban-cleanup doesn't clean worktrees | ❌ No worktree cleanup step |
| Board archived but DB orphaned | Low | CORRUPTION | No specific check | ❌ No post-cleanup verification |
| Staged changes not committed | Medium | DRIFT | kanban-advanced:kanban-cleanup §5 (stage non-kanban changes) | ⚠️ Manual |

**Gap to fix:** Add worktree cleanup to kanban-advanced:kanban-cleanup. Add cron removal verification.

---

## Cross-Cutting Sad Paths

| Sad path | Likelihood | Impact | Governance | Gap? |
|---|---|---|---|---|
| Terminal session ends → tmux watch dies | Medium | BLIND | Cron as fallback | ✅ board_keeper.sh covers this |
| WSL DrvFS corruption on /mnt/ | Low | CATASTROPHIC | Preflight §0 blocks cross-mount | ✅ Structural |
| /tmp fills with stale worktrees | High | DISK | kanban-advanced:kanban-cleanup doesn't address this | ❌ No governance |
| Concurrent plans on same board | Low | COLLISION | dispatcher_owner field (#32228) not yet available | ❌ Upstream bug |
| Plan file lost/deleted | Low | BLOCKING | Plan sits in .agent/plans/ — gitignored? | ⚠️ No backup mechanism |
| Gateway restart during execution → DB corruption | Medium | CATASTROPHIC | Known issues #30908 workaround | ❌ Only mitigation, no prevention |
| Provider extended outage | Low | CATASTROPHIC | Provider fallback chain | ⚠️ Only works if fallback_providers configured |
| Cursor CLI version mismatch | Low | BLOCKING | Agent binary verified in preflight | ⚠️ Version check, not compatibility check |
| Board keeper cron itself fails | Medium | BLIND | No monitoring of the monitor | ❌ No meta-monitoring |

---

## Gap Summary — Prioritized

### Critical (add structural gates):

1. **P008/P009 not implemented** — Declared in policy YAML but no script logic. P008 needs to detect --parents usage. P009 needs turn estimation from card body.
2. **No meta-monitoring** — If board_keeper.sh cron fails silently, nobody knows. Add a watchdog cron that checks the board keeper is running.
3. **Worktree accumulation** — /tmp fills with stale worktrees. Add cleanup to kanban-advanced:kanban-cleanup or board keeper.
4. **Token tracking not default** — token_tracker.py not configured by default. Bundle it and add preflight check.

### Important (add detection or documentation):

5. **Max-retries not enforced** — Orchestrator must remember `--max-retries 2`. Add to validate_board.sh.
6. **No automated worktree merge** — Done cards with unmerged branches need manual salvage. Board keeper could detect and merge.
7. **Branch deletion detection** — If a completed card's branch was deleted, work is lost. Add to final audit.
8. **Plan file backup** — No backup mechanism if plan file is lost.
9. **Contradiction detection** — Between plan sections that modify the same file.

### Nice-to-have (document or defer):

10. **Agent OOM prevention** — Memory budget per card
11. **Provider rate-limit staggering** — Dispatch staggering
12. **Cursor CLI compatibility check** — Version verification
13. **Concurrent plan isolation** — Upstream #32228
14. **Postmortem commit enforcement** — Auto-commit postmortem

---

## Post-audit navigation (2026-06)

Gaps closed or routed by the in-flight governance navigation plan:

- **Sad-path SSOT:** `plugin/skills/kanban-advanced/references/in-flight-governance-index.md` + `wiki/in-flight-navigation.md`
- **Handoff / worktree / delegation incidents:** index rows + `handoff-regression-checklist.md`
- **Worker SOUL vs skill:** `worktree_setup.sh` + E021 in seeded `worker.md`
- **Remaining audit items** (P008/P009 script logic, meta-monitoring, etc.) — still engineering backlog; index points to T2/T3 recovery where documented
