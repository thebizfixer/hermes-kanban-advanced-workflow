# Coding Agents

Any headless coding agent on PATH works. The worker extracts the **prompt** from the card body's fenced block and dispatches using project env — not the literal `agent` string in the card template.

| Env var | Source | Purpose |
| --- | --- | --- |
| `KANBAN_CODING_AGENT` | `coding_agent_binary` in `kanban-config.yaml` / `.env` | CLI binary name (`agent`, `claude`, …) |
| `KANBAN_CODING_AGENT_MODEL` | `coding_agent_model` in `kanban-config.yaml` / `.env` | Model ID for that CLI, or `auto` for the CLI default |

Set both at **init** (CLI step 1c / 1c-ii) or dashboard **Bootstrap** / **Save**. The dashboard **Coding Agent** card shows a reachability dot for the CLI (same pattern as Hermes dispatch profiles). Use **`auto`** when you want the tool's own default model.

**Card bodies must not include `--model`.** Policy P005 blocks model overrides in fenced blocks when the assignee Hermes profile has model config. The worker injects `--model` from `KANBAN_CODING_AGENT_MODEL` at dispatch time when the value is not `auto`.

## SSOT invocation reference

Per-binary headless flags, structured output, and trust/permissions are documented in:

[`plugin/data/references/coding-agent-cli-invocation.md`](../../plugin/data/references/coding-agent-cli-invocation.md)

Workers and smoke tests should call:

```bash
bash hermes-kanban-advanced-workflow/scripts/coding_agent_invoke.sh smoke
bash hermes-kanban-advanced-workflow/scripts/coding_agent_invoke.sh dispatch "$FULL_PROMPT"
```

## Supported binaries

| Binary | Source | Install | Headless invocation | Structured output | Permissions / trust |
| --- | --- | --- | --- | --- | --- |
| `agent` | Cursor CLI | `curl https://cursor.com/install -fsS \| bash` | `agent -p "..."` | `--output-format json` (with `-p`) | `--trust` (with `-p`, required in worktrees) |
| `claude` | Claude Code | `npm i -g @anthropic-ai/claude-code` | `claude -p "..."` | `--output-format json` (with `-p`) | `--dangerously-skip-permissions` |
| `codex` | OpenAI Codex | `pip install openai-codex` | `codex exec "..."` | `--json` (JSONL) | `-a never`; `--sandbox workspace-write` for edits |
| `grok` | superagent-ai/grok-cli | `npm i -g grok-dev` | `grok --prompt "..."` | `--format json` (NDJSON) | `GROK_API_KEY` |
| `aider` | Aider-AI/aider | `pip install aider-install` | `aider --message "..."` | text only | `--yes-always` |
| `gemini` | google-gemini/gemini-cli | `npm i -g @google/gemini-cli` | `gemini --yolo "..."` | `--output-format json` | `--yolo` / `--approval-mode=yolo` |

Model flag when not `auto`: `--model <id>` (all supported binaries).

Implementation: [`plugin/coding_agent.py`](../../plugin/coding_agent.py) (`build_smoke_argv`, `build_dispatch_argv`, `smoke_test_coding_agent`). Tests: [`tests/test_coding_agent.py`](../../tests/test_coding_agent.py).

## Bootstrap vs blocking auth (read this first)

| Stage | Smoke? | Blocks? |
| --- | --- | --- |
| `hermes kanban-advanced init` / dashboard **Bootstrap** | Yes — one advisory run | **No** — warns with `! coding CLI auth/model check failed` |
| Dashboard **Save** | Yes — when probing | **No** |
| Preflight + `pre_dispatch_gate.sh` | Yes — `check_coding_agent_cli.py` | **Yes** — decomposition blocked |
| Worker Step 3 (worktree) | Yes — `coding_agent_invoke.sh smoke` | **Yes** — card blocked |

Bootstrap writes `KANBAN_CODING_AGENT`, `KANBAN_CODING_AGENT_MODEL`, and `HOME` to `.env`. It does **not** add vendor API keys — you must put keys in `.env` or run vendor login (`agent login`, `claude login`, …) on the gateway host **before** execute.

**Agent routing:** user auth trouble → [`plugin/data/references/coding-agent-auth.md`](../../plugin/data/references/coding-agent-auth.md) § *Agent: user reports coding-binary auth trouble*.

## Auth gate (preflight / pre-dispatch)

Before decomposition, `preflight.sh` runs `coding_agent_cli_reachability` and `pre_dispatch_gate.sh` runs `check_coding_agent_cli.py`. Both smoke the **configured** binary from `coding_agent_binary` / `KANBAN_CODING_AGENT` — not hardcoded to Cursor.

**Always set `HOME`:** Gateway workers without `HOME` cannot load OAuth files (Cursor, Claude, Codex). Init and dashboard **Save** write `HOME=` to `.env`; `coding_agent_invoke.sh` also sources `scripts/lib/coding_agent_env.sh`.

Per-binary auth SSOT: [`plugin/data/references/coding-agent-auth.md`](../../plugin/data/references/coding-agent-auth.md).

