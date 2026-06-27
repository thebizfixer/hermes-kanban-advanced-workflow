# Architecture

## Pipeline stages

```mermaid
flowchart LR
    subgraph PLAN["Planning (interactive)"]
        direction TB
        DRAFT["Draft<br/>'Plan this out'"] --> SANITY["Sanity check<br/>'Do a sanity check'"]
        SANITY --> HARDEN["Harden<br/>'Harden the plan'"]
        HARDEN -->|"Revise section X"| HARDEN
    end

    OPT["Optimize<br/>'Optimize for Kanban'"]

    EXE["Execute<br/>'Execute the plan'"]

    subgraph GATE["Preflight → dispatch"]
        direction TB
        PRE["Preflight"] --> ATT["Attest"] --> DEC["Decompose"]
    end

    subgraph OPS["During execution"]
        direction TB
        MON["Monitor"] --> PAUSE["Pause / Reset"] --> RCV["Recover"] --> VER["Verify<br/>eval chain"]
    end

    subgraph CLOSE["Closeout"]
        direction TB
        AUD["Audit"] --> REC["Reconcile"] --> CLN["Cleanup"]
    end

    PM["Postmortem"]

    PLAN --> OPT --> EXE --> PRE
    DEC --> VER
    VER --> AUD
    CLN --> PM

    MON -.-> DEC
    PAUSE -.-> DEC
    RCV -.-> DEC
```

## Governance layers (pre-execution through verify)

Deterministic gates run from plan hardening through worker verification. **SSOT:** [`wiki/governance.md`](../../wiki/governance.md) § Full pre-execution governance stack (check matrices, blocking vs WARN).

```mermaid
flowchart LR
    VG["Goal cards<br/>verify_goal_cards"] --> PF["Preflight"]
    PF --> ATT["Attest"]
    ATT --> PDG["Pre-dispatch<br/>gate"]
    PDG --> HO["Handoff<br/>optional"]
    HO --> DEC["Decompose<br/>verify crons + validate"]
    DEC --> W0["Worker<br/>E021 + smoke"]
    W0 --> EC["Eval chain<br/>E001–E020"]

    GI["Governance<br/>integrity"] -.-> PDG
```

| Layer | Stage | Script / gate | Blocks? |
| ----- | ----- | ------------- | ------- |
| 0 | After Optimize | `verify_goal_cards.py` | Yes (via attestation) |
| 1 | Pre-decompose | `preflight.sh` → `kanban_attestation.py` | Yes (A001–A003) |
| 2 | Pre-decompose | `pre_dispatch_gate.sh` (+ OAuth pre-warm WARN) | Yes on FAIL |
| 3 | Execute (non-orchestrator) | `kanban_handoff.py` + dispatcher preconditions + `provision_kanban_crons.sh --create` | Yes (exit 2–4, 8) |
| 4 | Decompose | `provision_kanban_crons.sh --check` (`--no-crons` on handoff path), card policy, `validate_board.sh` | Yes |
| 5 | Worker Step 3 | `worktree_setup.sh`, **E021**, coding-agent smoke | Yes |
| 6 | Worker Step 6 | `kanban_evaluation_chain.py` | Yes (DENY) |

**In-flight sad-path:** [`wiki/in-flight-navigation.md`](../../wiki/in-flight-navigation.md) + [`plugin/skills/kanban-advanced/references/in-flight-governance-index.md`](../../plugin/skills/kanban-advanced/references/in-flight-governance-index.md) (Hermes `skill_view`).
| — | Plugin health (optional) | `governance_integrity.sh` | Yes |

Handoff detail (metadata, runbook, Hermes config): [`wiki/decomposition-workflow.md`](../../wiki/decomposition-workflow.md) § Board-mediated handoff.

## Stage reference

