# Plugin verification tests (install & bootstrap)

> **For the agent:** When install, bootstrap, **Update Plugin**, or materialized skills/scripts look wrong, run the suites below **before** guessing or re-running init in a loop. These tests do not need a live board or plan — most run from the plugin checkout or `$HERMES_HOME` materialized bundle.

## When to load this page

| User / symptom | Run |
| --- | --- |
| "Bootstrap failed" / profile reconciliation errors | Tier 2 + bootstrap output lines |
| Stale skills after **Update Plugin** | `provision.sh --check`, Tier 1 smoke |
| "Plugin broken" / missing tools or hooks | Tier 1 `smoke_test_plugin.py` |
| Developer / CI validating a checkout | Tier 1 full (`sanity_check.sh` includes unit tests) |
| Decomposition blocked but init passed | Tier 3 (`preflight.sh`, `check_coding_agent_cli.py`) — auth is separate from plugin contract |
| `governance_integrity.sh` reports missing registry/skills | Wrong working directory — see **Where to run** |

**Not covered here:** host-app `pytest`/`npm test`, gateway dispatch, kanban board state — use [[troubleshooting]] and the in-flight index.

## Platform, shell, and host repo (read first)

Supported environments match [PLATFORM_NOTES.md](../PLATFORM_NOTES.md) and [coding agents](../docs/reference/coding-agents.md):

| Environment | Run `.sh` scripts | Python smoke / unit tests | Host repo |
| --- | --- | --- | --- |
| **Linux / macOS** | Native `bash` | `python3` (or `python`) from plugin checkout | Any git repo with `.hermes/kanban-overrides/` after init |
| **Windows native** | Hermes **Git Bash** (PortableGit) — not CMD alone | `python scripts/smoke_test_plugin.py` from repo root | Same; set `HOME=` in `.env` for coding CLI OAuth |
| **WSL2** | Native `bash` inside WSL | `python3` inside WSL | Clone to **native ext4** (`~/projects/…`) — not `/mnt/c/` (preflight E011) |

**Bundle path:** Examples use `hermes-kanban-advanced-workflow/` as a neutral submodule/install dir name. Your overlay `bundle_path` in `kanban-config.yaml` may differ — substitute `${bundle_path}` or the path init materialized under `$HERMES_HOME/scripts/`.

**Coding agent binary:** Tier 3 probes the **configured** CLI (`KANBAN_CODING_AGENT` / dashboard **Coding Agent** picker). Init and dashboard populate the picker from commands **on PATH** (`cursor-agent`, `claude`, `codex`, `grok`, `aider`, `gemini`, custom). Auth is per vendor; see `plugin/data/references/coding-agent-auth.md`. Bootstrap smoke is **advisory** for all binaries; preflight/gate **block** when smoke fails. Contested shared names: [coding agents](../docs/reference/coding-agents.md) § Binary name collisions.

**Windows note:** `sanity_check.sh` requires bash and checks **LF** line endings on shell scripts (repo shipping standard). Run Tier 1 shell checks from Git Bash or WSL, not plain CMD.

## Where to run (paths)

| Location | Typical path | Use for |
| --- | --- | --- |
| **Plugin checkout** | Git clone or submodule `hermes-kanban-advanced-workflow/` | Tier 1 — source tree layout |
| **Hermes install dir** | `$HERMES_HOME/.hermes/plugins/kanban-advanced/` (see `hermes plugins list`) | Tier 1 after **Update Plugin** |
| **Materialized bundle** | `$HERMES_HOME/scripts/` (+ sibling `registry/`, `policies/`, `prompts/`, `skills/`) | Tier 2 `governance_integrity.sh` |
| **Host app repo** | Project root with `.hermes/kanban-overrides/kanban-config.yaml` | Tier 2 `provision.sh --check`, Tier 3 preflight |

`governance_integrity.sh` expects the **plugin checkout** (`plugin/data/*`, `plugin/skills/*`) or a legacy flat materialized bundle. Running it from an unmaterized monorepo without `plugin/data/registry` will fail — run Tier 1 `sanity_check.sh` on the checkout, or run integrity from `hermes-kanban-advanced-workflow/scripts/` after clone.

