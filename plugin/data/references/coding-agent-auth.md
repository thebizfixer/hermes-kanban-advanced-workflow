# Coding-agent authentication (headless / gateway)

> **SSOT** for operator setup, bootstrap expectations, and preflight prerequisites. Execution smoke (`check_coding_agent_cli.py`, worker Step 3) is always authoritative — status commands and credential file presence alone are not sufficient.

## Bootstrap vs pre-dispatch (what blocks what)

| When | What runs | Blocks init/bootstrap? | Blocks decomposition? |
| --- | --- | --- | --- |
| **Bootstrap** (`hermes kanban-advanced init` / dashboard **Bootstrap**) | One **advisory** headless smoke + writes `HOME`, `KANBAN_CODING_AGENT*` to `.env` | **No** — logs `! coding CLI auth/model check failed` but init can still succeed | — |
| **Save** (dashboard) | Same advisory smoke when binary on PATH | **No** | — |
| **Preflight** | `coding_agent_cli_reachability` via `check_coding_agent_cli.py` | — | **Yes** (blocking check) |
| **Pre-dispatch gate** | `check_coding_agent_cli.py` again | — | **Yes** |
| **Worker Step 3** | `coding_agent_invoke.sh smoke` from worktree — **handshake** (`agent -p "hello" --trust`) when `.hermes/kanban/preflight_cache.json` is fresh (< 30 min); full smoke otherwise | — | **Yes** (card block / E020) |

### What bootstrap does **not** do

