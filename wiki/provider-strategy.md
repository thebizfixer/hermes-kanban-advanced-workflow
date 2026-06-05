# Provider Strategy & Rate Limit Prevention

> **For the agent:** When a user sets up worker profiles, decomposes a plan, or hits HTTP 429 errors, load this page.

## The problem

Multiple workers dispatched simultaneously on the **same provider** will trigger rate limits (HTTP 429). This has caused protocol violations, orphaned tasks, and direct orchestrator intervention across multiple plans.

**Root cause:** The decomposer creates sibling cards that the dispatcher picks up in parallel. Two workers hitting the same provider at the same time → both get 429ed.

**Evidence:** 5 simultaneous worker-profile tasks on the same provider model → 8 consecutive HTTP 429 errors within 12 seconds. Two sibling cards dispatched simultaneously → both 429ed before parent link could be established.

## Solution 1: Serialize same-provider workers (required)

**Never dispatch two workers on the same provider simultaneously.** The orchestrator must serialize them via parent-child links:

```bash
# After creating cards, wire dependencies BEFORE unblocking:
hermes kanban link <parent_task> <child_task>
hermes kanban block <child_task>   # child stays blocked until parent completes
```

Rule: for any N cards assigned to the same `assignee` profile that use the same LLM provider, serialize them. Only one runs at a time.

This is documented in `kanban-orchestrator` § Step 2 — same-provider serialization.

## Solution 2: Multiple worker profiles with different providers (recommended for fan-out)

For true parallel fan-out, create multiple worker profiles — each using a **different provider** with its own rate-limit pool. The examples below use placeholder names (`<provider-a>`, `<provider-b>`, `<provider-c>`) — substitute your own providers:

```bash
# Worker 1: Provider A
hermes profile create worker-provider-a --clone
hermes config set model.default <provider-a>/<model-name> --profile worker-provider-a
hermes config set model.provider <provider-a> --profile worker-provider-a

# Worker 2: Provider B
hermes profile create worker-provider-b --clone
hermes config set model.default <provider-b>/<model-name> --profile worker-provider-b
hermes config set model.provider <provider-b> --profile worker-provider-b

# Worker 3: Provider C
hermes profile create worker-provider-c --clone
hermes config set model.default <provider-c>/<model-name> --profile worker-provider-c
hermes config set model.provider <provider-c> --profile worker-provider-c
```

Then assign cards to different worker profiles. Cards on `worker-provider-a` and `worker-provider-b` can run in parallel — they hit different API endpoints with independent rate limits.

## Solution 3: Fallback providers (safety net)

Configure each worker profile with fallback providers so a 429 doesn't kill the task:

```yaml
# $HERMES_HOME/profiles/<worker>/config.yaml
model:
  default: <provider-a>/<model-name>
  provider: <provider-a>
  fallback_providers:
    - <provider-b>/<model-name>      # Provider B API directly
    - <provider-c>/<model-name>
```

**Critical pitfall:** The fallback must use a **different provider's endpoint**, not the same provider under a different model name. Using `<provider-a>/<alternate-model>` as a fallback still routes through Provider A and shares its rate-limit pool — defeating the purpose.

**Correct:** `<provider-b>/<model-name>` (Provider B's API directly).

**Wrong:** `<provider-a>/<alternate-model>` (still Provider A, same pool).

## Solution 4: Stagger dispatch (defense in depth)

Even with serialization, stagger same-provider tasks by 30 seconds to prevent accidental stampedes:

```bash
# When creating sequential cards, add stagger notes:
hermes kanban create "WS1 — Omit SERP" --assignee worker
hermes kanban create "WS2 — Streaming insert" --assignee worker
hermes kanban link <ws1> <ws2>
```

The parent-child link ensures WS2 doesn't start until WS1 completes. The dispatcher naturally staggers them.

## Provider selection for Hermes Agent

For full provider configuration documentation, see:

- **Hermes Agent docs:** https://hermes-agent.nousresearch.com/docs (provider configuration, model setup, fallback behavior)
- **`hermes config --help`** — local provider/model management

## Profile thinking + provider matrix

Combined recommendations from [[configuration]] and this page:

| Profile          | Thinking    | Provider strategy                                   |
| ---------------- | ----------- | --------------------------------------------------- |
| **orchestrator** | `high`      | Single provider (e.g. your preferred reasoning model); low throughput |
| **Worker 1**     | `medium`    | Provider A (primary) + Provider B (fallback)        |
| **Worker 2**     | `medium`    | Provider B (primary) + Provider C (fallback)        |
| **Worker 3**     | `medium`    | Provider C (primary) + Provider A (fallback)        |
| **Coding agent** | `low` / off | Whatever the agent CLI uses; worker verifies output |

With 3 workers on different providers, up to 3 cards can fan out in parallel without rate-limit collisions. More workers = more profiles on distinct providers.

## Detection & recovery

| Symptom                             | Error                                | Fix                                                      |
| ----------------------------------- | ------------------------------------ | -------------------------------------------------------- |
| Multiple workers 429 simultaneously | Rate limit stampede                  | Serialize via parent-child links; add fallback providers |
| Single worker 429                   | Transient rate limit                 | Auto-retry once; fallback provider handles               |
| Model 404 after provider switch     | Wrong provider path                  | Check `model.default` uses correct provider prefix       |
| All fallbacks exhausted             | G001 (gateway) or protocol violation | Stagger dispatch; add more provider profiles             |
