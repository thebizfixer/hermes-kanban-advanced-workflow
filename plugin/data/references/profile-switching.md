# Hermes profile switching (upstream behavior)

Authoritative Nous docs:

- [Profile Commands Reference](https://hermes-agent.nousresearch.com/docs/reference/profile-commands)
- [Profiles user guide](https://hermes-agent.nousresearch.com/docs/user-guide/profiles)
- [Slash Commands Reference](https://hermes-agent.nousresearch.com/docs/reference/slash-commands) — `/profile` entry

## There is no in-chat profile switch

Hermes **cannot** change the active profile inside an ongoing chat session.

| Command | What it does |
| --- | --- |
| `/profile` | **Show** active profile name and home directory — does **not** switch |
| `/status` | Session info including profile name |
| `/model` | Switch **model**, not profile |

To work as **orchestrator**, the user must **start a new session** under that profile (CLI, TUI, or messaging gateway bound to that profile's process).

## List profiles (show the user a menu)

```bash
hermes profile list
```

The active profile is marked with `*` (see upstream Profile Commands Reference). Use this output verbatim when the user asks how to switch — do not invent profile names.

kanban-advanced init creates `worker` and `orchestrator` when missing; names may differ if the operator renamed them — always discover with `hermes profile list`.

## Start orchestrator chat (cross-platform)

Pick **one** — same on Linux, macOS, Windows native, and WSL:

```bash
# Explicit profile flag (always works)
hermes -p orchestrator chat

# TUI
hermes --tui -p orchestrator

# Sticky default for the shell, then chat
hermes profile use orchestrator
hermes chat

# Profile command alias (if created at profile install / init)
orchestrator chat
```

After the new session starts, the user repeats the trigger phrase (e.g. **execute the plan**). The kanban-advanced `on_session_start` hook logs orchestrator-specific skill hints when `HERMES_PROFILE=orchestrator`.

## One-shot CLI without switching chat (agent terminal_tool)

The agent may run **individual** orchestrator commands from any profile's terminal without changing the chat session:

```bash
hermes -p orchestrator kanban list
hermes -p orchestrator kanban complete <task_id>
```

`-p` / `--profile` overrides the active profile for that subprocess only ([Profile Commands Reference](https://hermes-agent.nousresearch.com/docs/reference/profile-commands)).

**Full decomposition SOP** (interactive card creation, gate management, monitoring) still belongs in an **orchestrator chat session** — not scattered one-shot CLI calls from a worker/default session.

## Agent script when user hits "execute" on the wrong profile

1. Run `hermes profile list` and include the output.
2. Say clearly: Hermes has **no** `/profile switch` — they need a **new** orchestrator session.
3. Offer the three launch patterns above (`hermes -p orchestrator chat`, `orchestrator chat` if listed, `hermes profile use orchestrator` + `hermes chat`).
4. Ask them to say **execute the plan** again in that session.

Do **not** tell the user to run `hermes -p orchestrator` alone — that is not a chat launcher; use `hermes -p orchestrator chat` or the profile alias.
