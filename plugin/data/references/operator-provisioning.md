# Operator provisioning (beyond kanban-advanced init)

> **SSOT** for what bootstrap/init provisions vs what the **project operator** must supply. Load this when helping a user prepare a repo for governed kanban execution.

## Three provisioning layers

| Layer | Who provisions | Survives in card worktree? |
| --- | --- | --- |
| **1. Kanban plugin** | `hermes kanban-advanced init` / dashboard **Bootstrap** | Partially — see `.worktreeinclude` below |
| **2. Gateway / host** | Operator on the machine running `hermes gateway` | Yes — inherited via process env and `$HOME` |
| **3. Application / project** | Operator — **not** written by the plugin | Only if listed in `.worktreeinclude` or inherited env |

Bootstrap succeeding does **not** mean layer 3 is ready.

---

## Layer 1 — What init provisions (plugin scope)

| Asset | Location | Notes |
| --- | --- | --- |
| Dispatch profiles | `$HERMES_HOME/profiles/kanban-advanced-*` | SOUL, role-only skills, model copied from active profile |
| Config overlay | `.hermes/kanban-overrides/kanban-config.yaml` | Branches, coding agent binary/model, policy profile |
| Project `.env` keys | Repo root `.env` | `HERMES_ENABLE_PROJECT_PLUGINS`, `KANBAN_CODING_AGENT`, `KANBAN_CODING_AGENT_MODEL`, `KANBAN_POLICY_PROFILE`, `HOME` |
| Materialized scripts | `$HERMES_HOME/scripts/` (+ `lib/`) | `coding_agent_invoke.sh`, `coding_agent_env.sh`, cron scripts |
| Shared skills | `$HERMES_HOME/skills/kanban-advanced/` | Discoverable from any profile |
| `.worktreeinclude` | Repo root (merge, not overwrite user lines) | Kanban paths only — see below |
| Coding-agent smoke | Advisory at init | Does **not** block init; preflight/gate block later |

### `.worktreeinclude` paths the plugin adds automatically

When project-local `.hermes/` exists (typical project-scoped layout):

```
.hermes/kanban-overrides/
.hermes/kanban/memory/
.hermes/scripts/
.hermes/scripts/lib/
.hermes/plugins/kanban-advanced/scripts/      # when plugin install is under .hermes
.hermes/plugins/kanban-advanced/scripts/lib/
```

`worktree_setup.sh` copies these from the **main checkout** into each card worktree (`/tmp/wt-*`). Commit `.worktreeinclude` after init.

**External `HERMES_HOME`** (`~/.hermes` separate from repo): plugin still adds overlay paths; invoke scripts are reached via `$HERMES_HOME` env, not worktree copy.

---

## Layer 1 — What init does **not** provision

| Item | Why omitted | Operator action |
| --- | --- | --- |
| Vendor API keys | Secrets are project-specific | Add to repo `.env` (gitignored) |
| OAuth for coding CLI | Host-level login | `agent login`, `claude login`, `codex login`, … on gateway host |
| Application secrets | `SECRET_KEY`, `MONGODB_URI`, Stripe keys, … | Add to `.env`; set `required_secrets` in overlay for preflight |
| `.env` in worktrees | Not kanban infrastructure | Add `.env` to `.worktreeinclude` if worktree needs it (see below) |
| `.venv/`, `node_modules/` | Large, stack-specific | Add to `.worktreeinclude` or install policy outside agent |
| Database / Redis / local services | Runtime infrastructure | Operator runs separately; connection strings in `.env` |
| Gateway systemd `HOME` | OS unit config | `Environment=HOME=...` or ensure gateway loads project `.env` |
| Hermes profile LLM keys | Copied from default profile only | User configures `kanban-advanced-orchestrator` / `worker` models separately |

---

## Layer 2 — Gateway / host (usually no worktree copy)

Inherited by Hermes worker sessions when the gateway loads project `.env` or systemd sets vars:

- `HERMES_HOME`, `HOME`, `KANBAN_CODING_AGENT*`
- OAuth credential files under `$HOME/.config/` (Cursor, Codex, Claude cache)

**Cursor OAuth:** does not need `.env` in the worktree if `HOME` is set on the gateway worker. See [coding-agent-auth.md](coding-agent-auth.md).

---

## Layer 3 — Application / project (operator responsibility)

Ask the user what cards will **run in worktrees** (code-gen cards always do). Provision based on their answers.

### Decision guide

