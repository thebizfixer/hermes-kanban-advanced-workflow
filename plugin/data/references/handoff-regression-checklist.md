# Handoff regression checklist

Run after **Update Plugin**, **init/reconcile**, or before repeating a governed decomposition on a project that previously failed (e.g. Sentimentary Matrix v5 runs).

## 1. Handoff card body

```bash
python3 scripts/kanban_handoff.py --plan <plan.md> --dry-run 2>/dev/null || \
  hermes kanban show <handoff_task_id>
```

Confirm stamped fields:

| Field | Expected |
|-------|----------|
| `BUNDLE_ROOT` | Absolute path to plugin bundle |
| `cards_yaml` | Path when `.hermes/kanban/memory/<plan_id>.yaml` exists |
| `pre_dispatch_gate` | `PASSED …` when gate ran before handoff |
| `gate_script` | Absolute path to `pre_dispatch_gate.sh` |

## 2. Worker SOUL consistency

Worker profile SOUL must **not** instruct raw `git worktree add`. After init:

```bash
WORKER_SOUL="$(hermes profile show kanban-advanced-worker 2>/dev/null | grep -i SOUL || true)"
# Or read seeded file:
grep -n 'git worktree add' "${HERMES_HOME}/profiles/kanban-advanced-worker/SOUL.md" 2>/dev/null && echo FAIL || echo OK
```

Expected: **OK** (no matches). Governed path is `worktree_setup.sh` + E021.

## 3. In-flight index rows

Primary: `plugin/skills/kanban-advanced/references/in-flight-governance-index.md`

Verify handoff trigger table is present (scratch, nous portal, delegation, stale skill, E021, etc.).

```bash
grep -c '^| `' plugin/skills/kanban-advanced/references/in-flight-governance-index.md
```

Expect ≥ 15 symptom rows.

### 3b. Materialized bridge references (init / Update Plugin)

After init, shared docs are bundled under the bridge skill for `skill_view`:

```bash
test -f "$HERMES_HOME/skills/kanban-advanced/kanban-advanced/references/in-flight-governance-index.md" \
  && test -f "$HERMES_HOME/skills/kanban-advanced/kanban-advanced/references/profile-switching.md" \
  && echo OK || echo FAIL
```

Expected: **OK** (index SSOT + at least one bundled `plugin/data/references/` file).

## 4. Stale-skills cross-link

- `wiki/troubleshooting.md` documents plugin vs built-in `kanban-worker`.
- Materialized skill: `$HERMES_HOME/skills/kanban-advanced/kanban-worker/SKILL.md` contains `terminal()` dispatch and `execute_code` prohibition.

```bash
grep -q 'terminal()' "$HERMES_HOME/skills/kanban-advanced/kanban-worker/SKILL.md" && echo OK || echo FAIL
```

## 5. Quick smoke (optional)

```bash
bash scripts/coding_agent_invoke.sh smoke
PYTHONPATH=. python3 scripts/check_coding_agent_cli.py
bash scripts/preflight.sh | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status'))"
```

All should pass or degraded-only before decomposition.
