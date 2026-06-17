---
plan_id: presentation-opt-good
---

# Presentation optimization fixture (passes checks 19–21)

Surface-slots:
  loader_slot: primary loader region
  status_panel: pending panel

## Kanban optimization

#### Card 1 — route-layout

```agent
agent -p 'reorder route shell'
Files: frontend/app/page.tsx
Mode: modify-only
Tests: npm test
Commit: "feat: route layout"

Acceptance (layout):
- line number of `Loader` < line number of `Panel` in route shell

Acceptance (a11y):
- reduced-motion path disables slide via prefers-reduced-motion
```