| Stage       | Trigger phrase                           | Skill                   | Governance gate                                            |
| ----------- | ---------------------------------------- | ----------------------- | ---------------------------------------------------------- |
| Draft       | `"Plan this out"`                        | `kanban-advanced:kanban-planning`       | —                                                          |
| Sanity check | `"Do a sanity check"`                   | `kanban-advanced:kanban-planning`       | Read-only audit: anchor verification, code cross-ref, gap report |
| Harden      | `"Harden the plan"`                      | `kanban-advanced:kanban-planning`       | Edge cases, contingencies, provider staggering             |
| Revise      | `"Revise section X"`                     | `kanban-advanced:kanban-planning`       | —                                                          |
| Optimize    | `"Optimize for Kanban"`                  | `kanban-advanced:kanban-planning`       | Harden (WHAT) + Optimize (HOW); then `verify_goal_cards.py` |
| Goal cards  | (before attestation)                     | `kanban-advanced:kanban-planning`       | `verify_goal_cards.py` — budget, Acceptance, agent blocks |
| Preflight   | (automatic)                              | `kanban-advanced:kanban-preflight`      | `preflight.sh` — env, gateway, profiles, coding CLI, FS (see governance wiki) |
| Attestation | (automatic)                              | `kanban-advanced:kanban-orchestrator`   | `attestation.yaml` (120 min TTL) — **mandatory** (A001–A003) |
| Pre-dispatch | (before decompose)                      | `kanban-advanced:kanban-orchestrator`   | `pre_dispatch_gate.sh` — single entry; folds preflight + attestation + infra |
| Handoff     | `"Execute the plan"` (non-orchestrator)  | `kanban-advanced:kanban-advanced`       | `kanban_handoff.py` — gate stamp, dispatcher preconditions |
| Decompose   | (automatic)                              | `kanban-advanced:kanban-orchestrator`   | Crons `--check`, card policy (P001–P009), `validate_board.sh` |
| Worker pre-exec | (per card, Step 3)                   | `kanban-advanced:kanban-worker`         | `worktree_setup.sh`, **E021**, coding-agent smoke |
| Execute     | (worker dispatch)                        | `kanban-advanced:kanban-worker`         | Preflight cache fast path (< 30 min); else full preflight |
| Verify      | (automatic)                              | `kanban-advanced:kanban-worker`         | **Evaluation chain** E001–E020 (DAL ALLOW/DENY); **E021** is Layer 5 pre-exec |
| Audit       | (automatic)                              | `kanban-advanced:kanban-orchestrator`   | 10-gate final audit                                        |
| Reconcile   | `"Yes"` (at checkpoint)                  | `kanban-advanced:kanban-reconciliation` | Error code → recovery mapping                              |
| Postmortem  | `"Yes"` (at checkpoint)                  | `kanban-advanced:kanban-postmortem`     | Structured retrospective from kanban.db (before archive)   |
| Cleanup     | `"Yes"` (at checkpoint)                  | `kanban-advanced:kanban-cleanup`        | Board archive + cron removal                               |
| Recovery    | (on failure)                             | `kanban_recover.py`     | 10 automated recovery actions + cascade triage             |
| Pause/Reset | `"Pause the plan"` / `"Block and reset"` | `kanban-advanced:kanban-orchestrator`   | Blocks all cards, preserves plan file                      |

## Package structure

```
hermes-kanban-advanced-workflow/
├── plugin.yaml                       # Plugin manifest (Hermes discovers this)
├── __init__.py                       # Root proxy → plugin/__init__.py
├── plugin/
│   ├── __init__.py                   # register(ctx): wires everything
│   ├── config_overlay.py             # Config read/write: build_overlay_yaml, read_overlay_config, _MANAGED_KEYS
│   ├── script_materialize.py         # Skill preservation + script sync to $HERMES_HOME
│   ├── schemas.py                    # 7 tool schemas (what the LLM sees)
│   ├── tools.py                      # 7 tool handlers (wraps hermes kanban CLI)
│   ├── hooks.py                      # on_session_start; post_tool_call (board JSONL + event-driven auto_unblock)
│   ├── cli.py                        # hermes kanban-advanced <subcommand>
│   ├── skills/                       # 12 skill subdirectories, each with SKILL.md
│   └── data/
│       ├── references/               # shared reference docs (+ skill-local index under skills/kanban-advanced/references/)
│       ├── registry/                 # error-codes.yaml
│       ├── policies/                 # card-body-policy.yaml
│       └── prompts/                  # orchestrator.md, worker.md
├── scripts/                          # Bootstrap, cron, governance scripts
├── bundles/                          # Skill bundle for non-plugin sessions
├── docs/                             # User-facing documentation
├── wiki/                             # Agent-facing reference
└── README.md
```

## Config serialization pipeline

