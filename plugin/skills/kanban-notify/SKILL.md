---
name: kanban-notify
description: Gateway push notifications for intervention-required kanban events during walk-away execution.
version: 1.0.0
metadata:
  hermes:
    tags: [kanban, notify, gateway, walk-away, intervention]
    related_skills: [kanban-advanced:kanban-orchestrator, kanban-advanced:kanban-preflight, kanban-advanced:kanban-cleanup, kanban-advanced:kanban-postmortem]
---

# Kanban Notify — Intervention Gateway Push

> **Skill precedence (mandatory):** When this skill and any project-specific skill (e.g., `host-project-dev-environment`) provide conflicting information about profiles, assignees, workspace paths, or dispatch rules, **this skill wins**. Kanban governance rules override project conventions. Specifically:
> - Profile names (`worker`, `orchestrator`) come from `hermes profile list` and `kanban-config.yaml`, NOT from project skill examples or artifact tables.
> - Workspace paths and branch naming come from this skill's decomposition rules, not from project-specific CLI examples.
> - Card body format (`Files:`, `Mode:`, `agent -p` blocks) is enforced by card body policy (P001–P009), not by project documentation.
>
> If you detect a conflict between this skill and a project skill, apply this skill's rule and note the conflict in a `kanban_comment` on the affected card.

Walk-away mode runs the board unattended. **Notify the operator only when human judgment is required** — not for routine progress, heartbeats, or recoverable transient failures.

The orchestrator loads this skill during walk-away setup, confirms delivery prerequisites, and uses the trigger table below when triaging `blocked`, `gave_up`, `crashed`, or `timed_out` events.

## When to notify

| Trigger | When | Auto-retry first? | Example |
| --- | --- | --- | --- |
| `blocked_after_retry` | Task blocked and one auto-retry (per plan sad-path) did not resolve | Yes — once | Worker blocked on lint failure after retry |
| `repeated_crash_timeout` | Same task `crashed` or `timed_out` **2+ times** | Yes — once | Agent OOM twice on the same card |
| `missing_profile` | Card assignee not in `hermes profile list` | No | `${worker_profile}` profile deleted mid-run |
| `auth_failure` | Agent auth invalid (`agent status` not logged in) affecting workers | No | Session expired during walk-away |
| `file_constraint_violation` | Worker changed files outside the card `Files:` line after self-audit | No | Extra paths in `git diff --stat` |
| `memory_budget` | Host RAM below blocking threshold mid-run (`PREFLIGHT_MEMORY_MIN_MB`) | No | MemAvailable drops under 1024 MB |
| `manual_judgment` | Plan sad-path marks the risk **non-retryable** (API key, legal approval, external dependency) | No | Stripe webhook secret missing in prod |
| `ci_red_after_push` | Final audit pushed but CI/deploy gate stays red after orchestrator retry window | No | Cloud Build failure needs operator decision |

**Flow (orchestrator):**

1. **Pause** — `hermes kanban block <task_id>` with a clear reason if not already blocked.
2. **Auto-retry** — when the trigger row allows it and the plan sad-path table marks the risk retryable, unblock once and let the dispatcher retry.
3. **Notify** — if retry fails or the trigger is non-retryable, send gateway notification (format below).
4. **Resume silently** — if retry succeeds, continue monitoring **without** notifying.

Increment the intervention counter once per orchestrator intervention:

```bash
bash ${bundle_path}/scripts/kanban_intervention_inc.sh
```

## Do not notify (non-intervention list)

These events are **silent** during walk-away unless the operator opted into completion notify (`NOTIFY_ON_COMPLETE=true`):

1. **Routine task completions** — worker `kanban_complete` and next-card promotion.
2. **Single reclaim cycles** — first dispatcher reclaim (~15 min idle); orchestrator heartbeats and retries internally.
3. **Expected worker heartbeats** — periodic `kanban_heartbeat` notes during agent execution.
4. **Gate completion / dependency promotion** — orchestrator completes gate card after validate; auto_unblock releases children.
5. **Worker progress notes** — orchestrator chat summaries while the operator is still present (walk-away cron logs only).
6. **Final-audit ready** — audit card reaches `ready` (default off; see completion opt-in below).
7. **Successful auto-retry** — transient block/crash/timeout resolved without operator action.

