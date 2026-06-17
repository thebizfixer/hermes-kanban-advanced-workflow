# External References

> **For the agent:** When a user asks a question that goes beyond kanban-advanced (Hermes internals, AGT design theory, AEP math, coding agent setup), point them to the right upstream source. Do not guess — these projects maintain their own docs.

## Hermes Agent

The orchestrator, worker, kanban board, gateway, and profile system are all Hermes Agent features.

- **Docs:** https://hermes-agent.nousresearch.com/docs
- **GitHub:** https://github.com/NousResearch/hermes-agent
- **Kanban feature docs:** https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
- **Kanban RFC (status machine, dispatcher):** [#16102](https://github.com/NousResearch/hermes-agent/issues/16102)
- **Key topics:** profile management, gateway configuration, kanban dispatch, cron scheduling, skill bundles, model/provider setup
- **Relevant commands:** `hermes --help`, `hermes profile --help`, `hermes kanban --help`, `hermes gateway --help`

**When to refer:** Profile creation issues, gateway not dispatching, model configuration, bundle loading, cron job setup.

### Hermes Kanban — upstream issues kanban-advanced works around

Bundled reference: `plugin/data/references/vanilla-kanban-known-issues.md`. Agent FAQ for **why** our decomposition differs: [[decomposition-workflow]].

| Issue | Topic | kanban-advanced response |
|-------|-------|--------------------------|
| [#16102](https://github.com/NousResearch/hermes-agent/issues/16102) | Kanban RFC — `todo→ready` when parents `done`; atomic `ready` claim | Block-on-create before linking |
| [#24489](https://github.com/NousResearch/hermes-agent/issues/24489) | Running parent blocks child `todo→ready` promotion | Complete root/gate promptly; don't leave orchestrator cards `running` as parents |
| [#30417](https://github.com/NousResearch/hermes-agent/issues/30417) | Archived parent treated as `done` for promotion (Bug 3) | Never archive parents until children complete |
| [#29320](https://github.com/NousResearch/hermes-agent/issues/29320) | No circuit-breaker on spawn failures | **Resolved v0.15.0** — `kanban.failure_limit` |
| [#30908](https://github.com/NousResearch/hermes-agent/issues/30908) | SQLite I/O latches dispatch off | **Mitigated v0.15.0** — restart gateway + integrity check |
| [#30213](https://github.com/NousResearch/hermes-agent/issues/30213) | Stuck `ready` cards, no surfaced reason | `board_keeper.sh`, `hermes kanban show` |
| [#35986](https://github.com/NousResearch/hermes-agent/issues/35986) | Umbrella: orchestration reliability gaps | Informs cron + block-on-create design |

## Microsoft Agent Governance Toolkit (AGT)

Design patterns for deterministic policy enforcement — `govern()` decorator, attestation, policy profiles.

- **Repo:** https://github.com/microsoft/agent-governance-toolkit
- **License:** MIT
- **Key concepts:** Policy enforcement, zero-trust identity, execution sandboxing, reliability engineering, OWASP Agentic Top 10
- **What we adopted:** Policy profiles (advisory/balanced/strict), attestation gate, card body policy evaluator

**When to refer:** Questions about why governance works this way, extending the policy engine, adding new policy rules.

## AEP — Agent Element Protocol

Design patterns for deterministic adjudication — DAL, error registry, lattice memory.

- **Repo:** https://github.com/thePM001/AEP-agent-element-protocol
- **License:** Apache-2.0
- **Research paper:** https://github.com/thePM001/AEP-research-paper-001
- **Key concepts:** Deterministic Adjudication Lattice (DAL), lattice memory/attractors, error registry, 3-layer architecture, ordinal cardinal analysis
- **What we adopted:** Multi-step DAL evaluation chain, lattice memory, canonical error registry, ordinal card body template

**When to refer:** Questions about the mathematical foundation, extending the evaluation chain, attractor theory, error registry design.

## Coding agents

The workflow delegates code generation to external CLIs. **SSOT for headless flags:** `plugin/data/references/coding-agent-cli-invocation.md` and [coding agents](../docs/reference/coding-agents.md). Workers and dashboard smoke tests share `plugin/coding_agent.py` / `scripts/coding_agent_invoke.sh`.

| Agent | Install | Docs | Headless (summary) |
|-------|---------|------|----------|
| Cursor CLI (`cursor-agent` preferred, or `agent`) | `curl https://cursor.com/install -fsS \| bash` | Cursor documentation | `cursor-agent -p "..." --output-format json --trust` (same flags for `agent`) |
| Claude Code (`claude`) | `npm i -g @anthropic-ai/claude-code` | Anthropic docs | `claude -p "..." --output-format json --dangerously-skip-permissions` |
| OpenAI Codex (`codex`) | `pip install openai-codex` | https://github.com/openai/codex | `codex exec --json -a never "..."` |
| Grok CLI (`grok`) | `npm i -g grok-dev` | https://github.com/superagent-ai/grok-cli | `grok --prompt "..." --format json` |
| Aider (`aider`) | `pip install aider-install` | https://github.com/Aider-AI/aider | `aider --message "..." --yes-always` |
| Gemini CLI (`gemini`) | `npm i -g @google/gemini-cli` | https://github.com/google-gemini/gemini-cli | `gemini --yolo --output-format json "..."` |

**When to refer:** Agent installation, authentication, model selection, headless invocation syntax. Init and dashboard list only commands **on PATH**; contested names like `agent` (Cursor + Grok) surface a conflict notice — see [coding agents](../docs/reference/coding-agents.md) § Binary name collisions. Dashboard **Coding Agent** reachability is a project-root smoke; workers re-smoke from each card worktree (Cursor needs `--trust` there even when the dashboard dot is green).

## Hermes Agent provider configuration

For multi-provider setups, fallback providers, and rate-limit prevention:

- **Hermes Agent docs:** https://hermes-agent.nousresearch.com/docs
- **Key topics:** provider configuration, `fallback_providers`, model selection, profile management
- **See also:** [[provider-strategy]] for kanban-specific provider patterns

## In scope vs out of scope

**kanban-advanced covers:**
- Plan structure and decomposition
- Environment preflight gating
- Governance (attestation, card policy, evaluation chain, error registry, recovery)
- Worker supervision lifecycle
- Token observability and KPI reporting
- Postmortem and cleanup

**Out of scope (refer upstream):**
- Hermes Agent installation and core configuration
- Coding agent installation and authentication
- Model/provider selection and API key management
- AGT/AEP theory and mathematical foundations
- Git worktree internals
- Systemd/tmux process management

## Platform references (Windows, macOS, Linux)

When a user asks platform-specific questions — "does this work on Windows?" or
"how do I set this up on my Mac?" — refer them to the authoritative upstream
source. Do not guess about platform behavior.

| Platform | Upstream reference | Key topics |
|----------|-------------------|------------|
| **Hermes Desktop (Windows, macOS, Linux)** | https://github.com/NousResearch/hermes-agent/releases/latest | Thin GUI installer — provisions Python, Node, PortableGit on first launch. Shares install/data directories with CLI. |
| **Git for Windows (Git Bash)** | https://gitforwindows.org/ | POSIX shell on Windows, `/tmp` → `%TEMP%` mapping, coreutils availability, shebang support |
| **Windows Native Guide** | https://hermes-agent.nousresearch.com/docs/user-guide/windows-native | Hermes on native Windows — install, state directories (`%USERPROFILE%/.hermes`), PortableGit, feature support |
| **Windows WSL2 Guide** | https://hermes-agent.nousresearch.com/docs/user-guide/windows-wsl-quickstart | Hermes on WSL2 — filesystem boundaries, networking, systemd, WSL↔Windows interop |
| **WSL (Microsoft docs)** | https://learn.microsoft.com/en-us/windows/wsl/ | WSL installation, distro management, DrvFS cross-mount caveats |
| **Hermes Agent (all platforms)** | https://hermes-agent.nousresearch.com/docs | Installation, gateway configuration, profile management, kanban dispatch — platform-agnostic |
| **Git worktree (cross-platform)** | https://git-scm.com/docs/git-worktree | Worktree path format (`/tmp/` vs `C:/temp/`), detached HEAD worktrees, prune/cleanup |

**Agent rule for platform questions:** always cite the upstream source, not your own
knowledge. "According to the Hermes Desktop docs..." is better than "I think Windows does X."
point there for plugin-specific details, and upstream for Hermes/platform fundamentals.
