# Your first governed plan

**Tutorial** — A guided walkthrough of the complete kanban-advanced lifecycle. Have your agent guide you through this and by the end you will have built a real tool you can use every day: a kanban board health dashboard that surfaces stalled cards, tracks token burn, and flags orphaned worktrees.

> **For the agent guiding this tutorial:** You are the tutor. Each step shows what the user says and what you say in response. Show expected output. Flag common mistakes before they happen. Link to reference docs for deeper explanation. Keep the user moving forward.

---

## Step 1: Install the plugin

**You run:**

```bash
hermes plugins install thebizfixer/hermes-kanban-advanced-workflow
```

Expected output:

```
Installing plugin from thebizfixer/hermes-kanban-advanced-workflow...
Cloning into ~/.hermes/plugins/kanban-advanced...
Plugin kanban-advanced v1.0.0 installed.
```

Restart Hermes.

> **If the install fails:** Check that GitHub is reachable. Fallback: `git clone https://github.com/thebizfixer/hermes-kanban-advanced-workflow.git ~/.hermes/plugins/kanban-advanced/`

**Agent says:**

> "Run this command to install the plugin. After it finishes, restart Hermes. Once restarted, run `hermes plugins list` — you should see `kanban-advanced` in the list."

---

## Step 2: Bootstrap your project

Bootstrap creates dispatch profiles, config, scripts, and verifies profile SOUL/skills in one step. You do **not** create profiles manually.

**You run:**

```bash
cd your-project
hermes kanban-advanced init --project-root . --working-branch main
```

Replace `main` with your integration branch.

Expected output (abbreviated):

```text
HERMES_HOME: /path/to/your-project/.hermes
OK Created 'kanban-advanced-worker' (no default skills)
OK Created 'kanban-advanced-orchestrator' (no default skills)
OK kanban-advanced-worker: SOUL.md <- worker.md (.../profiles/kanban-advanced-worker)
OK kanban-advanced-worker: 3 skills seeded [...]
OK kanban-advanced-orchestrator: 9 skills seeded [...]
OK Profiles verified: kanban-advanced-worker, kanban-advanced-orchestrator (role skills only)
```

Init copies **Hermes profile** model config from your default profile when missing. Init also asks for the **coding agent command on PATH** and model (step 1c / 1c-ii) — only detected supported commands appear in the numbered list; stored as `coding_agent_binary` / `coding_agent_model` and synced to `.env`. Use `auto` for the CLI default model. See [coding agents](../docs/reference/coding-agents.md) § Binary name collisions if you use a shared name like `agent`.

To set Hermes dispatch profile models explicitly:

```bash
hermes -p kanban-advanced-worker config set model.default <your-model>
hermes -p kanban-advanced-worker config set model.provider <your-provider>
```

**Agent says:**

> "Navigate to your project and run init (or use dashboard **Bootstrap**). What's your integration branch? Pick your coding agent binary and model on the dashboard **Coding Agent** card (or answer CLI prompts 1c / 1c-ii). You should see `HERMES_HOME`, profile creation with `no default skills`, SOUL/skills seeded, `coding_agent_model` in config, and `Profiles verified`. If `hermes profile show` reports 90+ skills, something went wrong — see wiki/bootstrap.md."

Full reference: [wiki/bootstrap.md](../../wiki/bootstrap.md)

---

## Step 3: Choose your plan

Setup is done. Now you need something to execute. The agent will offer three paths.

**Agent says:**

> "Setup is complete. Now, what do you want to run through the pipeline?"
>
> **1. Guided tutorial** — I'll walk you through building a kanban board health dashboard. It scans your board for stalled cards, tracks token burn across plans, and flags orphaned worktrees. You'll end up with a real CLI tool you can run every day. This is the best way to see what the full pipeline can do.
>
> **2. Use an existing plan** — If you've already got a plan file, give me the path and we'll run it through harden → optimize → decompose → execute.
>
> **3. Start fresh** — Tell me what you want to build. I'll draft a plan from your description and we'll run it through the full pipeline together.
>
> "Which path sounds right?"

**If the user chooses option 2:** skip to Step 6 with their plan file. **If option 3:** draft a plan from their description and continue from Step 6. **If option 1:** continue below.

---

### Tutorial path: Kanban Board Health Dashboard

A CLI tool called `kanban-health` that gives you a one-command summary of your board:

```
$ kanban-health
Board: default
  Cards: 12 total · 3 running · 2 blocked · 5 done · 2 ready
  Stalled: card-47 (running 4.2h, no heartbeat in 45m)
  Token burn today: 1.2M input · 84K output · $3.42 est.
  Orphaned worktrees: /tmp/wt-oldplan-card12 (branch merged, worktree stale)
  Dispatcher: running · last tick 12s ago
```

This isn't just an example, you'll actually use this. And building it through governed decomposition — with three parallel workstreams, dependency gating, and full verification — will show you the pipeline at its best.

**Agent says:**

