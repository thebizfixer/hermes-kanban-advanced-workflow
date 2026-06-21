# Coding-agent CLI invocation (headless / worker dispatch)

> **SSOT for workers:** `KANBAN_CODING_AGENT` selects the binary; `KANBAN_CODING_AGENT_MODEL` (`auto` or an ID) is injected at dispatch — never in the card body's fenced block (P005).

Workers run coding agents **headlessly** from the card worktree. Each CLI uses different flags for print mode, structured output, permissions, and workspace trust. Use `scripts/coding_agent_invoke.sh` so smoke tests and dispatch share one contract.

Verify installed flags with `<binary> --help` after upgrades. `plugin/coding_agent.py` and `coding_agent_invoke.sh` pick Grok headless flags from `--help` when both xAI Grok Build and superagent `grok-cli` may register as `grok`.

## Summary table

| Binary | Headless entry | Structured output | Permissions / trust | Model flag (`auto` = omit) |
| --- | --- | --- | --- | --- |
| `cursor-agent` or `agent` (Cursor) | `-p` (`--print`) | `--output-format json` (requires `-p`) | `--trust` in worktrees (requires `-p`) | `--model <id>` |
| `claude` | `-p` (`--print`) | `--output-format json` (requires `-p`) | `--dangerously-skip-permissions` or `--permission-mode bypassPermissions` | `--model <alias>` |
| `codex` | `codex exec "<prompt>"` | `--json` (JSONL on stdout) | smoke: `--sandbox read-only`; dispatch: `--sandbox workspace-write`; `-a never` | `--model <id>` |
| `grok` | xAI: `-p` / `--single`; superagent: `--prompt` | xAI: `--output-format json`; superagent: `--format json` | xAI: `--always-approve` | `--model <id>` when supported |
| `gemini` | `-p` / `--prompt` | `--output-format json` | `--yolo` or `--approval-mode=yolo` for walk-away runs | `--model <id>` |
| `aider` | `--message "<prompt>"` | text only (no JSON envelope) | `--yes-always` (or `--yes`) | `--model <id>` |
| `hermes` | `chat -q "<prompt>"` | text only (no JSON envelope) | `--yolo` | `--model <id>` |

## Cursor CLI (`cursor-agent` or `agent`)

Prefer **`cursor-agent`** on PATH when both Cursor and other tools may register `agent`. `coding_agent_invoke.sh` and `plugin/coding_agent.py` treat `cursor-agent` and `agent` identically for smoke/dispatch when configured.

**Docs:** `cursor-agent --help` or `agent --help` — `-p` is `--print`; `--output-format` only works with `--print`; `--trust` only works with `--print`/headless.

**Smoke (from worktree):**

```bash
cursor-agent -p "say ok" --output-format json --trust
# or when configured as agent:
agent -p "say ok" --output-format json --trust
```

**Dispatch:**

```bash
cursor-agent -p "$FULL_PROMPT" --output-format json --trust
# explicit model:
cursor-agent -p "$FULL_PROMPT" --output-format json --trust --model composer-2.5
```

**JSON result (single object on stdout):** `is_error`, `usage.inputTokens`, `usage.outputTokens`, `usage.cacheReadTokens`, `duration_api_ms`, `result`.

**Common false failure:** exit 1 with `Workspace Trust Required` when `--trust` is omitted in a new worktree. `worktree_setup.sh` also writes `~/.cursor/projects/<hash>/.workspace-trusted`; still pass `--trust` on every headless call.

## Claude Code (`claude`)

