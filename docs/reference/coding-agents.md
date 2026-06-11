# Coding Agents

Any headless coding agent on PATH works. The worker extracts the **prompt** from the card body's fenced block and dispatches using project env — not the literal `agent` string in the card template.

| Env var | Source | Purpose |
| --- | --- | --- |
| `KANBAN_CODING_AGENT` | `coding_agent_binary` in `kanban-config.yaml` / `.env` | CLI binary name (`agent`, `claude`, …) |
| `KANBAN_CODING_AGENT_MODEL` | `coding_agent_model` in `kanban-config.yaml` / `.env` | Model ID for that CLI, or `auto` for the CLI default |

Set both at **init** (CLI step 1c / 1c-ii) or dashboard **Bootstrap** / **Save**. The dashboard **Coding Agent** card shows a reachability dot for the CLI (same pattern as Hermes dispatch profiles). Use **`auto`** when you want the tool's own default model.

**Card bodies must not include `--model`.** Policy P005 blocks model overrides in fenced blocks when the assignee Hermes profile has model config. The worker injects `--model` from `KANBAN_CODING_AGENT_MODEL` at dispatch time when the value is not `auto`.

## Supported binaries

| Binary   | Source                   | Install                                            | Headless invocation                  | Model flag (when not `auto`) |
| -------- | ------------------------ | -------------------------------------------------- | ------------------------------------ | ---------------------------- |
| `agent`  | Cursor CLI               | `curl https://cursor.com/install -fsS \| bash` | `agent -p "..."`                     | `--model <id>` (`agent --list-models`) |
| `claude` | Claude Code              | `npm i -g @anthropic-ai/claude-code`               | `claude -p "..."`                    | `--model <alias or full name>` |
| `codex`  | OpenAI Codex             | `pip install openai-codex`                         | `codex exec "..."`                   | `--model <id>` |
| `grok`   | superagent-ai/grok-cli   | `npm i -g grok-dev`                                | `grok -p "..."`                      | `--model <id>` (when supported) |
| `aider`  | Aider-AI/aider           | `pip install aider-install`                        | `aider --message "..." --yes-always` | `--model <id>` |
| `gemini` | google-gemini/gemini-cli | `npm i -g @google/gemini-cli`                      | `gemini -p "..."`                    | `--model <id>` |

Implementation: [`plugin/coding_agent.py`](../../plugin/coding_agent.py) (adapters, list-models, smoke test). Tests: [`tests/test_coding_agent.py`](../../tests/test_coding_agent.py).

## Cursor CLI (`agent`) — recommended default

**List models:**

```bash
agent --list-models
```

**Smoke test (what init / Save runs):**

```bash
agent -p "say ok" --output-format json --trust
# with explicit model:
agent -p "say ok" --model composer-2.5 --output-format json --trust
```

On Windows, `agent` may resolve to `agent.CMD` in `%LOCALAPPDATA%\cursor-agent\`; the plugin resolves PATH shims before subprocess calls.

## CLI init prompts

`hermes kanban-advanced init` step **1c** — pick binary (1–6 or custom name). Step **1c-ii** — pick model from a numbered list (Cursor: live list from `agent --list-models`; other binaries: curated defaults). Init runs a smoke test when the binary is on PATH and logs reachable / auth failed / inconclusive.

Re-init **preserves** `coding_agent_model` unless you use `--force` or answer the model prompt again on first-time setup.

## Dashboard

**Kanban-Advanced** tab → **Coding Agent**:

1. **Binary on PATH** — dropdown (or custom name).
2. **Model** — click the row to open the picker (`GET /api/plugins/kanban-advanced/coding-agent/models?binary=<name>`).
3. **Save** or **Bootstrap** — writes YAML + `.env`, reconciles profiles, runs smoke.

Status field `coding_agent_cli.model_reachable` is filled on the slow status path (`probe=1`), like Hermes profile model pings.

## Worker dispatch (runtime)

From `kanban-worker` SKILL Step 4 — prompt extraction unchanged; command built from env:

```bash
CODING_AGENT="${KANBAN_CODING_AGENT:-agent}"
CODING_MODEL="${KANBAN_CODING_AGENT_MODEL:-auto}"
if [ "$CODING_MODEL" = "auto" ] || [ "$CODING_MODEL" = "default" ] || [ -z "$CODING_MODEL" ]; then
  "$CODING_AGENT" -p "$FULL_PROMPT" --output-format json
else
  "$CODING_AGENT" -p "$FULL_PROMPT" --model "$CODING_MODEL" --output-format json
fi
```

See also: [configuration.md](configuration.md), [wiki/configuration.md](../../wiki/configuration.md), [dashboard/API.md](../../dashboard/API.md).