Resolve `$HERMES_HOME`: see [[bootstrap#hermes_home-resolution]] and `plugin/data/references/hermes-state-directory.md`.

---

## Tier 1 — Plugin contract (no Hermes runtime)

Fast checks that the plugin **registers** correctly: skills, tools, hooks, CLI.

```bash
cd /path/to/hermes-kanban-advanced-workflow   # or installed plugin dir

# Contract smoke — skills, tools, hooks, on_session_start role split
python3 scripts/smoke_test_plugin.py    # Windows: python scripts/smoke_test_plugin.py

# Structural + shell + unit tests (bash required; includes unittest when python on PATH)
bash scripts/sanity_check.sh
```

| Script | Exit 0 means | Common failures |
| --- | --- | --- |
| `smoke_test_plugin.py` | All 13 skills, 7 tools, 4 hooks, CLI register; handlers callable | Missing `kanban-git` in roster, broken `register()` import |
| `sanity_check.sh` | Dirs present, all `*.sh` pass `bash -n`, LF endings, skill frontmatter, error registry (incl. E028/E029), presentation acceptance scripts, unit tests pass | Bash heredoc/syntax in a script, CRLF on shell scripts, unittest failures |

**Full Python unit suite** (same as sanity_check’s unittest block; use `-v` for detail):

```bash
cd /path/to/hermes-kanban-advanced-workflow
python3 -m unittest discover -s tests -p 'test_*.py' -v   # Windows: python -m unittest …
```

Optional: `python -m pytest tests/ -v --tb=short` if pytest is installed — not required for plugin CI. `sanity_check.sh` tries `python3`, then `python`, then `py -3` on Windows.

---

## Tier 2 — Post-bootstrap / materialization (host project or `$HERMES_HOME`)

Confirms skills and scripts on disk match the plugin bundle after init or **Update Plugin**.

```bash
# From host app repo root (where .hermes/kanban-overrides/ lives)
bash hermes-kanban-advanced-workflow/scripts/provision.sh --check

# From plugin checkout (structural governance + optional provision when overlay exists)
bash hermes-kanban-advanced-workflow/scripts/governance_integrity.sh
# optional JSON: bash hermes-kanban-advanced-workflow/scripts/governance_integrity.sh --json
```

| Script | Exit 0 means | Common failures |
| --- | --- | --- |
| `provision.sh --check` | Materialized skills under configured `skills_output_path` match plugin source hashes; `$HERMES_HOME/scripts/lib/` includes `card_body.py`, `presentation_acceptance.py`, `verify_optimization_presentation.py` | Hand-edited skill files, init not re-run after pull, stale lib sync |
| `governance_integrity.sh` | Required scripts + lib modules, registry/policies/prompts/skills/references present (plugin layout), E028/E029 in registry, provision check when host overlay exists | Run from wrong directory; missing `frontend-neutrality.md` or presentation lib modules |

After **Update Plugin** on the dashboard: run Tier 1 on the install dir, then Tier 2 from the host project, then **Bootstrap** if reconciliation still fails — see [[bootstrap#troubleshooting]]. For the full update workflow (Update Plugin → Bootstrap → gateway restart → verify), see [README.md](../README.md#updating-the-plugin), the [install guide](../docs/how-to/install-as-plugin.md#updating), or [[setup#updating-the-plugin]].

---

## Tier 3 — Environment & bootstrap gates (host project)

These validate **operator** readiness — not the plugin Python package alone. Bootstrap **advisory** smoke can pass while these **block** decomposition.

```bash
cd your-host-app

# Blocking coding-agent CLI (same probe as pre-dispatch gate; any configured binary)
grep -E '^(KANBAN_CODING_AGENT|HOME)=' .env
python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py

# Full environment gate (JSON to stdout)
bash hermes-kanban-advanced-workflow/scripts/preflight.sh

# Pre-decomposition stack (includes attestation, plan memory, cron script presence)
bash hermes-kanban-advanced-workflow/scripts/pre_dispatch_gate.sh <plan_id>
```

See [[bootstrap#coding-agent-auth-during-bootstrap-limitations]], [[troubleshooting]] (coding-agent / preflight sections), and `plugin/data/references/coding-agent-auth.md`.

---

## Recommended order (install / bootstrap troubleshooting)

1. **Tier 1** on plugin checkout or install dir — rules out broken plugin package.
2. **Tier 2** `provision.sh --check` on host repo — rules out stale materialization.
3. Re-run **Bootstrap** or `hermes kanban-advanced init` if Tier 2 failed; read verification lines in output ([[bootstrap#verify-on-disk-after-bootstrap]]).
4. **Tier 3** if init succeeded but execute/preflight fails — usually `.env`, `HOME`, or coding CLI auth.
5. If still stuck: [[troubleshooting]] + `skill_view("kanban-advanced:kanban-advanced", "references/in-flight-governance-index.md")`.
6. **Run the end-to-end smoke test** — copy [the standard smoke test plan](../test-plan/kanban-standard-smoke-test.plan.md) to `.hermes/kanban/plans/`, decompose, and execute. Validates the full governance pipeline (evaluation chain E001–E023, escalation ladder with 5-loop cap, token metering, postmortem generation). Expected: 5 cards, 8/8 tests passing, postmortem artifacts.

---

## CI / maintainer reference

From a clean plugin checkout on **Linux, macOS, or WSL** (bash + python3):

```bash
bash scripts/sanity_check.sh          # structure + bash -n + unittest
python3 scripts/smoke_test_plugin.py  # contract
python3 -m unittest discover -s tests -p 'test_*.py' -q
```

On **Windows native**, run the same from Git Bash; use `python` if `python3` is not on PATH.

Reference detail: [`docs/reference/scripts.md`](../docs/reference/scripts.md) (governance scripts), [`docs/reference/platform-neutral-parsing.md`](../docs/reference/platform-neutral-parsing.md) (sanity guard for `grep -P`), [PLATFORM_NOTES.md](../PLATFORM_NOTES.md) (Hermes home, temp, worktree paths).

---

## Related pages

- [[setup]] — install and first bootstrap
- [[bootstrap]] — what init provisions vs operator-owned
- [[troubleshooting]] — runtime failures (E-codes, gateway, auth)
- [[governance]] § Plugin integrity — when to run `governance_integrity.sh` before a plan
- [PLATFORM_NOTES.md](../PLATFORM_NOTES.md) — Windows / WSL / macOS / Linux paths and limits
- [coding agents](../docs/reference/coding-agents.md) — supported CLI binaries and auth
- [Smoke test plan](../test-plan/kanban-standard-smoke-test.plan.md) — end-to-end governance validation
- `AGENTS.md` — agent question router
