# Final audit — doc coverage matrix (Tier 2 SSOT)

**Load:** `skill_view("kanban-advanced:kanban-advanced", "references/final-audit-doc-coverage.md")`

Tier 2 of `scripts/final_audit_sanity.py` maps **code/config signals** in plan-touched paths to **required doc surfaces**. Gaps spawn worker remediation cards (`Remediation-phase: final`).

## Coverage matrix

| Code/config signal | Required doc surfaces |
| --- | --- |
| `plugin/config_overlay.py` managed key | `wiki/configuration.md`, `kanban-config.example.yaml`, `schema/kanban-config.schema.json` when applicable |
| New/changed `scripts/*.sh` or `scripts/lib/*` | `docs/reference/scripts.md`; materialize list in `plugin/script_materialize.py` if shipped to `$HERMES_HOME` |
| Bootstrap/init behavior | `wiki/bootstrap.md`, `dashboard/API.md`, `llms.txt` |
| Skill behavior change | Matching `plugin/skills/*/SKILL.md` |
| New registry code P0xx/E0xx | `plugin/data/registry/error-codes.yaml` + cross-ref in troubleshooting if operator-visible |
| Dashboard field | `dashboard/API.md` + `dashboard/dist/index.js` if UI |

## Violation classes (Tier 2)

| Class | Meaning |
| --- | --- |
| `doc_coverage_gap` | Changed code surface has no matching doc mention or link |
| `doc_link_stale` | Doc references a removed symbol or path |
| `approved_skip` | Matched `final_audit_overrides` entry — logged, not counted, not spawned |

## Allowlist (`final_audit_overrides`)

In `.hermes/kanban-overrides/kanban-config.yaml`:

```yaml
final_audit_overrides:
  - signal: doc_coverage_gap
    path: scripts/lib/some_internal.py
    rationale: "Internal helper — no scripts.md entry required"
```

`final_audit_sanity.py` downgrades matching violations to `approved_skip`.

## Cross-references

- Runbook + exit codes: `final-audit-sanity-check.md`
- Orchestrator SOP: `kanban-advanced:kanban-orchestrator` § Final audit
- KPI fields: `docs/reference/kpis.md`