The overlay config at `.hermes/kanban-overrides/kanban-config.yaml` is the single source of truth for every subsystem — branch model, profiles, coding agent, policy, lifecycle toggles, plan paths. Two functions in `plugin/config_overlay.py` gate all access to it:

```mermaid
flowchart TB
    CONFIG["kanban-config.yaml<br/>(.hermes/kanban-overrides/)"]

    CONFIG --> READ["read_overlay_config()"]
    CONFIG --> YAML["yaml.safe_load()"]

    READ --> FLAT["flat dict[str,str]<br/>(top-level keys only;<br/>indented lines skipped)"]
    YAML --> NESTED["nested keys:<br/>subagent_gate, plan_search_dirs,<br/>ui_stack, escalation_max_attempts"]

    FLAT --> BUILD["build_overlay_yaml()"]

    BUILD --> INIT["Init<br/>(dashboard Bootstrap or CLI)"]
    BUILD --> SAVE["Save<br/>(dashboard toggle change)"]
    BUILD --> HANDOFF["Handoff<br/>(kanban_handoff.py stamps overlay)"]

    INIT --> ORDER
    SAVE --> ORDER
    HANDOFF --> ORDER

    subgraph ORDER["Serialization order"]
        direction TB
        S1["1. Write managed keys fresh<br/>(_MANAGED_KEYS)"]
        S2["2. Pass through unrecognized<br/>operator-owned keys"]
        S3["3. Write structured blocks<br/>(plan_search_dirs,<br/>escalation_max_attempts,<br/>subagent_gate)"]
        S1 --> S2 --> S3
    end
```

### Read: `read_overlay_config(path) → dict[str, str]`

Reads **flat top-level `key: value` pairs only**. Indented (nested) lines under `escalation_max_attempts`, `subagent_gate`, and `ui_stack` are skipped — they belong to parent blocks managed elsewhere. For nested access, use `yaml.safe_load()` directly (e.g., `read_plan_search_dirs_from_overlay`, `read_subagent_gate_config`).

### Write: `build_overlay_yaml(...) → str`

Serializes the full config in three passes:

1. **Managed keys** — `_MANAGED_KEYS` members (branches, profiles, coding agent, paths, policy, lifecycle toggles) are written from current state. These 17 keys are owned by init/save and rewritten fresh every cycle.
2. **Pass-through** — Any key in the existing config that is NOT in `_MANAGED_KEYS` is preserved as-is. This is how operator-added keys (e.g., `required_secrets`, `gateway_timeout_seconds`, `final_audit_overrides`) survive re-init. **Caveat:** bugs that introduce bogus keys (e.g., the old flat reader flattening nested values) are also preserved — the pass-through is agnostic.
3. **Structured blocks** — `plan_search_dirs`, `escalation_max_attempts`, and `subagent_gate` are written as YAML blocks with their nested children.

### Callers

| Trigger | Path | What it does |
|---------|------|-------------|
| Dashboard Bootstrap | `POST /init` → `_execute_init()` → `build_overlay_yaml()` | Full init: profiles, model config, coding agent, skills, scripts, env, gateway |
| Dashboard Save | `POST /save` → `_execute_save()` → `build_overlay_yaml()` | Persist form field changes (toggle, dropdown, branch) without full re-init |
| CLI init | `hermes kanban-advanced init` → `_handle_init()` → `build_overlay_yaml()` | Interactive terminal bootstrap with prompts |
| Update Plugin | `POST /update` → `_materialize_plugin_assets()` → `materialize_hermes_scripts()` | Scripts only — does NOT rewrite config |
| Kanban handoff | `kanban_handoff.py` → stamps overlay fields | Records `notify_lifecycle`, `walk_away_mode`, `notify_deliver` at dispatch time |

### Skill preservation

Scripts (`materialize_hermes_scripts`) are overwritten on every materialization — they are infrastructure, not user-editable. Skills (`materialize_skills_with_preservation`) use a three-way hash comparison against `.materialize-manifest.json` to detect operator edits and preserve them across updates. See `plugin/script_materialize.py`.

### Related

- **Config key reference:** [`wiki/configuration.md`](../../wiki/configuration.md) — every key, default, and purpose
- **Schema:** [`schema/kanban-config.schema.json`](../../schema/kanban-config.schema.json) — JSON Schema with `additionalProperties: false`
- **Example:** [`kanban-config.example.yaml`](../../kanban-config.example.yaml)
