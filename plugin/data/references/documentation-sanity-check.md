# Documentation sanity check

Run after large doc edits or before plan hardening sign-off.

## Stale reference detection

```bash
# Broken relative markdown links (repo root)
python3 - <<'PY'
import re
from pathlib import Path
root = Path(".")
missing = []
for md in root.rglob("*.md"):
    if ".git" in md.parts:
        continue
    for _, t in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", md.read_text(errors="ignore")):
        if t.startswith(("http", "#")):
            continue
        p = (md.parent / t.split("#")[0]).resolve()
        if t.split("#")[0] and not p.exists() and not (root / t.split("#")[0]).exists():
            missing.append((md, t))
for m, t in missing[:30]:
    print(m, "->", t)
print("total", len(missing))
PY
```

## Code fence integrity

- Opening ` ``` ` on its own line; closing fence matches language tag.
- No nested fences inside examples without indentation.

## Table formatting

- Header separator row required (`|---|`).
- No mixed HTML tables in markdown skills/wiki.

## Package tree maintenance

- Update `docs/reference/architecture.md` tree when adding `plugin/data/references/` files.
- Error code count in prose must match `plugin/data/registry/error-codes.yaml` (currently **37**).
