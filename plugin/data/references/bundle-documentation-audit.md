# Bundle documentation audit

Detect drift between **README / docs tree** and the live plugin layout. Distinct from `provision.sh --check` (runtime materialization).

## README vs file tree

```bash
# Skills declared in plugin.yaml
grep -A20 'provides_skills' plugin.yaml

# Skills on disk
ls plugin/skills/*/SKILL.md | wc -l
```

Expect counts to match (currently **11** skills).

## Reference doc inventory

```bash
ls plugin/data/references/*.md | wc -l
```

Update `docs/reference/architecture.md` if the count changes materially.

## Common drift signals

- README error-code count ≠ `error-codes.yaml` length.
- `AGENTS.md` routing table points at deleted paths.
- Wiki `[[wikilinks]]` without `wiki/<page>.md` target.

## Fix order

1. Registry / code SSOT (`error-codes.yaml`, scripts).
2. `plugin/data/references/` and skills.
3. `wiki/` and `docs/`.