> "We're going to build a real tool — a kanban board health dashboard. It'll have three parts: a board scanner that finds stalled cards, a token reporter that shows your burn rate, and a worktree auditor that flags orphaned directories. Three workstreams, some independent and some dependent. By the end you'll have a CLI command you can run every morning to check your board's health. Ready?"

---

## Step 5: Plan the dashboard

**You say:**

> "Plan this out: I want a CLI tool called `kanban-health` that gives me a one-command summary of my kanban board. It should show: total cards by status, any cards that have been running too long or stalled, token burn across recent plans, and orphaned worktrees that need cleanup. Output should be clean terminal-friendly text."

The agent will draft a plan at `.agent/plans/kanban-health.plan.md`.

**Agent says:**

> "Tell me what you want the dashboard to show and I'll draft the plan. Describe it naturally. For example: 'I want a command that shows board health — stalled cards, token burn, orphaned worktrees.' Go ahead."

After the user describes their goal, draft a plan with three workstreams:

```markdown
---
name: Kanban Board Health Dashboard
plan_id: kanban-health
overview: A CLI tool that surfaces kanban board health — stalled cards, token burn, and orphaned worktrees — in a single terminal-friendly summary.
todos:
  - id: ws1-board-scanner
    content: Build the board scanner — query kanban.db for cards by status, detect stalled cards (running >1h with no recent heartbeat)
    status: pending
  - id: ws2-token-reporter
    content: Build the token reporter — read token JSONL logs from recent plans, compute input/output totals and cost estimates
    status: pending
  - id: ws3-worktree-auditor
    content: Build the worktree auditor — scan /tmp for wt-* directories, cross-reference with active kanban cards, flag orphaned worktrees
    status: pending
  - id: ws4-cli-formatter
    content: Build the CLI entry point and output formatter — wire the three scanners together into a single `kanban-health` command
    status: pending
---

# Kanban Board Health Dashboard

## Fix design

A CLI tool at `scripts/kanban-health` that prints a terminal-friendly health summary.
Three independent scanners (board, token, worktree) feed a shared formatter.
The formatter depends on all three scanners completing first.

## Architecture

```
kanban-health
├── board scanner   (WS1) ──┐
├── token reporter  (WS2) ──┼── formatter (WS4) ──► output
└── worktree auditor (WS3) ──┘
```

WS1–WS3 are independent and can run in parallel. WS4 depends on all three.
```

Show the user the draft and ask: *"Here's the plan — three scanners that feed a formatter. The scanners can run in parallel because they don't touch the same files. The formatter waits for all three. Does this look right?"*

---

## Step 6: Harden the plan

Switch to the orchestrator profile (new session — Hermes has no in-chat profile switch; `/profile` is show-only):

```bash
hermes profile list
hermes -p kanban-advanced-orchestrator chat
```

**You say:**

> "Harden the plan at `.agent/plans/kanban-health.plan.md`"

The orchestrator will verify anchor points, check for redundant work, confirm scope, and add test strategy and edge cases.

When the orchestrator prompts for review, you can accept or iterate. Say "Revise the test plan to include integration tests" or "Add an edge case for empty boards." The harden → revise loop can run as many times as needed before you lock the plan with Optimize.

**Agent says:**

> "Start an orchestrator session (`hermes -p kanban-advanced-orchestrator chat`), then say: 'Harden the plan at `.agent/plans/kanban-health.plan.md`'. The orchestrator will verify everything against your codebase and add any missing test coverage. When it prompts for review, you can accept or ask for changes — say 'Revise the test plan to include integration tests' if something's missing. This loop can run as many times as you want. When you're happy, we'll move to Optimize."

---

## Step 7: Optimize for Kanban

**You say:**

> "Optimize for Kanban"

The orchestrator adds `agent -p` blocks for each workstream, `Files:` and `Mode:` lines, a dependency graph showing WS1–WS3 parallel → WS4 dependent, iteration budgets, and commit messages.

**Agent says:**

> "Say: 'Optimize for Kanban.' The orchestrator will add execution formatting for all four workstreams — including the dependency graph that keeps the three scanners parallel and the formatter waiting. When it finishes, it'll prompt: 'Plan optimized. Ready when you are.'"

---

### Why gates instead of trust

Before we decompose: a prompt that says "please verify your work" is a request. A gate that says "you cannot complete this card unless these six conditions are met" is a script. The three gates we're about to run — preflight, attestation, card body policy — exist so that by the time a card reaches a worker, the environment is clean, the plan is locked, and the card body is complete. The worker can't skip them. The orchestrator can't skip them.

**Agent says:**

> "Quick pause. You're about to see three gates run. They're not slowdowns — they're the reason you can walk away from a running board and trust it'll finish. Preflight checks the environment. Attestation locks the plan. Card body policy validates every card. Each one is a script, not a prompt. Ready?"

---

## Step 8: Decompose into cards

**You say:**

> "Execute the plan"

The orchestrator runs `Preflight → Attestation → Card body policy → Decompose`. Your four workstreams become four kanban cards with WS1–WS3 linked as parents of WS4.

