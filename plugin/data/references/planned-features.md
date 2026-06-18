# Planned features — deferred until upstream or full implementation

> **Purpose:** Track kanban-advanced capabilities that are **designed but not fully shippable** on today's Hermes Agent build. Sibling to [`vanilla-kanban-known-issues.md`](vanilla-kanban-known-issues.md): known-issues documents **bugs + workarounds**; this document documents **intended features blocked or partial** until Hermes ships APIs/behavior or the plugin finishes non-upstream work.

**Hermes floor:** kanban-advanced targets **Hermes Agent ≥ 0.16.0** (see `wiki/setup.md`).

## How to use

| Audience | Action |
| --- | --- |
| **Operator** | Before expecting automation, check whether the feature is **Workable today** or **Blocked on upstream**. |
| **Orchestrator / agent** | Do not promise walk-away or governance behavior that depends on a row marked **Blocked** without citing the workaround column. |
| **Plugin maintainer** | When upstream closes an issue, update this doc and trim the row. |

**Cross-refs:** Umbrella reliability gaps — [#35986](https://github.com/NousResearch/hermes-agent/issues/35986). Live bug workarounds — `vanilla-kanban-known-issues.md`. Operator hardening tracker — maintain deferred rows here (not in shipping plan paths).

---

## Blocked on Hermes Agent upstream

These need **new or fixed Hermes kanban / CLI / hook behavior**. Plugin scripts can only partially simulate them (skills, manual calls, crons).

| Feature | Full intent | Why upstream | Partial today | Upstream ask |
| --- | --- | --- | --- | --- |
| **Pre-complete governance hook** | `hermes kanban complete` runs verify-deploy attestation, eval chain, and intervention log before terminal transition | No first-class `pre_complete` hook on kanban state machine | `kanban_pre_complete_gate.py` + eval chain when worker/orchestrator **voluntarily** runs it; `board_keeper` salvage may bypass | Kanban lifecycle hook or wrapper command that invokes plugin gate scripts |
| **CLI intervention auto-log** | Every `kanban unblock`, `kanban complete`, and body edit increments `interventions.jsonl` + counter | Hermes CLI does not emit extension events | Manual `kanban_intervention_inc.sh` per skill SOP (`intervention-jsonl-cli` todo) | Post-mutation hook or `--reason` flag wired to operator plugins |
| **Working `--parents` on create** | Atomic parent link at create time | Flag silently ignored ([#24489](https://github.com/NousResearch/hermes-agent/issues/24489) surface) | `kanban link` after block-on-create; P008 policy | Fix or remove `--parents`; document atomic create+link |
| **Archived cards in `kanban list`** | Live board + archived plan cards for operator triage | Archived hidden from default list | Postmortem + reconciliation read `kanban.db`; `hermes kanban show <id>` per archived id | `kanban list --include-archived` or plan-scoped list API |
| **Blocked reason always visible** | Operator sees **why** a card is blocked without `kanban show` | [#30213](https://github.com/NousResearch/hermes-agent/issues/30213); [#35986](https://github.com/NousResearch/hermes-agent/issues/35986) Gap 2 | `hermes kanban show`; `board_keeper` warnings | Surface `block_reason` on `kanban list` / gateway notify |
| **Safe archive semantics** | Archive parent without promoting children | [#30417](https://github.com/NousResearch/hermes-agent/issues/30417) Bug 3 | Never archive parents until children done | Archive must not treat archived parent as `done` for promotion |
| **Atomic create + block + link** | Single transaction: no dispatcher claim race | [#16102](https://github.com/NousResearch/hermes-agent/issues/16102) claim race | block-on-create + stagger + crons | Optional `create --blocked` that is race-safe, or create in `todo` with working block |
| **Native token usage on task** | Kanban task row stores agent token usage from dispatch | Usage only in agent JSON stdout today | `log_invoke_tokens.py`, worker `log_token_run`, E018 | Attach usage metadata to task on worker completion |
| **Cron reconcile API** | Dashboard toggle change updates Hermes cron jobs without handoff re-run | Cron CRUD is CLI/script-level; dashboard Save does not reconcile jobs | Handoff `provision_kanban_crons --create/--check`; manual re-provision | Gateway or `hermes cron` API for idempotent reconcile from overlay hash |
| **Subagent supervision telemetry** | Parallel gate subagents report structured pass/fail into kanban task | [#35986](https://github.com/NousResearch/hermes-agent/issues/35986) Gap 5 | `pre_dispatch_gate.sh` serial fallback; parallel gate prompts | Delegation tool returns machine-readable gate results on task |
| **`dispatch_stale_timeout` reliable default** | Stale `running` reclaimed per docs without bootstrap | [#35986](https://github.com/NousResearch/hermes-agent/issues/35986) Gap 7; upstream default often `0` | Init sets `14400`; `dispatch-stale-timeout.md` | Non-zero safe default in upstream; config introspection |
| **Goal-mode + kanban_complete integration** | Goal cards complete with acceptance attestation | Goal loop blocks for review when turns exhausted (by design) | One-shot cards preferred; `goal_card_selection.md` | Clearer kanban_complete from goal loop when Acceptance met |

---

## Plugin-only deferred (no upstream required)

Shipped in v7 plugin-only pass (2026-06-18). Remaining rows are upstream-blocked only.

| Feature | Plan todo | Status |
| --- | --- | --- |
| **Deploy stub card pattern** | `deploy-stub-card-pattern` | Shipped — `plan-file-format.md` + planning skill |
| **Orchestrator token checkpoints** | `orchestrator-token-checkpoints` | Shipped — decompose, gate, final audit |
| **Skill preservation on Update Plugin** | `skill-preservation-update` | Shipped — `script_materialize` manifest |
| **Dashboard cron reconcile** | `dashboard-toggle-cron-reconcile` | Shipped — Save + status API |
| **Worktree branch durability** | `worktree-branch-durability` | Shipped — optional push + `kanban_recover --salvage-branch` |
| **Eval chain stat width** | `eval-chain-stat-width` | Shipped — `git diff --stat=200` |
| **Coding-agent invoke parity** | `coding-agent-binary-flags` | Shipped — doc + `test_coding_agent_parity.py` |
| **Docs v7 final shipping pass** | `docs-v7-final-shipping-pass` | Shipped — README, API, references |

---

## Hybrid — shipped with manual/discipline gap

Feature works on current Hermes **if** operators follow SOP. Upstream or plugin polish would make it automatic.

| Feature | Shipped artifact | Gap | Workable today |
| --- | --- | --- | --- |
| **verify-deploy attestation** | `kanban_card_attestation.py`, eval chain, tier1 | `hermes kanban complete` does not auto-call pre-complete gate | Yes — orchestrator runs attestation writer + gate before complete |
| **Cycle detect** | `cycle_detector.py`, pre_dispatch_gate | Board scrape via `kanban list` + `show`; not in gateway UI | Yes — gate blocks on balanced/strict |
| **validate_card_bodies** | WARN dry-run / BLOCK gate | Does not auto-fix plan; operator edits plan | Yes |
| **Cron Option A** | `kanban_handoff.py` provisions; dashboard Save reconciles on toggle | No cron API when lifecycle off mid-plan | Yes — handoff or Save with active `lifecycle_plan_id` |
| **Postmortem archived KPIs** | DB-sourced metrics | `kanban list` omits archived — reconcile §2b documents | Yes — run postmortem before archive |
| **Intervention JSONL** | `kanban_intervention_inc.sh` | Not wired to Hermes CLI mutations | Yes — manual per notify skill |

---

## Workable today on current Hermes (≥ 0.16.0)

Full operator lifecycle **without waiting on upstream**:

1. **Plan → Harden → Optimize** — planning skills, anchors, canonical `.hermes/kanban/plans/`
2. **Execute via handoff** — `kanban_handoff.py` (cron provision + overlay stamp)
3. **Orchestrator decompose** — `kanban_decompose.py --no-crons`, `--archive-prior`, `--dry-run` + `validate_card_bodies`
4. **Pre-dispatch gate** — attestation, card bodies, cycle detect, coding-agent smoke
5. **Block-on-create + gate + crons** — `auto_unblock`, `board_keeper`, walk-away post-exec
6. **Worker governance** — eval chain (P014, impl-before-test, verify-deploy), token log, E-codes
7. **Final audit + postmortem + reconciliation** — tier1/tier2, KPI `data_confidence`, archived terminal
8. **All v7 P0 logistics gates** — Tests sanitize, Files normalize, plan_hardening_diff, cycle_detector

**Use workarounds from** `vanilla-kanban-known-issues.md` for: `--parents`, archive parents, triage+auto_decompose, profile-scoped `HERMES_HOME`, OAuth stagger.

---

## Suggested upstream filing map

When opening Hermes issues for rows above, reference [#35986](https://github.com/NousResearch/hermes-agent/issues/35986) where applicable:

| Plugin planned feature | Suggested upstream theme |
| --- | --- |
| Pre-complete hook | Kanban lifecycle hooks / plugin extension points |
| CLI intervention log | CLI mutation events |
| `--parents` / atomic link | Kanban create API |
| Archived list | Kanban query API |
| Blocked reason on list | Dispatcher observability |
| Cron reconcile | Gateway cron management API |
| Task token metadata | Worker completion payload |

---

## Version tracking

| Date | Change |
| --- | --- |
| 2026-06-18 | Initial document — v7 deferred items + upstream dependency matrix |
