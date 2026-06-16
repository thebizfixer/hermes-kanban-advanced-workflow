# Parallel subagent gate

**Status:** Default orchestrator path (Hermes `delegate_task` background subagents)  
**Serial fallback:** `scripts/pre_dispatch_gate.sh` (unchanged)  
**Overlay toggle:** `subagent_gate.enabled` in `.hermes/kanban-overrides/kanban-config.yaml` (default **true**; set `false` to force serial only)

## Motivation

The pre-dispatch gate runs 13+ checks sequentially. The bottleneck is `preflight.sh` (30–60s for coding-agent CLI smoke, profile validation, memory/disk checks). Independent check domains can run in parallel, cutting gate wall-clock from ~60–90s to ~30–60s without weakening any check.

## Three independent domains

| Domain | Checks | Writable state |
|--------|--------|----------------|
| **Plan** | plan on branch, plan pushed, plan memory exists/fresh | None (read-only git/fs) |
| **Env** | preflight.sh, coding-agent CLI smoke | `preflight_cache.json` only |
| **Infra** | kanban.db PRAGMA, cron scripts, hermes PATH, card policy script, gateway | None (read-only) |

Governance order after collection (serial, orchestrator only): **domain results → attestation → coding_agent_auth_prewarm → decompose**. Attestation records combined state — never run in parallel with domain checks.

### Serial parity (blocking vs warning)

Parallel subagents mirror `pre_dispatch_gate.sh` severities. Domain `status: fail` only when a **blocking** check fails; warning-severity failures are reported but do not block (same as serial WARN lines).

| Check | Serial | Parallel domain |
|-------|--------|-----------------|
| plan on branch | FAIL | A blocking |
| plan pushed | WARN | A warning |
| plan memory | FAIL | A blocking |
| plan memory fresh | WARN | A warning |
| preflight `pass`/`degraded` | PASS | B pass |
| preflight `fail` | WARN | B warning (domain still pass) |
| coding_agent_cli | FAIL | B blocking |
| attestation | FAIL (mid-script) | Wave 2 serial |
| card_policy_script | WARN | C warning |
| kanban_db / cron / hermes PATH | FAIL | C blocking |
| gateway_running | WARN | C warning |
| coding_agent_auth_prewarm | WARN/blocking | Wave 2 serial |

## Orchestrator flow

1. Read overlay: `subagent_gate.enabled` — default **true** when key absent (`resolve_subagent_gate_enabled` in `plugin/config_overlay.py`).
2. If `enabled: false` **or** `delegate_task` / `delegation` toolset unavailable → `bash <BUNDLE>/scripts/pre_dispatch_gate.sh <plan_id>` (serial fallback).
3. If enabled and delegation available, load context templates from `plugin/data/prompts/gate-subagent-*.md`, substitute `{REPO_ROOT}`, `{PLAN_ID}`, `{BUNDLE_PATH}`, `{WORKING_BRANCH}`, `{PLAN_MEMORY_PATH}`, `{HERMES_HOME}`, `{CODING_AGENT_PROBE_TIMEOUT}`.
4. Wave 1 — `delegate_task` three tasks in parallel (`toolsets: ["terminal"]` only for A/B/C).
5. Wave 2 — collect JSON; domain `status: fail`, any blocking check fail, malformed JSON, or domain timeout → report **all** failures, then **serial fallback** or STOP. Warnings alone do not block.
6. Wave 2 serial — `kanban_attestation.py <plan_id> --verify` (generate if missing), then `coding_agent_auth_prewarm` (blocking when `KANBAN_CODING_AGENT=agent`).
7. Proceed to decomposition (standard process or decomposition parallelization below).

### Delegation pre-check

```bash
hermes tools list 2>/dev/null | grep -q delegation || FALLBACK_TO_SERIAL=1
```

Orchestrator profile must have the `delegation` toolset for parallel path. Handoff cards with `pre_dispatch_gate: PASSED` skip both paths.

## Subagent context templates

| File | Role |
|------|------|
| `gate-subagent-plan.md` | Subagent A — plan domain |
| `gate-subagent-env.md` | Subagent B — env domain |
| `gate-subagent-infra.md` | Subagent C — infra domain |
| `gate-subagent-plan-parse.md` | Subagent D — decomposition prep |
| `gate-subagent-cron-setup.md` | Subagent E — decomposition prep |

Load via `skill_view` path or `cat <BUNDLE>/plugin/data/prompts/gate-subagent-plan.md`.

## Timeouts (overlay)

```yaml
subagent_gate:
  enabled: true
  timeouts:
    plan_gate: 30
    env_gate: 120
    infra_gate: 15
    plan_parse: 60
    cron_setup: 30
```

| Subagent | Expected | Default timeout |
|----------|----------|-------------------|
| A — Plan | 5–15s | 30s |
| B — Env | 30–60s | 120s |
| C — Infra | 2–5s | 15s |
| D — Plan parse | 10–30s | 60s |
| E — Cron setup | 5–15s | 30s |

Timeout → treat domain as failed (E022). Recovery: fall back to serial gate (`kanban-orchestrator-governance`).

## Decomposition-phase parallelization

When parallel gate is enabled (default), optional second wave during decomposition:

- **Wave 1 parallel:** Subagent D (plan parse) + Subagent E (cron setup).
- **Wave 2 serial:** DB integrity check → create root → create gate → staggered card creation (unchanged) → validate → complete gate.

Card creation **must stay serial** — parallel `kanban_create` writes risk SQLite torn-extend errors.

## Anti-stepping rules

1. Subagents use restricted toolsets — no `delegation`, `kanban_create`, or attestation writes.
2. No shared mutable state across domains (see table above).
3. Orchestrator is the sole collection and gating point.
4. Structured JSON contracts — ambiguous output = failure.
5. Attestation and prewarm stay serial after all domains pass.

## What does not change

- `pre_dispatch_gate.sh` — serial fallback
- `preflight.sh`, `kanban_attestation.py`, `kanban_decompose.py`, `validate_board.sh`
- Worker skill — workers do not run gate checks
- `kanban_handoff.py` — defers serial gate at handoff build when `subagent_gate.enabled` is not `false` (orchestrator runs parallel Step 1); serial at build when `enabled: false`

## Speedup (typical)

| Phase | Serial | Parallel subagents |
|-------|--------|-------------------|
| Gate total | ~60–90s | ~30–60s |
| Decomp prep | ~35–70s | ~25–50s |

Qualitative win: preflight JSON and parse details stay in subagent context — only summaries enter the orchestrator thread.

## Cross-references

- Orchestrator SOP: `kanban-advanced:kanban-orchestrator` § Pre-dispatch gate
- Sad-path: `kanban-advanced:kanban-orchestrator-governance` § E022
- Config: `wiki/configuration.md` § `subagent_gate`
- Layer 2 governance: `wiki/governance.md` § Pre-dispatch gate
