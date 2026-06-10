# Goal-card selection (kanban `--goal`)

When to use Hermes **goal-mode cards** (`hermes kanban create … --goal`) on a **kanban-advanced** board. Requires **Hermes Agent ≥ 0.16.0**.

**Enhance, not replace:** vanilla goal-mode adds a semantic judge loop; this bundle still requires the **evaluation chain** before every `kanban_complete`. See [docs/how-to/goal-cards.md](../docs/how-to/goal-cards.md).

## Three tiers

| Tier | Mechanism | When |
| --- | --- | --- |
| `/goal` | Session standing goal (CLI/gateway) | Small scope, no board, no governance pipeline |
| Vanilla kanban | One-shot cards (default) | Parallel workstreams, crash resilience, audit trail |
| Kanban-advanced + `--goal` | Rare per-card goal loop + eval chain | 0–2 cards per plan after Harden; outcome-based lanes that resist splitting |

## Upstream best practices

Sourced from [Persistent Goals](https://hermes-agent.nousresearch.com/docs/user-guide/features/goals), [Kanban goal-mode](https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban), and Hermes PR #18262.

| Practice | Guidance | Advanced-workflow twist |
| --- | --- | --- |
| Four-part acceptance | Object, done-when, verify, out-of-scope | `Acceptance:` for judge; `Tests:` for eval chain |
| Conservative judge | Done only when completion is explicit or genuinely blocked | Still run eval chain when judge says done |
| Fail-open judge | Judge errors → continue; budget is the backstop | Set `goal_max_turns` in plan (often 15–20) |
| Not for exploration | `/goal` fights “look around” tasks | Harden: spikes → `goal_card: false` |
| Single primary outcome | No compound goal priorities | One `Acceptance:` block; optional `subgoals:` in frontmatter |
| User preemption | Real user messages preempt auto-continue | `/kanban comment` still works mid-run |
| Cheap judge model | Fast auxiliary model in `config.yaml` | Separate from worker/coding-agent model |
| Skip cheap one-shots | Judge overhead not worth one-pass work | Default one-shot cards |

### Acceptance block template

```markdown
Acceptance:
- Object: <what artifact or system state must exist>
- Done when: <observable condition, measurable if possible>
- Verify: <command, dashboard, or check the worker runs before kanban_complete>
- Out of scope: <paths, envs, or behaviors that must not change>
```

## Scenario index (Harden)

During **Harden**, tag each code workstream with `goal_scenario: D1` … `D10`, `A1` … `A10`, or `none`. Default `goal_card: false`. Plan-level `goal_card_budget: 2` (max goal cards per plan).

### D1–D10: good fit for `--goal` (use sparingly)

| ID | Scenario | Harden signal | Example acceptance (judge-facing) |
| --- | --- | --- | --- |
| D1 | CI gate recovery | One integration lane; history of early exit after failing tests | Done when: test + integration suite green on `${working_branch}`; no skipped tests without waiver |
| D2 | Terraform / IaC parity | Bounded stack; plan must be empty after apply | Done when: `terraform plan` empty for workspace AND smoke check passes |
| D3 | Cross-service config rollout | Same pattern across N services, one release | Done when: every service in list X has key Y; validator passes |
| D4 | Kubernetes baseline | All deployments in ns match policy P | Done when: audit script reports 0 violations for P |
| D5 | Dependency upgrade (bounded module) | Single workspace; tests flap until lockfile aligned | Done when: lockfile updated, test command green, no new high-severity audit issues |
| D6 | Observability / SLO wiring | Every service exports metric M with labels L | Done when: checklist finds M on all services in registry R |
| D7 | Secret / env migration | All runtimes use SECRET_V2 | Done when: old secret name absent in deploy configs; staging health 2xx |
| D8 | Incident remediation | Runbook with measurable stop condition | Done when: error rate below 1% for 15m OR mitigation per runbook §N |
| D9 | DB + app coordinated change | Migration and code must land together | Done when: migration applied, app starts, migration test job green |
| D10 | E2E smoke stabilization | Flaky E2E after deploy | Done when: E2E command passes 2 consecutive runs in worktree |

### A1–A10: anti-patterns (`goal_card: false`)

| ID | Scenario | Do instead |
| --- | --- | --- |
| A1 | Single-file config / flag | One-shot card or `/goal` without board |
| A2 | Independent microservices | Parallel one-shot cards per service |
| A3 | Spike / root-cause exploration | Interactive Hermes; then new plan |
| A4 | Orchestrator gate / audit / root | Orchestrator profile, no `--goal` |
| A5 | Mechanical rename / typo | One-shot per package or ≤2 files per card |
| A6 | Docs-only | Orchestrator or `/goal`; no worker eval chain |
| A7 | Whole-repo refactor by directory | Split by directory |
| A8 | Latency-sensitive hotfix | Direct `agent -p` |
| A9 | Cost-capped / single-provider | Fewer cards; no judge loop overhead |
| A10 | Plan fits README “Why NOT” | `/goal` or skip advanced pipeline |

## Decision checklist (all must be true for `goal_card: true`)

1. Single workstream cannot split without losing coherence.
2. Success is **outcome-based** (measurable acceptance in prose).
3. Prior runs or plan risks show **early worker exit** with incomplete work, OR happy-path estimate **> ~15 turns** and splitting increases merge risk.
4. `goal_card_budget` not exhausted (default max **2** per plan).
5. Section is **not** matched by any **A*** anti-pattern row.

## Plan frontmatter (Optimize)

```yaml
goal_card_budget: 2
workstreams:
  - id: ws-integration
    goal_card: true
    goal_scenario: D1
    goal_max_turns: 18
    goal_rationale: "Single integration lane; CI must be green before merge"
```

Each `goal_card: true` section must include an **`Acceptance:`** block in the plan body (copied into card body at decomposition).

## Related

- [docs/how-to/goal-cards.md](../docs/how-to/goal-cards.md)
- `kanban-advanced:kanban-planning` — Harden item #10, Optimize acceptance
- `kanban-advanced:kanban-orchestrator` — `--goal` on create
- `kanban-advanced:kanban-worker` — goal loop + eval chain
- [hermes-v0.15.0-upgrade.md](hermes-v0.15.0-upgrade.md)