## Notification format

Send a **single concise message** per intervention. Include every field so the operator can act from the phone without opening the repo.

### Required fields

| Field | Source |
| --- | --- |
| `plan_id` | Card body first line or `HERMES_KANBAN_PLAN_ID` |
| `task_id` | Hermes task id (e.g. `t_a1b2c3d4`) |
| `task_title` | `hermes kanban show <task_id>` title |
| `failure_class` | Trigger id from the table above |
| `suggested_action` | One imperative sentence (login, restore profile, approve deploy, etc.) |
| `board_state` | Done / active / blocked counts from `hermes kanban list` |

### Message template

```text
🚨 Kanban intervention — {failure_class}

Plan: {plan_id}
Task: {task_id} — {task_title}
State: {done} done · {active} active · {blocked} blocked

{one-line diagnosis from kanban_show / worker log}

Suggested action: {suggested_action}

Reply when resolved; orchestrator will unblock and resume.
```

### Example

```text
🚨 Kanban intervention — auth_failure

Plan: kanban-walkaway-hardening
Task: t_8f2a1c09 — wire preflight into orchestrator
State: 12 done · 1 active · 1 blocked

Agent status: not logged in (agent status → "Not logged in")

Suggested action: Run `agent login` on the worker host, then reply "resume".

Reply when resolved; orchestrator will unblock and resume.
```

### Persistence (postmortem input)

Append one JSON line per notify (create directory if missing):

```bash
LOGDIR="${KANBAN_NOTIFY_LOG_DIR:-$HOME/.hermes/kanban/logs}"
mkdir -p "$LOGDIR"
# Append after sending gateway message:
# {"timestamp":"...","plan_id":"...","task_id":"...","failure_class":"...","message":"..."} >> "$LOGDIR/interventions.jsonl"
```

Dedupe: do **not** re-send the same `task_id` + `failure_class` within **30 minutes** unless the failure worsens (e.g. retry count increases).

## Gateway delivery setup

Push delivery requires the Hermes **gateway** with a configured chat platform (Telegram, Discord, etc.). CLI-only setups cannot receive push — use `hermes kanban watch` in tmux instead.

**Wave crons are separate:** `auto_unblock.sh` and `board_keeper.sh` use script-only crons (`deliver=local`) and do **not** require messaging. Missing Telegram/Discord does not stop wave progression — only intervention **notify** pages need a chat channel.

### Prerequisites

1. **Gateway running**

```bash
hermes gateway status
# If down:
hermes gateway run   # tmux or background for persistence
```

2. **Preflight pass** — `bash hermes-kanban-advanced-workflow/scripts/preflight.sh` must report `gateway_health` as pass (see `kanban-advanced:kanban-preflight`).

3. **Chat channel configured** — Hermes config maps the operator's chat id for the active platform. Without this, gateway runs but messages have nowhere to go.

### Test delivery before walk-away

```bash
# 1. Confirm gateway (preflight check 4)
hermes gateway status

# 2. Optional: subscribe to final-audit card for instant audit-ready ping
hermes kanban notify-subscribe <audit_task_id> --source cli

# 3. List / remove subscriptions
hermes kanban notify-list
hermes kanban notify-unsubscribe <task_id>
```

Send a **test intervention-shaped message** through the orchestrator's gateway channel (e.g. Hermes `send_message` to the operator chat) before the operator leaves. Confirm receipt on the phone/desktop client.

### Walk-away handoff script (orchestrator says to operator)

Before the operator walks away, state explicitly:

- Gateway status (pass/fail)
- The **8 intervention triggers** that will page them
- The **7 silent events** above
- Whether `NOTIFY_ON_COMPLETE` is set
- Whether **lifecycle notify** is on (`notify_lifecycle: true` default — per-card progress, not intervention)

## Lifecycle notify (separate from intervention)

**Default on** (`notify_lifecycle: true` in `kanban-config.yaml` or dashboard **Profiles → Notifications**). Provisions `kanban-lifecycle-notify-5m` at decomposition via `provision_kanban_crons.sh`.

| Channel | Script | When | Prefix |
|---------|--------|------|--------|
| Intervention | orchestrator + `kanban_intervention_inc.sh` | 8 triggers only (auth exhausted, human gate, …) | 🚨 |
| Lifecycle | `kanban_lifecycle_notify.sh` | Per-card start / running / done + catastrophic re-block **after gate completes** | ℹ️ (no 🚨) |

