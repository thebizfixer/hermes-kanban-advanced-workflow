# Documentation style (kanban-advanced)

## Paths

- **System-agnostic:** `hermes-kanban-advanced-workflow/scripts/...` or `$BUNDLE/scripts/...` — not machine-specific absolute paths in skills.
- **Hermes state:** `$HERMES_HOME` — not `~/.hermes` alone when teaching operators.

## Terminology

| Context | Use |
|---------|-----|
| Hermes CLI sessions | **Hermes Agent** / **worker profile** |
| Vendor coding CLI | **coding agent** / configured binary name |
| User-authored plan prose | Preserve voice; do not rewrite without request |

## Wiki tables

- Prefer `wiki/*.md` for agent-facing deep dives; `docs/` for Diátaxis user docs.
- Wikilinks `[[page]]` only when `wiki/<page>.md` exists; otherwise use `` `plugin/data/references/...` ``.

## Skills vs references

- Procedural steps live in `SKILL.md`.
- Long checklists and SSOT tables live in `plugin/data/references/`.
- **Plan markdown format** (markup-safe placeholders, `Spec:` blocks): `plan-file-format.md`.
- After init, bridge skill bundles references for `skill_view("kanban-advanced:kanban-advanced", "references/<file>.md")`.
