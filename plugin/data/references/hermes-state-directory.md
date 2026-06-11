# Hermes State Directory (`$HERMES_HOME`)

## What it is

**`HERMES_HOME`** is where Hermes stores runtime state: credentials, `kanban.db`, profiles, and gateway config. It is separate from the git repository so `git pull` cannot clobber a live board or leak secrets into version control.

Set explicitly when you use a dedicated state directory:

```bash
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
```

Some installs also honor `HERMES_STATE_DIR`; kanban scripts in this bundle resolve via `scripts/lib/hermes_home.sh`.

## Two buckets

### Code (tracked in git, inside the repo)

| Path | What it is |
| --- | --- |
| `hermes-kanban-advanced-workflow/` | Canonical public skill bundle |
| `.hermes/kanban-overrides/` | Project overlay (`kanban-config.yaml`, patches, optional `references/`) |
| `.hermes/skills/…/kanban-*/` | Materialized skills (output of `provision.sh`) |

### Runtime state (NOT in git)

| Path under `$HERMES_HOME` | What it is |
| --- | --- |
| `config.yaml` | Hermes configuration |
| `auth.json` | API keys |
| `profiles/<name>/SOUL.md` | Agent personas |
| `kanban.db` | Live task board |
| `kanban/tokens.jsonl` | Token log (preflight may create) |

## Layout patterns

**Default:** `HERMES_HOME=$HOME/.hermes` — single machine, one project.

**Dedicated state dir (recommended for multi-clone or split-host setups):**

```bash
export HERMES_HOME=~/.hermes-state/my-project
mkdir -p "$HERMES_HOME/profiles"
```

Point Hermes and all kanban scripts at the same `HERMES_HOME`. The repo clone should live on a **native filesystem** (see `docs/examples/cross-mount-filesystems.md`).

**Symlink (optional):** Some teams symlink `repo/.hermes` → `$HERMES_HOME` for convenience. Others keep overlay paths in-repo (`.hermes/kanban-overrides/`) and only runtime data under `$HERMES_HOME`. Both work if `HERMES_HOME` is consistent in the shell that runs `hermes` and `preflight.sh`.

## Verify

```bash
echo "$HERMES_HOME"
hermes profile list
test -f "$HERMES_HOME/kanban.db" && echo "kanban.db present"
```

## Dispatch profiles (kanban-advanced)

Init manages two dispatch profiles under `$HERMES_HOME/profiles/`:

| Profile | SOUL source | Profile-local skills |
| --- | --- | ---: |
| `kanban-advanced-orchestrator` | `plugin/data/prompts/orchestrator.md` | 9 orchestrator skills |
| `kanban-advanced-worker` | `plugin/data/prompts/worker.md` | 2 worker skills |

Each dispatch profile also has `.no-bundled-skills` (opts out of Hermes bundled skill sync on `hermes update`).

**Do not** use `hermes profile create --clone` for these — init uses `--no-skills`. Full detail: `wiki/bootstrap.md`.

## Profiles: what to copy (manual migration)

| Item | Copy? |
| --- | --- |
| `config.yaml`, `.env` | Yes (init copies from default automatically) |
| `SOUL.md` | Installed by init from plugin prompts — do not copy from default |
| `skills/` | Seeded by init — do not copy from default |
| `sessions/`, `cache/` | No (large; regenerated) |

`hermes_home_hint` in `kanban-config.yaml` is documentation for operators only — it is not substituted into skills.