```bash
PYTHONPATH=. python3 hermes-kanban-advanced-workflow/scripts/check_coding_agent_cli.py
```

This is **separate** from Hermes profile `model_reachability` (`hermes -p <profile> chat`). Workers still re-smoke from each worktree in Step 3.

| Failure | Typical fix |
| --- | --- |
| Cursor (`agent`) auth / timeout | `agent login` — `agent status` can show logged in with stale OAuth |
| `claude` | `claude login` or API key |
| `codex` | Codex login or `OPENAI_API_KEY` |
| `grok` | `GROK_API_KEY` |
| Slow cold start | `PREFLIGHT_CODING_AGENT_PROBE_TIMEOUT=120` or `check_coding_agent_cli.py --full` |

After re-auth: delete `.hermes/kanban/preflight_cache.json`. See [wiki/troubleshooting.md](../../wiki/troubleshooting.md).

## Cursor CLI (`agent`) — recommended default

**List models:**

```bash
agent --list-models
```

**Smoke test (what init / Save runs):**

```bash
agent -p "say ok" --output-format json --trust
```

**Dispatch:**

```bash
agent -p "$FULL_PROMPT" --output-format json --trust
```

**JSON result:** single object with `is_error`, `usage.inputTokens`, `usage.outputTokens`, `duration_api_ms`, `result`.

**Common failure:** exit 1 with `Workspace Trust Required` when `--trust` is omitted in a new worktree. `worktree_setup.sh` pre-provisions trust files; workers still pass `--trust` on every headless call.

On Windows, `agent` may resolve to `agent.CMD` in `%LOCALAPPDATA%\cursor-agent\`; the plugin resolves PATH shims before subprocess calls.

## Claude Code (`claude`)

```bash
claude -p "say ok" --output-format json --dangerously-skip-permissions
```

`-p` skips the workspace trust dialog in trusted directories. Parse JSON `is_error` when present.

## OpenAI Codex (`codex`)

```bash
codex exec --json -a never "say ok"
codex exec --json --sandbox workspace-write -a never "$FULL_PROMPT"
```

Stdout is JSONL (`turn.completed` carries usage). Progress logs on stderr.

## Grok CLI (`grok`)

```bash
grok --prompt "say ok" --format json
```

Requires `GROK_API_KEY`. Output is newline-delimited JSON events.

## Gemini CLI (`gemini`)

```bash
gemini --yolo --output-format json "say ok"
```

Use `--sandbox` when you want tool isolation. Folder trust is configured in Gemini settings (`security.folderTrust`).

## Aider (`aider`)

```bash
aider --message "say ok" --yes-always --no-git
```

Text output only — token attribution uses estimates unless you add a separate metering hook.

## CLI init prompts

`hermes kanban-advanced init` step **1c** — pick binary (1–6 or custom name). Step **1c-ii** — pick model from a numbered list (Cursor: live list from `agent --list-models`; other binaries: curated defaults). Init runs a smoke test when the binary is on PATH and logs reachable / auth failed / inconclusive.

Re-init **preserves** `coding_agent_model` unless you use `--force` or answer the model prompt again on first-time setup.

## Dashboard

**Kanban-Advanced** tab → **Coding Agent**:

1. **Binary on PATH** — dropdown (or custom name).
2. **Model** — click the row to open the picker (`GET /api/plugins/kanban-advanced/coding-agent/models?binary=<name>`).
3. **Save** or **Bootstrap** — writes YAML + `.env`, reconciles profiles, runs smoke.

Status field `coding_agent_cli.model_reachable` is filled on the slow status path (`probe=1`). **Save** and **Bootstrap** also smoke the coding CLI when the binary is on PATH. This is separate from `profiles.*.model_reachable`, which pings the **Hermes** LLM backend for dispatch profiles.

Dashboard smoke runs from **project root**. Workers re-smoke from each **worktree** (Step 3) — a green dashboard dot does not skip worktree smoke.

## Worker dispatch (runtime)

From `kanban-worker` SKILL Step 3–4 — use the shared invoke script (reads `KANBAN_CODING_AGENT` / `KANBAN_CODING_AGENT_MODEL`):

```bash
# Step 3 — smoke from worktree
bash hermes-kanban-advanced-workflow/scripts/coding_agent_invoke.sh smoke

# Step 4 — dispatch after building FULL_PROMPT
AGENT_OUTPUT=$(bash hermes-kanban-advanced-workflow/scripts/coding_agent_invoke.sh dispatch "$FULL_PROMPT" 2>&1)
echo "$AGENT_OUTPUT" > "${KANBAN_TEMP:-${TMPDIR:-/tmp}}/agent_output_${HERMES_KANBAN_TASK}.json"
```

Do **not** put `--model` or `--output-format` in the card body's fenced block — the worker injects those from config at dispatch time (P005).

See also: [configuration.md](configuration.md), [wiki/configuration.md](../../wiki/configuration.md), [dashboard/API.md](../../dashboard/API.md).
