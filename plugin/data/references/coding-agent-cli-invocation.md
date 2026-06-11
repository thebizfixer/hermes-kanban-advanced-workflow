# Coding-agent CLI invocation (headless / worker dispatch)

> **SSOT for workers:** `KANBAN_CODING_AGENT` selects the binary; `KANBAN_CODING_AGENT_MODEL` (`auto` or an ID) is injected at dispatch — never in the card body's fenced block (P005).

Workers run coding agents **headlessly** from the card worktree. Each CLI uses different flags for print mode, structured output, permissions, and workspace trust. Use `scripts/coding_agent_invoke.sh` so smoke tests and dispatch share one contract.

Verify installed flags with `<binary> --help` after upgrades.

## Summary table

| Binary | Headless entry | Structured output | Permissions / trust | Model flag (`auto` = omit) |
| --- | --- | --- | --- | --- |
| `agent` (Cursor) | `-p` (`--print`) | `--output-format json` (requires `-p`) | `--trust` in worktrees (requires `-p`) | `--model <id>` |
| `claude` | `-p` (`--print`) | `--output-format json` (requires `-p`) | `--dangerously-skip-permissions` or `--permission-mode bypassPermissions` | `--model <alias>` |
| `codex` | `codex exec "<prompt>"` | `--json` (JSONL on stdout) | `-a never`; use `--sandbox workspace-write` for edits | `--model <id>` |
| `grok` | `--prompt "<prompt>"` or `-p` | `--format json` (NDJSON events) | non-interactive by default; set `GROK_API_KEY` | `--model <id>` when supported |
| `gemini` | prompt as arg (headless) | `--output-format json` | `--yolo` or `--approval-mode=yolo` for walk-away runs | `--model <id>` |
| `aider` | `--message "<prompt>"` | text only (no JSON envelope) | `--yes-always` (or `--yes`) | `--model <id>` |

## Cursor CLI (`agent`) — default

**Docs:** `agent --help` — `-p` is `--print`; `--output-format` only works with `--print`; `--trust` only works with `--print`/headless.

**Smoke (from worktree):**

```bash
agent -p "say ok" --output-format json --trust
```

**Dispatch:**

```bash
agent -p "$FULL_PROMPT" --output-format json --trust
# explicit model:
agent -p "$FULL_PROMPT" --output-format json --trust --model composer-2.5
```

**JSON result (single object on stdout):** `is_error`, `usage.inputTokens`, `usage.outputTokens`, `usage.cacheReadTokens`, `duration_api_ms`, `result`.

**Common false failure:** exit 1 with `Workspace Trust Required` when `--trust` is omitted in a new worktree. `worktree_setup.sh` also writes `~/.cursor/projects/<hash>/.workspace-trusted`; still pass `--trust` on every headless call.

## Claude Code (`claude`)

**Docs:** `claude --help` — `-p` skips the workspace trust dialog in directories you trust; use `--output-format json` with `-p`.

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

**Docs:** [Non-interactive mode](https://developers.openai.com/codex/noninteractive) — use `codex exec`, not the interactive TUI.

**Smoke (read-only):**

```bash
codex exec --json -a never "say ok"
```

**Dispatch (edits allowed in worktree):**

```bash
codex exec --json --sandbox workspace-write -a never "$FULL_PROMPT"
```

**Output:** JSON Lines on stdout (`turn.completed` carries `usage`). Progress goes to stderr. For token attribution, parse the JSONL stream (last `turn.completed` or aggregate usage).

## Grok CLI (`grok`)

**Docs:** [superagent-ai/grok-cli](https://github.com/superagent-ai/grok-cli) README — headless via `--prompt` / `-p`.

**Smoke:**

```bash
grok --prompt "say ok" --format json
```

**Dispatch:**

```bash
grok --prompt "$FULL_PROMPT" --format json
```

**Output:** newline-delimited JSON events (`step_start`, `text`, `tool_use`, `step_finish`, `error`). Requires `GROK_API_KEY`.

## Gemini CLI (`gemini`)

**Docs:** [settings reference](https://geminicli.com/docs/cli/settings/) — `output.format` can be `json`; YOLO/auto-approve via `--yolo` on the CLI.

**Smoke:**

```bash
gemini --yolo --output-format json "say ok"
```

**Dispatch:**

```bash
gemini --yolo --output-format json "$FULL_PROMPT"
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
| Worker Step 3 | `coding_agent_invoke.sh smoke` | Card **worktree** after `worktree_setup.sh` |
| Worker Step 4 | `coding_agent_invoke.sh dispatch` | Same worktree; full prompt + stdout capture |

A green dashboard coding-agent dot does not replace worktree smoke — Cursor especially may pass at project root but fail in a new worktree without `--trust`.

**Smoke timeout:** Dashboard and init use **180s** (`SMOKE_TIMEOUT_SECONDS` in `plugin/coding_agent.py`). Workers should allow the same when using `terminal()` (`timeout 180 bash … smoke`). Subprocess timeout returns `model_reachable: false`, not yellow/inconclusive.

**Worker dispatch:** Hermes workers must use **`terminal()`** to run `bash "$INVOKE" dispatch …` (up to **900s**). Do not use `execute_code`. Resolve `$INVOKE` via `bundle_path` in config, then `$HERMES_HOME/plugins/kanban-advanced`, then `$HERMES_HOME/scripts/coding_agent_invoke.sh` after **Update Plugin** / `provision.sh`.
