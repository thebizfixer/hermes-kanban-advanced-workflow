---
plan_id: matrix-v5-fixture
---

# Fixture plan for decomposer tests

## Kanban optimization

#### Card 1 — Holistic config fix

**Type:** code-gen  
**Files:** `backend/app/config.py`, `backend/tests/test_config.py`  
**Mode:** modify-only  
**Tests:** `pytest backend/tests/test_config.py -q`

```agent
plan_id: matrix-v5-fixture
Implement config fix.
```

#### Card 2 — Service layer

**Type:** code-gen  
**Files:** `backend/app/services/foo.py`  
**Mode:** modify-only  
**Tests:** `pytest backend/tests/test_foo.py -q`

```agent
plan_id: matrix-v5-fixture
Implement foo service.
```

#### Card 3 — API route

**Type:** code-gen  
**Files:** `backend/app/routers/foo.py`  
**Mode:** modify-only  
**Tests:** `pytest backend/tests/test_foo_api.py -q`

```agent
plan_id: matrix-v5-fixture
Add foo route.
```

#### Card 4 — Frontend component

**Type:** code-gen  
**Files:** `frontend/components/Foo.tsx`  
**Mode:** modify-only  
**Tests:** `npm test -- Foo`

```agent
plan_id: matrix-v5-fixture
Add Foo component.
```

#### Card 5 — Integration tests

**Type:** code-gen  
**Files:** `backend/tests/test_integration_foo.py`  
**Mode:** modify-only  
**Tests:** `pytest backend/tests/test_integration_foo.py -q`

```agent
plan_id: matrix-v5-fixture
Integration tests.
```

#### Card 6 — Docs update

**Type:** code-gen  
**Files:** `docs/FOO.md`  
**Mode:** modify-only  
**Tests:** `true`

```agent
plan_id: matrix-v5-fixture
Document foo.
```

#### Card 7 — Final verification (EOF card)

**Type:** verification  
**Files:** `backend/app/services/foo.py`  
**Mode:** modify-only  
**Tests:** `pytest backend/tests/ -q`

```agent
plan_id: matrix-v5-fixture
Run full test suite.
```

### Same-provider staggering

Wave 1 cards may run in parallel with stagger.