| User plans to run… | Likely need in main `.env` | Likely need in `.worktreeinclude` |
| --- | --- | --- |
| Cursor / Claude OAuth coding agent only; no tests hitting `.env` | `HOME` (init writes) | Often **none** beyond plugin paths |
| Codex / Grok / Gemini / Aider with API keys | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROK_API_KEY`, … | **`.env`** if agent/tests read cwd `.env` |
| `pytest` / integration tests in worktree | DB URLs, `SECRET_KEY`, test keys | **`.env`** + often **`.venv/`** |
| Node / frontend tests (`npm test`) | API URLs, feature flags | **`.env`** + **`node_modules/`** (or pre-install policy) |
| Preflight `required_secrets` | Comma list in `kanban-config.yaml` | Same vars must exist when preflight sources main `.env`; worktree cards need **`.env`** if coding agent runs those tests |
| Aider with config file auth | Keys in `.env` or `.aider.conf` | **`.env`** and/or **`.aider.conf`** |

### Common user additions to `.worktreeinclude`

```text
# Application — operator adds (plugin preserves these lines on re-init)
.env
.venv/
node_modules/
.aider.conf
config.local.yaml
```

**Do not** add absolute paths (`/home/...`, `~/.config/...`) — `.worktreeinclude` is repo-relative only.

**WSL:** If `.env` exists only on the Windows side (`/mnt/c/...`), fix layout first (copy or maintain one `.env` in the WSL repo root the gateway uses), then add `.env` to `.worktreeinclude`.

---

## Agent playbook: help the user provision

### 1. Interview (before execute)

Ask:

1. **Coding agent binary** — `agent`, `claude`, `codex`, `grok`, `gemini`, `aider`?
2. **Auth model** — OAuth on gateway host, or API keys in `.env`?
3. **Card tests** — Will workers run `pytest`, `npm test`, migrations, or hit a live DB/API from the worktree?
4. **Dependencies** — Is there a committed `.venv` / `node_modules`, or must the worktree have a copy to run tests?
5. **Preflight** — Any `required_secrets` or `preflight_api_url` in `kanban-config.yaml`?
6. **HERMES_HOME layout** — Project-local `.hermes/` in repo, or `~/.hermes` elsewhere?

### 2. Verify plugin layer

```bash
hermes kanban-advanced init   # or dashboard Bootstrap + Update Plugin
grep -E '^(KANBAN_CODING_AGENT|HOME)=' .env
cat .worktreeinclude
PYTHONPATH=. python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py
```

### 3. Apply operator layer

| Finding | Action |
| --- | --- |
| API-key coding agent | Add keys to `.env`; add `.env` to `.worktreeinclude` |
| OAuth coding agent | `agent login` (etc.) on gateway host; confirm `HOME=` in `.env` |
| Tests need installed deps | Add `.venv/` or `node_modules/` to `.worktreeinclude`, or document install-before-dispatch policy |
| Preflight secret check fails | Fill `required_secrets` vars in main `.env`; mirror into worktree via `.worktreeinclude` if tests run there |
| Worktree missing kanban files | Re-init, commit `.worktreeinclude`, re-run a card |

### 4. After changes

```bash
git add .worktreeinclude   # commit kanban + user paths
hermes gateway restart
rm -f .hermes/kanban/preflight_cache.json
bash hermes-kanban-advanced-workflow/scripts/preflight.sh
```

---

## What workers assume (don't skip)

- **Hermes dispatch** (orchestrator/worker `hermes chat`) uses **profile** model/auth — separate from the coding CLI.
- **Coding dispatch** uses `KANBAN_CODING_AGENT*` + `coding_agent_invoke.sh`; card bodies must not override `--model` / `--trust` (P005).
- **Worktree** is created by `worktree_setup.sh`; gitignored kanban paths appear only via `.worktreeinclude`.
- **Coding agent governance** forbids `pip install` / `npm install` in the agent prompt — dependencies must already exist in the worktree or host.

---

## Cross-references

- [coding-agent-auth.md](coding-agent-auth.md) — bootstrap vs gate, per-binary auth, `HOME`
- [coding-agent-cli-invocation.md](coding-agent-cli-invocation.md) — headless flags, worktree smoke
- [wiki/bootstrap.md](../../../wiki/bootstrap.md) — init steps
- [wiki/troubleshooting.md](../../../wiki/troubleshooting.md) — worktree / auth symptoms
- [limitations.md](../../../docs/reference/limitations.md) — plugin API boundaries