**Docs:** [Headless / Agent SDK CLI](https://code.claude.com/docs/en/headless) — `-p` skips the workspace trust dialog in directories you trust; use `--output-format json` with `-p`.

**Smoke:**

```bash
claude -p "say ok" --output-format json --dangerously-skip-permissions
```

**Dispatch:**

```bash
claude -p "$FULL_PROMPT" --output-format json --dangerously-skip-permissions
```

Parse JSON for `is_error` / result when present; otherwise treat exit 0 + stdout as success.

## OpenAI Codex (`codex`)

**Docs:** [Non-interactive mode](https://developers.openai.com/codex/noninteractive) — use `codex exec`, not the interactive TUI. Default sandbox is read-only; pass `--sandbox workspace-write` when the worker must edit files.

**Smoke (read-only):**

```bash
codex exec --json -a never --sandbox read-only "say ok"
```

**Dispatch (edits allowed in worktree):**

```bash
codex exec --json --sandbox workspace-write -a never "$FULL_PROMPT"
```

**Output:** JSON Lines on stdout (`turn.completed` carries `usage`). Progress goes to stderr. For token attribution, parse the JSONL stream (last `turn.completed` or aggregate usage).

## Grok CLI (`grok`)

Two different packages can install a `grok` command. The plugin detects flavor from `grok --help`:

| Flavor | Install | Headless flags |
| --- | --- | --- |
| **xAI Grok Build** | xAI Grok CLI / `grok-dev` | `-p` or `--single`, `--output-format json`, `--always-approve` |
| **superagent grok-cli** | `npm i -g grok-dev` (community) | `--prompt`, `--format json` |

**Docs:** [xAI headless & scripting](https://docs.x.ai/build/cli/headless-scripting); [superagent-ai/grok-cli](https://github.com/superagent-ai/grok-cli).

**Smoke (xAI Grok Build):**

```bash
grok -p "say ok" --output-format json --always-approve
```

**Smoke (superagent grok-cli):**

```bash
grok --prompt "say ok" --format json
```

**Output:** xAI supports `json` or `streaming-json`; superagent emits newline-delimited JSON events. Requires `GROK_API_KEY`.

## Gemini CLI (`gemini`)

**Docs:** [Headless mode](https://geminicli.com/docs/cli/headless/) — non-TTY or `-p` / `--prompt` triggers headless; `--output-format json` for structured output.

**Smoke:**

```bash
gemini -p "say ok" --yolo --output-format json
```

**Dispatch:**

```bash
gemini -p "$FULL_PROMPT" --yolo --output-format json
```

Use `--sandbox` when you want tool isolation. Folder trust is configured under `security.folderTrust` in settings.

## Aider (`aider`)

**Docs:** [Scripting aider](https://aider.chat/docs/scripting.html) — `--message` runs one instruction and exits.

**Smoke:**

```bash
aider --message "say ok" --yes-always --no-git
```

**Dispatch:**

```bash
aider --message "$FULL_PROMPT" --yes-always
```

**Output:** human-readable text only. Token extraction falls back to estimates (E020 path) unless you add a separate metering hook.

## Hermes Agent (`hermes`)

**Docs:** [Hermes Agent CLI](https://hermes-agent.nousresearch.com/docs/) — `hermes chat -q` runs a single query non-interactively; `--yolo` skips dangerous-command approval prompts.

**Smoke:**

```bash
hermes chat -q "say ok" --yolo
```

**Dispatch:**

```bash
hermes chat -q "$FULL_PROMPT" --yolo
```

**Output:** human-readable text only. Token extraction falls back to estimates (E020 path) unless you add a separate metering hook.

**Auth:** Uses the Hermes profile's own provider config — no separate CLI login needed.

## Shell helper

From the worktree (after `worktree_setup.sh`):

```bash
# Smoke
bash hermes-kanban-advanced-workflow/scripts/coding_agent_invoke.sh smoke

# Dispatch (stdout captured by worker)
bash hermes-kanban-advanced-workflow/scripts/coding_agent_invoke.sh dispatch "$FULL_PROMPT" \
  > "${KANBAN_TEMP:-${TMPDIR:-/tmp}}/agent_output_${HERMES_KANBAN_TASK}.json"
```

## Plugin / dashboard smoke

`hermes kanban-advanced init`, dashboard **Save**, and `coding_agent_cli.model_reachable` (when `probe=1`) use the same per-binary argv builders in `plugin/coding_agent.py` (`build_smoke_argv`).

| Layer | What it checks | Where it runs |
| --- | --- | --- |
| Dashboard **Coding Agent** dot | External CLI smoke (`say ok`) | Project root / API process |
| Dashboard **profile** dots | Hermes LLM backend (`hermes chat -q "say ok"`) | Hermes profile config — **not** the coding CLI |
| Preflight / pre-dispatch gate | `check_coding_agent_cli.py` — product identity (`binary --version`) then smoke (**15s** default fast smoke, single plain `--trust` probe for Cursor; use `--full` for 180s dashboard parity) | Project root before decomposition |
| Worker Step 3 | `coding_agent_invoke.sh smoke` | Card **worktree** after `worktree_setup.sh` |
| Worker Step 4 | `coding_agent_invoke.sh dispatch` | Same worktree; full prompt + stdout capture |

A green dashboard coding-agent dot does not replace worktree smoke — Cursor especially may pass at project root but fail in a new worktree without `--trust`.

**Smoke timeout:** Dashboard and init use **180s** (`SMOKE_TIMEOUT_SECONDS` in `plugin/coding_agent.py`). Workers should allow the same when using `terminal()` (`timeout 180 bash … smoke`). Subprocess timeout returns `model_reachable: false`, not yellow/inconclusive.

**Worker dispatch:** Hermes workers must use **`terminal()`** to run `bash "$INVOKE" dispatch …` (up to **900s**). Do not use `execute_code`. Resolve `$INVOKE` via `bundle_path` in config, then `$HERMES_HOME/plugins/kanban-advanced`, then `$HERMES_HOME/scripts/coding_agent_invoke.sh` after **Update Plugin** / `provision.sh`.

## Parity: `coding_agent_invoke.sh` vs `plugin/coding_agent.py`

Dashboard smoke and worker dispatch use **different entry points** that must stay aligned:

| Binary | `coding_agent_invoke.sh` | `plugin/coding_agent.py` (`ADAPTERS`) |
| --- | --- | --- |
| `agent` / `cursor-agent` | `-p`, `--output-format json`, `--trust` | `extra_smoke_argv` same |
| `claude` | `--dangerously-skip-permissions` | same |
| `codex` | `exec --json -a never`; dispatch `--sandbox workspace-write` | `exec_argv`, `dispatch_argv` same |
| `grok` | `--help`-detected xAI vs superagent flags | `detect_grok_cli_flavor()` + same branches |
| `gemini` | `--yolo --output-format json` | `extra_smoke_argv` same |
| `aider` | `--yes-always`; smoke `--no-git` | same |
| `hermes` | `--yolo` | `extra_smoke_argv` same |

Regression: `tests/test_coding_agent_parity.py` greps both files for these flag tokens. After CLI upgrades, update **both** paths and re-run `python3 scripts/check_coding_agent_cli.py`.
