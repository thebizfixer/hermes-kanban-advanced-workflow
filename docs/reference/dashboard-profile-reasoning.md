# Dashboard: profile reasoning effort (spec)

> **Status:** Implemented.  
> **Scope:** Hermes dispatch profiles (`kanban-advanced-orchestrator`, `kanban-advanced-worker`) on the Kanban-Advanced dashboard tab.  
> **Out of scope:** Coding-agent binary reasoning (model/config-driven; see `coding-agent-cli-invocation.md`).

## Overview

Dispatch profile **reasoning effort** (Hermes `agent.reasoning_effort`) is visible on the Kanban-Advanced dashboard **Profiles** card and editable in the **Profile settings** modal alongside model selection. Writes go through `PUT /api/plugins/kanban-advanced/profiles/{profile_name}` and persist via `hermes -p <profile> config set agent.reasoning_effort <level>`.

Bootstrap/init seeds role defaults when the key is absent (orchestrator → `high`, worker → `medium`). Preflight and decomposition do **not** enforce reasoning levels.

## Goals

1. **Display** the effective reasoning effort on each profile row (read-only badge extension).
2. **Configure** reasoning effort in the existing **Change model** modal alongside provider/model selection.
3. **Persist** via Hermes CLI (`hermes -p <profile> config set agent.reasoning_effort <level>`) — same durability as model changes.
4. **Do not enforce** reasoning levels in preflight or decomposition gates (informational + operator control only).

## Non-goals

- Coding-agent (`KANBAN_CODING_AGENT`) thinking/reasoning UI or dispatch flags.
- Per-model reasoning overrides inside Hermes (upstream limitation; profile-global only).
- Replacing Hermes core `/api/model/options` or provider auth flows.
- Blocking bootstrap/decompose when reasoning is `low` or unset.

---

## Hermes config contract

### Canonical field

| Key | Location | Values |
|-----|----------|--------|
| `agent.reasoning_effort` | `$HERMES_HOME/profiles/<profile>/config.yaml` | `none`, `low`, `minimal`, `medium`, `high`, `xhigh` |