```bash
hermes kanban list
```

Expected output shows three cards in `ready` (the scanners, running in parallel) and one in `blocked` (the formatter, waiting on its parents).

**Agent says:**

> "Say: 'Execute the plan.' You'll see four cards created — three scanners in ready status and one formatter blocked, waiting for its parents to complete. That's the dependency graph at work. The scanners run in parallel because they touch different files. The formatter waits."

---

## Step 9: Dispatch and watch

**You run:**

```bash
hermes gateway run          # in tmux
hermes kanban dispatch --daemon
hermes kanban watch          # live events
```

The three scanner cards dispatch in parallel. As each completes, the auto-unblock cron (provisioned at **decomposition** via `provision_kanban_crons.sh`, removed at cleanup) detects that WS4's parents are done and promotes the formatter to `ready`. The worker runs the evaluation chain on every card — deterministic checks that include file compliance, tests, token exactness, and more:

1. Every file in `Files:` was actually changed
2. No files outside `Files:` were modified
3. The test command passed
4. The commit message matches the plan
5. Token usage was logged
6. At least one file has a real diff (not zero-output)

**Agent says:**

> "Start the gateway, dispatch, and watch. You'll see the three scanners run simultaneously — that's parallel decomposition. When each scanner completes, the evaluation chain verifies it — deterministic script checks (file scope, tests, tokens, and more), not a prompt. Once all three parents are done, the auto-unblock cron promotes the formatter automatically. You don't lift a finger."

> **If a card blocks:** "Run `hermes kanban show <task-id>`. Common causes: test failure (E003), missing token log (E005), unlisted file changes (E002). See [troubleshooting](../how-to/troubleshooting.md)."

---

### Why reconciliation and cleanup matter

All four cards complete. The dashboard works. We could stop here — but the next two steps are where the compound effect lives. Every plan you reconcile feeds the next one. Cleanup archives the board and captures the final token costs. The postmortem that follows includes those cleanup costs, so your totals are complete. Skip these steps now and you'll skip them on a ten-card plan when something actually fails.

**Agent says:**

> "The dashboard is built and working. But we're not done. Reconciliation checks compliance and shows what this cost. Cleanup archives the board so the postmortem includes those final token counts. Building the habit on a successful plan means you won't skip it when a plan actually fails. Say 'Yes' when the orchestrator prompts."

---

## Step 10: Reconcile

The orchestrator prompts: *"Kanban complete. Proceed to reconciliation?"*

**You say:** "Yes"

File-level compliance checks, token burn report, failure-mode taxonomy.

---

## Step 11: Cleanup

The orchestrator prompts: *"Reconciliation complete. Ready to clean up?"*

**You say:** "Yes"

Board archived, cron jobs removed, worktrees cleaned.

---

## Step 12: Postmortem

The orchestrator prompts: *"Cleanup complete. Ready for post-mortem report?"*

**You say:** "Yes"

Structured retrospective with timeline, KPIs, and lessons learned. The postmortem includes the cost of cleanup itself, so your token totals are complete.

---

## Try your new tool

**You run:**

```bash
./scripts/kanban-health
```

You built a real diagnostic tool through governed decomposition — three parallel workstreams with dependency gating, full verification on every card, and a permanent audit trail. And here's the key: once you said "Execute the plan" at Step 8, everything from preflight through cleanup could have run without you. That's the walk-away point. On your next plan — especially one with more cards — you can say "execute" and come back hours later to find the board complete and the reconcilliation waiting.

You can also interrupt at any time: "Pause the plan" blocks all cards. "Resume the plan" picks up where you left off. The board holds state until you return.

**Agent says:**

> "Run `./scripts/kanban-health`. That's a tool you built through a governed pipeline — three parallel scanners, dependency-gated formatter, verified at every step. You can run this every morning. And here's the bigger point: once you said 'Execute,' everything from preflight through cleanup could have run without you. On your next plan, try saying 'Execute in walk-away mode' — you'll only get paged if something needs your attention. You can also pause and resume the board anytime. The [interaction model](../reference/interaction-model.md) has the full reference."

---

## Where to go from here


| You want to                         | Read                                                            |
| ----------------------------------- | --------------------------------------------------------------- |
| Understand the architecture         | [architecture.md](../reference/architecture.md)                 |
| Learn the trigger phrases           | [interaction-model.md](../reference/interaction-model.md)       |
| Configure providers for parallelism | [provider-strategy.md](../how-to/provider-strategy.md)          |
| Use goal-mode cards                 | [goal-cards.md](../how-to/goal-cards.md)                        |
| Understand governance gates         | [governance.md](../how-to/governance.md)                        |
| See all error codes                 | [error-codes.md](../reference/error-codes.md)                   |
| Troubleshoot failures               | [troubleshooting.md](../how-to/troubleshooting.md)              |
| Why you'd use this (or not)         | [why-kanban-advanced.md](../explanation/why-kanban-advanced.md) |


