# Frontend neutrality

SSOT for framework-agnostic UI planning in kanban-advanced. Cross-refs: `plan-file-format.md`, `worker-actionability-audit.md`, host neutrality in plugin shipping docs.

## Principle

Shipping plugin content describes **what surfaces exist and how they relate**, not **which framework renders them**. Host-specific paths and grep patterns live in overlay `ui_stack`, not in `plugin/`, `docs/`, `wiki/`, or `scripts/`.

| Avoid in shipping content | Use instead |
| --- | --- |
| React / Next.js / Vue / Svelte as assumed stack | **host UI stack** (`ui_stack.framework` in overlay) |
| `page.tsx`, hooks by name | **route shell**, `{ui_stack.page_glob}` |
| Vendor CSS class strings as defaults | **motion utility token**, `ui_stack.motion.entry_transition_pattern` |
| Host component names | **surface slots** (`primary_loader_slot`, `status_panel`, `detail_region`) |
| Single test runner hardcoded | `ui_stack.test_command` or plan `Tests:` line |

## Surface slots

Plans with presentation work declare **`Surface-slots:`** under `## Kanban optimization` (same role as backend `Contracts:`):

```markdown
Surface-slots:
  primary_loader_slot: progress indicator where main content will render
  status_panel: in-flight list / step cards region
  detail_region: post-load primary content (table, chart, etc.)
```

Card `Spec:` items reference **slot names**, not host components.

## Host overlay `ui_stack`

```yaml
ui_stack:
  framework: react-next   # react-next | vue-nuxt | sveltekit | angular | static
  page_glob: "frontend/app/**/page.tsx"
  motion:
    reduced_query: "prefers-reduced-motion: reduce"
    entry_transition_pattern: "animate-in fade-in|transition-opacity"
  test_command: "cd frontend && npm test --"
```

`kanban_layout_acceptance.sh` resolves patterns from overlay + plan slots — never hardcodes vendor classes in the plugin bundle.

## Acceptance blocks

| Block | Purpose |
| --- | --- |
| `Acceptance (presentation):` | Umbrella for layout + motion (optional label) |
| `Acceptance (layout):` | DOM order, entry transition class on named wrapper |
| `Acceptance (a11y):` | Live region during load; reduced-motion path |

WCAG references in plans are **testable patterns inspired by** accessibility guidelines — not legal conformance claims.

## Visual regression

Optional `visual_regression: pass|skipped` in **card attestation** JSON. Host chooses Playwright, Cypress, Storybook, etc. — plugin does not mandate a vendor.

## Review gate (shipping paths)

```bash
rg -i 'tailwind|shadcn|next\.js|useEffect' plugin/ docs/ wiki/ scripts/ \
  | rg -v 'frontend-neutrality|ui_stack|Avoid in' && echo "FIX: use surface slots / ui_stack"
```
