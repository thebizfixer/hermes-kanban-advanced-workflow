---
plan_id: decompose-nine-regression
---

## Kanban optimization

#### Card 1 — Baseline

**Type:** code-gen

plan_id: decompose-nine-regression
files:
  - module_a.py
mode: modify-only

```agent
agent -p "Card 1 baseline task"
```

#### Card 2 — Second

**Type:** code-gen

plan_id: decompose-nine-regression
files:
  - module_b.py
mode: modify-only

```agent
agent -p "Card 2 task"
```

#### Card 3 — Forbidden block stress

**Type:** code-gen

plan_id: decompose-nine-regression
files:
  - module_c.py
mode: modify-only

```agent
agent -p "Card 3 with governance stress"
Forbidden: do not skip tests
Acceptance:
- Done when: tests pass
```

#### Card 4 — Fourth

**Type:** code-gen

plan_id: decompose-nine-regression
files:
  - module_d.py
mode: modify-only

```agent
agent -p "Card 4 task"
```

#### Card 5 — Depends on card 3

**Type:** code-gen

plan_id: decompose-nine-regression
ordinal_parent: card3
files:
  - module_e.py
mode: modify-only

```agent
agent -p "Card 5 after card 3"
```

#### Card 6 — Sixth

**Type:** code-gen

plan_id: decompose-nine-regression
files:
  - module_f.py
mode: modify-only

```agent
agent -p "Card 6 task"
```

#### Card 7 — Rebase preamble before agent fence

**Type:** code-gen

plan_id: decompose-nine-regression
files:
  - module_g.py
mode: modify-only

Before modifying: rebase on Card 6 branch if parallel worktrees

```agent
agent -p "Card 7 with rebase preamble in plan prose"
Call-sites: module_g.py:handler
```

#### Card 8 — Eighth

**Type:** code-gen

plan_id: decompose-nine-regression
files:
  - module_h.py
mode: modify-only

```agent
agent -p "Card 8 task"
```

#### Card 9 — Depends on card 7

**Type:** code-gen

plan_id: decompose-nine-regression
ordinal_parent: card7
files:
  - module_i.py
mode: modify-only

```agent
agent -p "Card 9 after card 7"
```