- **Does not write vendor API keys** (`GROK_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, …). You must add those to project `.env` yourself, or complete vendor OAuth login on the gateway host.
- **Does not guarantee gateway workers inherit auth** — bootstrap writes `HOME=` to `.env`, but systemd gateways with `SetLoginEnvironment=no` may still need `Environment=HOME=...` on the unit unless Hermes loads project `.env` after restart.
- **Does not replace pre-dispatch** — a green bootstrap log line is not permission to decompose if preflight fails later.

### Operator assumption (supported model)

You choose **one** headless CLI (`coding_agent_binary`) and authenticate it **either**:

1. **API key in `.env`** (grok, codex, claude headless, gemini, aider), or  
2. **OAuth / login on the gateway host** (Cursor `agent login`, `claude login`, `codex login`, gemini login).

Bootstrap smoke only **warns** if that assumption is not met yet. **Preflight + gate** enforce it before cards are created.

### Agent: user reports coding-binary auth trouble

Load this file and [wiki/troubleshooting.md](../../../wiki/troubleshooting.md). Run in order:

```bash
# 1. Confirm configured binary and HOME (after: source .env)
grep -E '^(KANBAN_CODING_AGENT|HOME)=' .env
PYTHONPATH=. python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py --prerequisites-only

# 2. Execution smoke (blocking gate uses this)
PYTHONPATH=. python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py

# 3. If preflight cached a stale pass
rm -f .hermes/kanban/preflight_cache.json
bash hermes-kanban-advanced-workflow/scripts/preflight.sh | python3 -m json.tool
```

Then apply the per-binary fix from the table below. Do **not** treat bootstrap `! coding CLI` as the final word — re-run the gate after fixing credentials.

## Universal rule: set `HOME`

Many CLIs store OAuth or API session files under `$HOME`. Hermes gateway units with `SetLoginEnvironment=no` may **not** pass `HOME` to workers.

| Symptom | Cause |
| --- | --- |
| `HOME: unbound variable` (Cursor agent) | Agent wrapper uses `set -u` and `${HOME}/.config/cursor` |
| `agent status` OK but `agent -p` fails | Often missing `HOME`, not expired OAuth |
| Misleading `[escalation:coding_agent:auth]` | Worker smoke without `HOME` looks like auth failure |

**Fix (pick one):**

1. `hermes kanban-advanced init` / dashboard **Save** — writes `HOME=` to project `.env`
2. Gateway systemd unit: `Environment="HOME=/home/youruser"`
3. Worker / invoke script: `scripts/lib/coding_agent_env.sh` (sourced by `coding_agent_invoke.sh`)

After re-auth: delete `.hermes/kanban/preflight_cache.json` and re-run preflight / gate. Gate success writes the cache via `check_coding_agent_cli.py`.

## Worktree provisioning (`.worktreeinclude`)

Card worktrees start as `git worktree add` checkouts — they do **not** include gitignored `.hermes/` files unless copied. Init writes **`.worktreeinclude`** at the repo root; **`worktree_setup.sh`** (governed path — not raw `git worktree add` alone) copies listed paths (scripts, `kanban-overrides`, plugin invoke `lib/`) into each worktree before the worker smoke test. Workers block at **E021** when worktree-local `.hermes/scripts/coding_agent_invoke.sh` is missing.

If smoke works at project root but fails in the worktree with exit 127 on `coding_agent_invoke.sh`, re-run init / **Update Plugin** and confirm `.worktreeinclude` is committed.

**Application `.env` / venvs:** The plugin does not add `.env` or `.venv/` to `.worktreeinclude`. See [operator-provisioning.md](operator-provisioning.md) for what operators must supply based on what they run through kanban.

## Per-binary auth (verified against vendor docs)

| Binary | Headless auth | Credential location / env | CI / automation best practice |
| --- | --- | --- | --- |
| `agent` (Cursor) | OAuth | `$HOME/.config/cursor/auth.json` | `agent login` on gateway host; use `-p --trust` for worktrees; **not** `CURSOR_API_KEY` |
| `claude` | API key, bearer token, or OAuth | `~/.claude/.credentials.json` or `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN` | Non-interactive `-p`: set `ANTHROPIC_API_KEY` or `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` ([Claude Code auth](https://code.claude.com/docs/en/authentication)) |
| `codex` | API key or saved login | `~/.codex/auth.json` or `CODEX_API_KEY` / `OPENAI_API_KEY` | `codex exec` in CI: `CODEX_API_KEY` secret ([Codex non-interactive](https://developers.openai.com/codex/noninteractive)) |
| `grok` | API key | `GROK_API_KEY` | Export key in `.env` / gateway env |
| `gemini` | Google login cache or API key | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Headless: API key or pre-cached login on gateway ([Gemini CLI auth](https://google-gemini.github.io/gemini-cli/docs/get-started/authentication.html)) |
| `aider` | Provider API keys | `.aider.conf` / `.env` per provider | Configure model provider keys before dispatch |

## Plugin checks (two layers)

1. **Prerequisites** (`audit_coding_agent_prerequisites`) — fast fail: `HOME`, missing key/file for configured binary
2. **Execution smoke** (`smoke_test_coding_agent` / `coding_agent_invoke.sh smoke`) — proves headless one-line prompt works

Hermes profile `model_reachability` (`hermes -p <profile> chat`) is a **third**, separate check for dispatch LLM backends — not the coding CLI. Dashboard profile badges label failures **model unreachable** (with optional `model_reachability_detail`: `provider auth failed`, `model not found`, etc.) — do not confuse with `coding_agent_cli.model_reachable` (**auth/model failed** on the external coding binary).

## Gateway operator checklist

```bash
# 1. HOME present for workers
echo "HOME=${HOME:-MISSING}"

# 2. Configured binary smoke (from repo root, after sourcing .env)
set -a && source .env && set +a
PYTHONPATH=. python3 scripts/check_coding_agent_cli.py

# 3. Worktree smoke (after worktree_setup)
cd <worktree>
bash ../hermes-kanban-advanced-workflow/scripts/coding_agent_invoke.sh smoke
```

## Concurrent OAuth refresh race (Cursor `agent`)

**Symptom:** `check_coding_agent_cli.py` passes once, but parallel workers intermittently fail with `[escalation:coding_agent:auth]` or `Authentication required` on some cards only.

**Cause:** Multiple workers call `coding_agent_invoke.sh` concurrently; each may refresh `~/.config/cursor/auth.json` at the same time.

**Fix (plugin):** All Cursor `agent` invocations are serialized with `flock` on `$HERMES_HOME/.locks/coding-agent-auth.lock` (120s wait). Smoke probes in `plugin/coding_agent.py` use the same lock.

**Operator check:**

```bash
ls -la "${HERMES_HOME:-$HOME/.hermes}/.locks/coding-agent-auth.lock"
# After parallel dispatch: only one holder at a time; waiters queue
```

**Notes:**

- Requires `flock` on the gateway host (WSL/Linux). NFS lock files are unreliable — keep `HERMES_HOME` and `~/.config/cursor` on local disk.
- One smoke retry after auth failure may succeed if a peer refreshed credentials.
- Complements (does not replace) `pre_dispatch_gate` pre-warm smoke before decomposition.

### Pre-warm before decomposition (Option A)

`pre_dispatch_gate.sh` calls `prewarm_coding_agent_auth()` after other checks pass — one serialized `agent -p "echo ok" --trust` under the flock so parallel workers read a fresh `auth.json` instead of racing refresh. When `KANBAN_CODING_AGENT=agent`, pre-warm is **blocking** (FAIL stops decomposition). Other coding binaries keep pre-warm as WARN-only.

`auto_unblock.sh` may pre-warm once per tick when `KANBAN_PREWARM_ON_UNBLOCK=1` (default). Use `--stagger-sec 30` (or `KANBAN_UNBLOCK_STAGGER_SEC`) when releasing parallel wave-1 cards.

**Operator check:**

```bash
bash hermes-kanban-advanced-workflow/scripts/pre_dispatch_gate.sh <plan_id>
# Expect: [GATE] coding_agent_auth_prewarm ... PASS when KANBAN_CODING_AGENT=agent
```

## Worktree script bootstrap (chicken-and-egg)

Workers must invoke `worktree_setup.sh` by **absolute path** from the main checkout or `$HERMES_HOME/scripts/` — not a cwd-relative `hermes-kanban-advanced-workflow/scripts/...` path inside an empty worktree.

Init / **Update Plugin** materializes `worktree_setup.sh` (+ hook installers and `lib/kanban_bundle.sh`) to `$HERMES_HOME/scripts/`. `worktree_setup.sh` then copies `.worktreeinclude` paths from the **main repo** into each card worktree before smoke tests.

If workers report missing `worktree_setup.sh` or exit 127: re-run **Bootstrap** / **Update Plugin**, restart gateway, confirm `.worktreeinclude` is committed.

## Related

- Headless flags: `coding-agent-cli-invocation.md`
- User reference: `docs/reference/coding-agents.md`
- Troubleshooting: `wiki/troubleshooting.md`
