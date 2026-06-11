# Coding Agents

Any headless coding agent on PATH works. The worker extracts the prompt from the card body's fenced block and dispatches **`KANBAN_CODING_AGENT`** with **`KANBAN_CODING_AGENT_MODEL`** (from `kanban-config.yaml` / `.env` — set at init or dashboard **Save**). Use `auto` for the CLI default; the worker injects `--model` only when a specific model ID is configured.

| Binary   | Source                   | Install                                            | Headless invocation                  |
| -------- | ------------------------ | -------------------------------------------------- | ------------------------------------ |
| `agent`  | Cursor CLI               | `curl https://cursor.com/install -fsS \| bash` | `agent -p "..."`                     |
| `claude` | Claude Code              | `npm i -g @anthropic-ai/claude-code`               | `claude -p "..."`                    |
| `codex`  | OpenAI Codex             | `pip install openai-codex`                         | `codex exec "..."`                   |
| `grok`   | superagent-ai/grok-cli   | `npm i -g grok-dev`                                | `grok -p "..."`                      |
| `aider`  | Aider-AI/aider           | `pip install aider-install`                        | `aider --message "..." --yes-always` |
| `gemini` | google-gemini/gemini-cli | `npm i -g @google/gemini-cli`                      | `gemini -p "..."`                    |
