# Documentation style (kanban-advanced)

## Paths

- **System-agnostic:** `hermes-kanban-advanced-workflow/scripts/...` or `$BUNDLE/scripts/...` — not machine-specific absolute paths in skills.
- **Hermes state:** `$HERMES_HOME` — not `~/.hermes` alone when teaching operators.

## Terminology

| Context | Use |
|---------|-----|
| Hermes CLI sessions | **Hermes Agent** / **worker profile** |
| Cursor coding CLI | **coding agent** / `agent` binary |
| User-authored plan prose | Preserve voice; do not rewrite without request |

## Wiki tables

- Prefer `wiki/*.md` for agent-facing deep dives; `docs/` for Diátaxis user docs.
- Wikilinks `[[page]]` only when `wiki/<page>.md` exists; otherwise use `` `plugin/data/references/...` ``.

## Skills vs references

- Procedural steps live in `SKILL.md`.
- Long checklists and SSOT tables live in `plugin/data/references/`.
- After init, bridge skill bundles references for `skill_view("kanban-advanced:kanban-advanced", "references/<file>.md")`.