Lifecycle state-diff logs: `.hermes/kanban/logs/lifecycle.jsonl`. Disable with `notify_lifecycle: false` or dashboard toggle off — wave crons (`auto_unblock`, `board_keeper`) still run.

**Do not** increment `interventions.count` for lifecycle messages. **Do not** use lifecycle notify for evaluation-chain denies — those are worker/orchestrator remediation unless they hit an intervention trigger.

### Completion notification opt-in

Off by default. When set, send a **non-intervention** summary after postmortem generation and board archive:

```bash
export NOTIFY_ON_COMPLETE=true
```

Completion message (no 🚨 prefix):

```text
✅ Kanban plan complete — {plan_id}

{done} tasks done · postmortem: .hermes/kanban/reports/{plan_id}.md
Board archived. Review postmortem when back.
```

Wired in `kanban-advanced:kanban-cleanup` — see that skill for ordering (postmortem before archive).

## Orchestrator integration

- **Active monitoring:** `hermes kanban watch --kinds completed,blocked,gave_up,crashed,timed_out` — triage triggers; notify only after retry exhaustion.
- **Walk-away cron:** 5-minute board poll; same trigger rules; log to `cron-monitor.log` when chat delivery fails (see `${bundle_path}/scripts/kanban_cron_monitor_log_fallback.sh`).
- **Mid-run reconciliation:** When intervention ratio exceeds 30%, orchestrator self-heals first; notify only if checklist cannot resolve without operator input.

Cross-reference: `hermes-kanban-advanced-workflow/prompts/orchestrator.md` § Intervention notifications.

## Pitfalls

- **Notifying on every block.** Most blocks are auto-retryable — pause, retry once, stay silent on success.
- **Gateway up but chat unconfigured.** `gateway status` passes while pushes vanish — always test delivery before walk-away.
- **Duplicate pages.** Use 30-minute dedupe on `task_id` + `failure_class`.
- **Skipping intervention log.** Postmortem § Intervention Log reads `interventions.jsonl` and `interventions.count` — log every notify.
- **Paging for token burn advisories.** >50K token alerts are orchestrator-only investigation; do not gateway-notify unless the task also hits an intervention trigger.
- **CLI-only environments.** Do not promise push; use tmux `kanban watch` and log fallback.
- **Final-audit subscribe vs intervention list.** `notify-subscribe` on the audit card is optional convenience; default walk-away stays silent until `NOTIFY_ON_COMPLETE=true`.
- **Notifying after exhausted code-problem retries.** If all three escalation levels (coding agent → worker → orchestrator) failed to resolve a code or test failure, the correct response is a plan review, not a gateway page. Notify only if the block cause is environmental or requires approval outside the agents' authority (`HUMAN_INTERVENTION` from `board_keeper.sh`).

## When to notify vs stay silent (load in order)

| Situation | Notify? | Load |
| --- | --- | --- |
| Auto-retryable worker block (first failure) | No | Orchestrator triage pipeline |
| `[escalation:coding_agent:auth]` after smoke retry | Yes (intervention) | `coding-agent-auth.md` |
| Final audit **exit 2** / max rounds / `gave_up` remediation | Yes (intervention) | `final-audit-sanity-check.md`; index L7 |
| Final audit exit 1 mid-remediation wave | No (unless stuck > policy) | Orchestrator § Final audit problem router |
| Token burn advisory only | No | Orchestrator investigates |
| Plan complete + postmortem | Optional | `NOTIFY_ON_COMPLETE=true` — `kanban-cleanup` |
| Unknown trigger | No until classified | This skill § Intervention trigger table |

## Cross-references

- Preflight gateway check: `kanban-advanced:kanban-preflight` § Gateway health
- Orchestrator prompt: `hermes-kanban-advanced-workflow/prompts/orchestrator.md`
- Intervention counter: `scripts/kanban_intervention_inc.sh`
- Completion opt-in: `kanban-advanced:kanban-cleanup`
- Postmortem input: `kanban-advanced:kanban-postmortem`, `hermes-kanban-advanced-workflow/scripts/generate_postmortem.py`
