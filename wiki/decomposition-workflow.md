# Decomposition workflow

> **For the agent:** When a user asks *"why block on create?"*, *"why not use `--triage`?"*, *"what does the gate card do?"*, or *"why is `auto_decompose` false?"*, answer from this page. Upstream bug details live in `plugin/data/references/vanilla-kanban-known-issues.md`.

kanban-advanced does **manual decomposition** — cards are created from an already-optimized plan (`kanban_decompose.py` or orchestrator standard process). Vanilla Hermes `hermes kanban decompose` and `kanban.auto_decompose` are **disabled** because they rewrite card bodies through an LLM after the plan is finalized.

## Vanilla Hermes status model (v0.16.x — minimum supported)

From the upstream Kanban RFC ([#16102](https://github.com/NousResearch/hermes-agent/issues/16102)) and [kanban docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban):

```
todo → ready → running → done
         ↑
      blocked / archived (side branches)
```

| Transition | Who does it |
|------------|-------------|
| `todo → ready` | Dispatcher — **only when all parents are `done`** |
| `ready → running` | Dispatcher — atomic claim (typically **<1 second** after a card becomes `ready`) |
| `ready → blocked` | `hermes kanban block` — **only works on `ready` cards** (v0.15.0+) |
| `blocked → ready` | `hermes kanban unblock` or `auto_unblock.sh` when parents are `done` |
| `triage → …` | Dispatcher + `kanban_decomposer` aux LLM — **only when `kanban.auto_decompose=true`** |

**Implication:** A card created without blocking sits in `ready` and can be claimed before you finish linking parents. Parent links added afterward do not stop an already-running worker.

## Why block-on-create (not `--triage`, not `--initial-status blocked`)

| Approach | Problem |
|----------|---------|
| Create as `ready`, link later | Dispatcher claims in <1s — dependency gating bypassed ([#16102](https://github.com/NousResearch/hermes-agent/issues/16102) atomic claim) |
| `--triage` on dependent cards | With `auto_decompose=false`, nothing promotes triage → ready; cards stuck permanently ([[troubleshooting#triage-cards-permanently-stuck]]) |
| `--triage` on root | Dispatcher may auto-decompose into stub children that duplicate manually-created cards |
| `--initial-status blocked` | Observed race: card can auto-promote to `ready` before block takes effect — use a separate `hermes kanban block` call immediately after create |
| `hermes kanban create --parents` | Flag silently ignored — must use `hermes kanban link` after creation (see `vanilla-kanban-known-issues.md`) |

**Supported pattern:** `hermes kanban create` (lands `ready`) → **`hermes kanban block` immediately** (same turn, before stagger sleep) → link parents → mechanical unblock via cron.

`kanban_decompose.py` implements this with `block_after=True` on gate, implementation, and audit cards.

## Why `kanban.auto_decompose=false`

Hermes v0.15.0 defaults `kanban.auto_decompose: true`. When enabled, the dispatcher runs the `kanban_decomposer` aux model on every **triage** task, producing stub children that conflict with cards you already created from the optimized plan.

kanban-advanced init sets:

```bash
hermes config set kanban.auto_decompose false
```

Without this, triage cards may be LLM-rewritten even when you intended manual decomposition only. See [[configuration#hermes-v015x-kanban-config-keys]] and [umbrella #35986](https://github.com/NousResearch/hermes-agent/issues/35986) Gap 3 (orphaned triage cards).

## Standard decomposition sequence

```
0.  VERIFY DB integrity         PRAGMA integrity_check → 'ok'
1.  CREATE root card            create root, do not block (completed immediately)
2.  CREATE gate → block         create gate, block immediately (<1s race window)
3.  CREATE wave crons           bash scripts/provision_kanban_crons.sh --create --plan-id <id>
4.  (kanban_decompose Step 6 also calls --create if orchestrator skipped Steps 3–5)
5.  VERIFY wave crons            bash scripts/provision_kanban_crons.sh --check — gateway must run; deliver=local
6.  CREATE impl cards (stagger) create each card, block immediately; ≥1s stagger, 3s pause / 5 cards
                                 pass --gate-id to kanban_decompose.py to avoid duplicate gate
7.  CREATE audit card           create + block (gates on all impl)
8.  COMPLETE root               hermes kanban complete <root_id> (placeholder only)
9.  LINK dependencies           gate → all impl; wave_parent; ordinal_parent; impl → audit
10. RUN validate_board.sh       full governance gate — fail closed
11. COMPLETE gate (orchestrator) validate passes → hermes kanban complete <gate_id>
```

`kanban_decompose.py` implements steps 6–9 (pass `--gate-id` to skip re-creating the gate). Crons (steps 3–5) are **orchestrator-created before card creation** per `kanban-orchestrator` SKILL. Step 11 is **orchestrator-only** — not a human checkpoint.

Manual orchestration may create root before gate (SKILL step order); both paths must **complete root** and use **block-on-create** for gate, impl, and audit.

## Board-mediated handoff (executing from a non-orchestrator profile)

Decomposition is **orchestrator-only** (the dispatcher matches a card's `assignee` to a
profile name). When a non-orchestrator profile is told to *"execute the plan"*, the
preferred path is **not** asking the user to switch sessions — it is creating one
handoff card the dispatcher runs under the orchestrator profile:

```bash
python3 scripts/kanban_handoff.py --plan <plan.md>
```

The handoff card is deliberately hardened:

| Property | Value | Why |
|----------|-------|-----|
| Title | `Decompose: <plan_id>` | Deterministic — idempotency scan key |
| Marker | `Type: orchestrator-handoff` | Governance carve-out + dispatched-decompose detection |
| `assignee` | orchestrator profile | Dispatcher spawns an orchestrator-profile agent |
| Status | `ready`, no parents | Dispatches immediately (wave 0) |
| Body | plan path + repo + branch + orchestrator SOP | Self-contained instructions |
| Agent block | **none** | A coding `agent -p` block would make Hermes LLM-decompose the card into stub children (the reason `auto_decompose=false` is also required) |

Handoff body metadata (stamped by `kanban_handoff.py`):

| Field | Purpose |
|-------|---------|
| `BUNDLE_ROOT` | Absolute plugin checkout — runbook commands use `{BUNDLE_ROOT}/scripts/…` |
| `gate_script` | Resolved `pre_dispatch_gate.sh` path (forensics for double-`lib/` incidents) |
| `pre_dispatch_gate` | Gate result at creation — orchestrator skips re-run when `PASSED` |
| `cards_yaml` | Structured decompose input when optimize/harden wrote `.hermes/kanban/memory/<plan_id>.yaml` (or plan-adjacent YAML) |

Cards YAML convention: optimize/harden may write `{plan_memory_path}/{plan_id}.yaml` (default `.hermes/kanban/memory/`). Handoff discovers plan-adjacent YAML first, then plan memory.

The builder is **idempotent** (one open `todo/ready/running/blocked` handoff per
`plan_id`, plus a Hermes `--idempotency-key`) and checks its own preconditions before
creating anything: orchestrator profile exists, `kanban.dispatch_in_gateway` is on,
`kanban.auto_decompose` is off, and the gateway is running. It exits non-zero with a
`fix` hint otherwise (use `--allow-offline` to create the card regardless). A manual
`hermes -p kanban-advanced-orchestrator chat` session is the **fallback** when the gateway is
unavailable — see `plugin/data/references/profile-switching.md`.

### Handoff sad-path

| Symptom | Index layer | Recovery |
|---------|-------------|----------|
| Builder exit 2–4 | L3 | Follow printed `fix` (init, gateway, dispatcher config) |
| Handoff `ready` 10+ min | L3 | Restart gateway; confirm assignee = orchestrator profile |
| `pre_dispatch_gate: UNKNOWN` on card | L2 | Orchestrator re-runs `bash <BUNDLE_ROOT>/scripts/pre_dispatch_gate.sh <plan_id>` |
| `pre_dispatch_gate: PASSED` on card | L2 | Skip gate — proceed to runbook Step 2 |

See `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")` § L3.

The `Type: orchestrator-handoff` marker is whitelisted in `kanban_card_policy.py` so
the SOP-only body is exempt from the worker code-gen rules (P001/P002/P003), exactly
like gate/root/audit control cards.

### Gate card (orchestrator control — not human)

The gate is a **dependency root**, not an approval step for the operator.

- All implementation cards link to the gate as a parent.
- Gate starts **blocked** so nothing dispatches during card creation and linking.
- After `validate_board.sh` passes, the **orchestrator** runs `hermes kanban complete <gate_id>`.
- Completing the gate marks it `done`. `auto_unblock.sh` then unblocks wave-1 children whose parents are all `done`.
- Workers never interact with the gate card.

Do **not** leave the gate blocked and expect wave 1 to start — **complete** it after validation. Do **not** use `hermes kanban unblock` on the gate as the release mechanism; completion is the signal.

### Wave progression (mechanical — not orchestrator polling)

LLM orchestrators cannot poll the board between turns. `auto_unblock.sh` (cron every 1m) unblocks each blocked card when **all** its parents are `done`:

```
gate done → wave-1 cards unblock → dispatcher claims → workers run
card N done → ordinal/wave children unblock on next cron tick
all impl done → audit unblocks → orchestrator runs audit checklist
```

See [[governance#auto-progression-mechanical-wave-unblocking]].

## What we deliberately do NOT use

| Vanilla feature | Why kanban-advanced avoids it |
|-----------------|------------------------------|
| `hermes kanban decompose <root_id>` | LLM rewrites optimized card bodies |
| `hermes kanban create --triage` (dependent cards) | Stuck when `auto_decompose=false` |
| `hermes kanban create --parents` | Silently ignored |
| `hermes kanban create --initial-status blocked` | Race auto-promote; use block call instead |
| Operator unblocks gate | Gate is orchestrator-managed; operator says "execute the plan" once |

## FAQ (agent answers)

**Q: Why can't we create cards in `todo` and let the dispatcher promote them?**  
A: `hermes kanban create` does not offer a reliable `todo` initial status for governed plans. Default create lands `ready`. `hermes kanban block` only works on `ready` (v0.15.0+). The supported path is create → block on `ready`.

**Q: Why not `--triage` to park cards safely during linking?**  
A: Triage exit requires the dispatcher + decomposer (`auto_decompose=true`). We disable auto-decompose to protect optimized bodies. Triage cards with `auto_decompose=false` stay stuck — see [[troubleshooting#triage-cards-permanently-stuck]].

**Q: Who unblocks wave 2, wave 3, …?**  
A: `auto_unblock.sh` — not the orchestrator manually. Each card unblocks when all parents are `done`.

**Q: Why complete the gate instead of unblocking it?**  
A: `auto_unblock` requires parents in `done` status. Completing the gate satisfies that for all gate-linked children. Unblocking without completing leaves parents not-`done` and children stay blocked.

**Q: Does parent gating work natively?**  
A: Partially. Dispatcher promotes `todo→ready` only when parents are `done` ([#16102](https://github.com/NousResearch/hermes-agent/issues/16102)). But cards created as `ready` dispatch before links exist. Block-on-create + cron unblock is our structural workaround until upstream closes the claim race. See also [#24489](https://github.com/NousResearch/hermes-agent/issues/24489) (running parent blocks children — different symptom, same dependency surface).

## Related pages

- Known upstream bugs: `plugin/data/references/vanilla-kanban-known-issues.md`
- Governance gates: [[governance]]
- Config keys: [[configuration]]
- Failure symptoms: [[troubleshooting]]
- Upstream links: [[external-references]]