Hermes default when unset: **`medium`** ([configuration options](https://nousresearch-hermes-agent.mintlify.app/reference/configuration-options)).

Runtime toggle in interactive Hermes chat: `/reasoning [level]` — dashboard changes apply to **new** sessions on that profile (same semantics as model changes).

### Legacy / docs

Wiki and setup docs use **`agent.reasoning_effort`** as SSOT (`wiki/configuration.md`, `wiki/setup.md`). Implementation:

1. **Writes** only `agent.reasoning_effort` (canonical).
2. **Reads** `agent.reasoning_effort` first; falls back to legacy `model.thinking` in `config.yaml` for display when present.
3. **Does not** delete legacy `model.thinking` on write (operator may remove manually).

### Role recommendations (UI hints only)

| Profile | Recommended | Rationale |
|---------|-------------|-----------|
| `kanban-advanced-orchestrator` | `high` | Planning, audit, reconcile |
| `kanban-advanced-worker` | `medium` | Supervision + eval chain balance |

Show as helper text in the modal (“Recommended for orchestrator: high”). Do **not** auto-change on every modal open.

### Provider caveat (modal footnote)

> Reasoning effort applies to models and providers that support extended thinking (e.g. OpenRouter, Nous Portal). Other providers may ignore this setting.

---

## Backend

### 1. `plugin/hermes_model_config.py`

Add:

```python
REASONING_EFFORT_LEVELS = (
    "none", "low", "minimal", "medium", "high", "xhigh",
)

DEFAULT_REASONING_EFFORT = "medium"

def normalize_reasoning_effort(value: str | None) -> str | None: ...

def read_reasoning_effort_from_yaml(path: Path) -> dict[str, str]:
    """
    Returns:
      reasoning_effort: normalized level or DEFAULT when absent
      reasoning_effort_configured: bool  # True if key present in yaml
      reasoning_effort_source: "agent" | "legacy_model_thinking" | "default"
    """

def read_reasoning_effort_from_config_show(stdout: str) -> dict[str, str]:
    """Prefer on-disk config.yaml via config_path_from_show; else parse show output."""

def apply_reasoning_effort_to_profile(
    run, hermes_bin, profile, level: str, *, env=None, timeout=15
) -> bool:
    """hermes -p <profile> config set agent.reasoning_effort <level>"""
```

**Normalization rules:**

- Strip + lower-case input; map synonyms only if Hermes accepts them (otherwise reject).
- Invalid API input → HTTP 400 with allowed list in `detail`.

**Do not** remove legacy `model.thinking` on read; optional one-time migration on write is **out of scope** (operator can delete manually).

### 2. `dashboard/plugin_api.py` — status extension

Extend `_check_profiles()` profile info:

```json
{
  "exists": true,
  "has_model": true,
  "model": "anthropic/claude-opus-4.6",
  "provider": "openrouter",
  "model_reachable": true,
  "reasoning_effort": "high",
  "reasoning_effort_configured": true,
  "reasoning_effort_source": "agent",
  "recommended_reasoning_effort": "high"
}
```

`recommended_reasoning_effort` is derived from profile name (`orchestrator` → `high`, `worker` → `medium`, else `medium`). Not persisted.

When `reasoning_effort_configured` is false, still return `reasoning_effort: "medium"` for display but set `reasoning_effort_source: "default"`.

### 3. New endpoint: `PUT /api/plugins/kanban-advanced/profiles/{profile_name}`

**Why a kanban endpoint:** Hermes core `PUT /api/profiles/{name}/model` does not accept reasoning. The dashboard modal routes all profile writes through the plugin-owned endpoint so model + reasoning stay atomic.

**Path param:** `profile_name` — must be one of the configured dispatch profiles (`resolve_dispatch_profiles`).

**Request body** (JSON; at least one field required):

```json
{
  "provider": "openrouter",
  "model": "anthropic/claude-opus-4.6",
  "reasoning_effort": "high"
}
```

| Field | Required | Behavior |
|-------|----------|----------|
| `provider` + `model` | Optional pair | If `model` set, apply via existing `apply_model_config_to_profile` (provider optional if already in profile). |
| `reasoning_effort` | Optional | Apply via `apply_reasoning_effort_to_profile`. |

**Response 200:**

```json
{
  "ok": true,
  "profile": "kanban-advanced-orchestrator",
  "model": { "provider": "openrouter", "default": "anthropic/claude-opus-4.6" },
  "reasoning_effort": "high",
  "reasoning_effort_configured": true
}
```

**Errors:**

| Code | Condition |
|------|-----------|
| 400 | Empty body; invalid `reasoning_effort`; `model` without resolvable provider when required |
| 404 | Profile not in dispatch list or Hermes profile missing |
| 500 | `hermes config set` non-zero exit |

**Side effects:**

- Invalidate server probe cache key `model_reachable:{profile}` so next `probe=1` re-pings.
- Do **not** require Save/Bootstrap — writes go directly to profile `config.yaml` (same as Hermes model picker today).

### 4. Bootstrap / init (optional seed)

On **first** profile provisioning (`ensure_dispatch_profiles` / bootstrap), if `agent.reasoning_effort` is absent:

| Profile | Seed value |
|---------|------------|
| `kanban-advanced-orchestrator` | `high` |
| `kanban-advanced-worker` | `medium` |

Only when the key is missing — never overwrite operator-configured values. Log:

```text
   OK kanban-advanced-orchestrator: reasoning_effort = high (default)
```

CLI `hermes kanban-advanced init` should mirror the same seeding via shared helper.

---

## Frontend (`dashboard/dist/index.js`)

### Profile row badge

Extend `profileBadge(info)`:

| State | Label pattern |
|-------|----------------|
| Reachable | `reachable (model · effort)` e.g. `reachable (claude-opus-4.6 · high)` |
| Configured, no probe | `configured (model · effort)` |
| Effort is Hermes default and unconfigured | omit `· medium` **or** show `· medium (default)` — **prefer omit** to reduce noise |

Truncate long model IDs with CSS `truncate` (unchanged); effort suffix stays visible.

### Modal UX

Rename header to **Profile settings — {profile}** (covers model + reasoning).

**Layout** (top → bottom):

1. Provider/model list (unchanged; uses `GET /api/model/options`).
2. **Reasoning effort** control — new section above footer:
   - `<select>` or segmented buttons for six levels.
   - Default selection on open: `status.profiles[profile].reasoning_effort`.
   - Helper: “Recommended for this role: **high**” (from `recommended_reasoning_effort`).
   - Footnote: provider caveat (one line, `text-muted-foreground`).
3. Footer:
   - Left: summary `model · effort` (pending selections).
   - Right: **Cancel** | **Apply** (replace **Switch**).

**State:**

```javascript
pendingReasoningEffort  // set on openModelPicker from status
selectedModel           // null until user picks a different model
initialReasoningEffort  // for dirty detection
initialModelSnapshot    // provider+model for dirty detection
```

**Apply enabled when:**

- `selectedModel` is set (model change), **or**
- `pendingReasoningEffort !== initialReasoningEffort` (reasoning-only change).

**Apply action:**

```javascript
PUT /api/plugins/kanban-advanced/profiles/{profile}
{
  provider: selectedModel?.provider,      // omit if reasoning-only
  model: selectedModel?.model,            // omit if reasoning-only
  reasoning_effort: pendingReasoningEffort // omit if unchanged
}
```

On success: close modal, `reloadStatus()` (preserve probe behavior).

**Implemented:** The modal calls `PUT /api/plugins/kanban-advanced/profiles/{profile}` only (no Hermes core profile model PUT). Model switches use the same provider normalization as `normalize_provider_id` in `hermes_model_config.py`.

### Accessibility

- Reasoning `<select>`: `aria-label="Reasoning effort for {profile}"`.
- Recommended hint: `aria-describedby` linking to footnote.

---

## API documentation

Update `dashboard/API.md`:

- Status `profiles.*` new fields.
- Full `PUT .../profiles/{profile_name}` section with examples.

Add cross-link from `wiki/configuration.md` § Thinking / reasoning effort.

---

## Tests

| File | Cases |
|------|-------|
| `tests/test_hermes_model_config.py` | Read `agent.reasoning_effort`; legacy `model.thinking` fallback; normalize invalid → None; apply mock subprocess |
| `tests/test_dashboard_profile_reasoning.py` (new) | PUT validation; dispatch-profile allowlist; 400 on bad level; mock hermes success/failure |
| Manual | Open modal → change effort only → Apply → `grep reasoning_effort` in profile config.yaml → badge updates |

---

## Rollout / compatibility

| Concern | Mitigation |
|---------|------------|
| Hermes &lt; 0.16 without `agent.reasoning_effort` | `config set` may fail — return 500 with message to upgrade Hermes; document in troubleshooting |
| Existing operators with no key | Display as default `medium`; optional bootstrap seed on next init |
| Session cache | Reasoning change affects **new** `hermes -p` sessions only (document in modal footnote) |

---

## Implementation checklist

- [x] `hermes_model_config.py` — read/write reasoning helpers + constants
- [x] `plugin_api.py` — status fields + `PUT /profiles/{name}`
- [x] `dashboard/dist/index.js` — modal control + badge + Apply flow
- [x] `dashboard/API.md` — document endpoints
- [x] `wiki/configuration.md`, `wiki/setup.md` — `agent.reasoning_effort` SSOT
- [x] `tests/test_hermes_model_config.py` + `tests/test_dashboard_profile_reasoning.py`
- [x] Bootstrap seed in `plugin_api.py` init + `plugin/cli.py` init

---

## Future (not in this spec)

- Hermes upstream: extend core `PUT /api/profiles/{name}/model` with `reasoning_effort` and delegate from kanban endpoint.
- Per-model reasoning in custom provider definitions (Hermes issue #15511).
- Preflight **advisory** warning when orchestrator effort &lt; `high` (opt-in knob).
