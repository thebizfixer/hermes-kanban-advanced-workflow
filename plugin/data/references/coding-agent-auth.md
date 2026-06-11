# Coding-agent authentication (headless / gateway)

> **SSOT** for operator setup, bootstrap expectations, and preflight prerequisites. Execution smoke (`check_coding_agent_cli.py`, worker Step 3) is always authoritative — status commands and credential file presence alone are not sufficient.

## Bootstrap vs pre-dispatch (what blocks what)

| When | What runs | Blocks init/bootstrap? | Blocks decomposition? |
| --- | --- | --- | --- |
| **Bootstrap** (`hermes kanban-advanced init` / dashboard **Bootstrap**) | One **advisory** headless smoke + writes `HOME`, `KANBAN_CODING_AGENT*` to `.env` | **No** — logs `! coding CLI auth/model check failed` but init can still succeed | — |
| **Save** (dashboard) | Same advisory smoke when binary on PATH | **No** | — |
| **Preflight** | `coding_agent_cli_reachability` via `check_coding_agent_cli.py` | — | **Yes** (blocking check) |
| **Pre-dispatch gate** | `check_coding_agent_cli.py` again | — | **Yes** |
| **Worker Step 3** | `coding_agent_invoke.sh smoke` from worktree | — | **Yes** (card block / E020) |

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

After changing `HOME` or credentials: delete `.hermes/kanban/preflight_cache.json` and re-run preflight.

## Worktree provisioning (`.worktreeinclude`)

Card worktrees are plain `git worktree add` checkouts — they do **not** include gitignored `.hermes/` files unless copied. Init writes **`.worktreeinclude`** at the repo root; `worktree_setup.sh` copies listed paths (scripts, `kanban-overrides`, plugin invoke `lib/`) into each worktree before the worker smoke test.

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

Hermes profile `model_reachability` (`hermes -p <profile> chat`) is a **third**, separate check for dispatch LLM backends — not the coding CLI.

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

## Related

- Headless flags: `coding-agent-cli-invocation.md`
- User reference: `docs/reference/coding-agents.md`
- Troubleshooting: `wiki/troubleshooting.md`
