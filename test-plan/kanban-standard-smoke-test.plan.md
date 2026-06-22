1|---
2|name: Kanban Standard Smoke Test
3|plan_id: kanban-standard-smoke-test
4|line_budget: 200
5|overview: >
6|  Standardized end-to-end validation test for the kanban-advanced plugin.
7|  Verifies card body parsing, coding-agent dispatch, eval chain governance
8|  (E001–E022), token logging (E018/E020), postmortem generation, and
9|  reconciliation. Ships with the plugin as a self-diagnostic for new
10|  installations. Produces example postmortem/KPI artifacts demonstrating
11|  post-execution success.
12|isProject: false
13|optimization_checklist:
14|  plan_committed: pass
15|contingencies:
16|  - risk: "Coding agent not configured (KANBAN_CODING_AGENT unset or binary missing)"
17|    probability: High
18|    impact: BLOCKING
19|    mitigation: "Run `hermes kanban-advanced init` and set `coding_agent_binary` in kanban-config.yaml. See `plugin/data/references/coding-agent-auth.md`."
20|    auto_retry: false
21|  - risk: "Coding agent auth failure (OAuth expired / API key missing)"
22|    probability: Medium
23|    impact: BLOCKING
24|    mitigation: "Authenticate coding CLI per `plugin/data/references/coding-agent-auth.md`. Re-run preflight after auth fix."
25|    auto_retry: false
26|  - risk: "Token tracker unavailable (scripts/token_tracker.py not provisioned)"
27|    probability: Low
28|    impact: BLOCKING
29|    mitigation: "Re-run `hermes kanban-advanced init` or `Update Plugin` to provision token_tracker.py."
30|    auto_retry: false
31|  - risk: "Eval chain script missing (scripts/kanban_evaluation_chain.py not found)"
32|    probability: Low
33|    impact: BLOCKING
34|    mitigation: "Run `Update Plugin` to restore scripts. Verify with: ls scripts/kanban_evaluation_chain.py"
35|    auto_retry: false
36|  - risk: "E002 unlisted changes blocks Card 4 (negative test — expected behavior)"
37|    probability: Expected
38|    impact: DEGRADED
39|    mitigation: "Card 4 intentionally creates a file outside Files: scope. Verify the block message contains E002_UNLISTED_FILE_CHANGE. Archive the blocked card — this confirms the governance gate works."
40|    auto_retry: false
41|  - risk: "E020/E018 token logging blocked — coding agent produces no JSON usage block (aider only; hermes now uses authoritative insights metering)"
42|    probability: Medium
43|    impact: BLOCKING
44|    mitigation: "Known limitation for text-only coding agents (hermes, aider). The eval chain requires JSON output with usage block for exact token tracking. See § Token Logging Gap below. Fix: configure a JSON-output coding agent (Cursor, Claude Code, Codex, Gemini, Grok) or add a metering hook for hermes sessions in coding_agent_invoke.sh."
45|    auto_retry: false
46|  - risk: "Gateway not running (dispatcher won't pick up cards)"
47|    probability: Medium
48|    impact: BLOCKING
49|    mitigation: "Start gateway: `hermes gateway run` (or Windows scheduled task). Verify: `hermes kanban list` shows cards."
50|    auto_retry: false
51|  - risk: "Subagent gate interrupted (parallel subagents crash mid-exec)"
52|    probability: Medium
53|    impact: BLOCKING
54|    mitigation: "Known infrastructure issue — delegation subagents may be interrupted. Fall back to serial gate: set `subagent_gate: false` in kanban-config.yaml, then run pre_dispatch_gate.sh directly."
55|    auto_retry: false
56|  - risk: "Missing or incomplete hermes_insights deltas at orchestrator checkpoints"
57|    probability: Medium
58|    impact: BLOCKING
59|    mitigation: "Orchestrator must emit planning-complete, decompose-complete, audit-start, and cleanup-complete checkpoints using hermes_token_meter + insights. Verify deltas appear in tokens.jsonl and postmortem."
60|    auto_retry: false
61|  - risk: "Insufficient negative/governance test coverage"
62|    probability: Medium
63|    impact: DEGRADED
64|    mitigation: "Add deliberate malformed-block, budget-violation, and circular-dep negative tests. Archive blocked cards only after confirming exact E00x messages."
65|    auto_retry: false
66|  - risk: "No formal preflight/attestation step before decompose"
67|    probability: Low
68|    impact: BLOCKING
69|    mitigation: "Run explicit preflight checklist (env, profiles, scripts, gateway, token tracker, kanban-config, DB integrity) and attest before creating root/gate cards."
70|    auto_retry: false
71|todos:
72|  - id: card-preflight
73|    content: "Preflight & Attestation: verify env, profiles, scripts, gateway, token tracker, kanban-config, DB integrity before any decomposition"
74|    status: pending
75|  - id: card-1-utils
76|    content: "Create test-plan/scripts/smoke_utils.py with utility functions (greet, add, format_name)"
77|    status: pending
78|  - id: card-2-tests
79|    content: "Create test-plan/scripts/test_smoke_utils.py with pytest tests for all three functions"
80|    status: pending
81|  - id: card-3-modify
82|    content: "Modify test-plan/scripts/smoke_utils.py to add a multiply() function (modify-only mode)"
83|    status: pending
84|  - id: card-4-e002-test
85|    content: "Negative governance test: agent attempts to create a file NOT on Files: (should trigger E002 block)"
86|    status: pending
87|  - id: card-5-verify
88|    content: "Verification card: run test suite, check token log exists, confirm all artifacts"
89|    status: pending
90|---
91|
92|# Kanban Standard Smoke Test
93|
94|> **Purpose:** Validate a kanban-advanced installation end-to-end. Run after `hermes kanban-advanced init` to confirm the plugin is correctly provisioned, the coding agent dispatches and produces verifiable output, all evaluation chain gates function, and postmortem artifacts are generated correctly.
95|
96|> **Prerequisites:**
97|> - Hermes Agent ≥ 0.16.0
98|> - `hermes kanban-advanced init` completed successfully
99|> - Coding agent binary configured in `.hermes/kanban-overrides/kanban-config.yaml` (`coding_agent_binary`)
100|> - Coding agent authenticated (see `plugin/data/references/coding-agent-auth.md`)
101|> - Gateway running (`hermes gateway run` or scheduled task)
102|> - Working directory: host project repo root
103|
104|> **Expected duration:** 15–30 minutes (depends on coding agent speed)
105|> **Expected outcome:** 4 code-gen cards dispatched, 3 completed (Cards 1–3), 1 blocked (Card 4 — E002 expected), 1 verification card passed (Card 5). Postmortem generated at `.hermes/kanban/reports/kanban-standard-smoke-test_postmortem_*.md`. Token log populated at `~/.hermes/kanban/tokens.jsonl` with entries for all completed cards.
106|
107|> **Success criteria:**
108|> - [ ] Preflight & attestation checklist passed before any decomposition
109|> - [ ] Card 1 completed: `test-plan/scripts/smoke_utils.py` exists with `greet()`, `add()`, `format_name()`
110|> - [ ] Card 2 completed: `test-plan/scripts/test_smoke_utils.py` exists, tests pass
111|> - [ ] Card 3 completed: `multiply()` added to `test-plan/scripts/smoke_utils.py`, tests updated and pass
112|> - [ ] Card 4 blocked: E002_UNLISTED_FILE_CHANGE detected, unlisted file auto-reverted
113|> - [ ] Card 5 completed: test suite passes, token log has entries, artifacts exist
114|> - [ ] hermes_insights deltas present at all four orchestrator checkpoints (planning/decompose/audit/cleanup)
115|> - [ ] Token log shows separate input/output/cache where available; Effective Tokens (or equivalent) calculated in postmortem
116|> - [ ] ≥2 negative/governance tests executed (E002 + at least one malformed-block or budget test)
117|> - [ ] Reconciliation covers: file compliance, token burn accuracy, governance taxonomy, state, and delta vs prior run
118|> - [ ] Postmortem generated with KPI JSON, reconciliation sidecar, and concrete action items (owner + deadline)
119|> - [ ] Postmortem is blameless and includes decision-path / tool-usage traces for main cards
120|> - [ ] Token log (`tokens.jsonl`) has entries for completed cards + orchestrator checkpoints
121|> - [ ] Reconciliation report confirms ≥80% success rate and 0 un-reconciled governance violations
122|
123|---
124|
125|## Architecture Notes
126|
127|### Token Logging
128|
129|The kanban-advanced plugin supports three tiers of token metering, selected automatically based on the configured coding agent binary:
130|
131|| Tier | Source | Agents | Mechanism |
132||------|--------|--------|-----------|
133|| 1 | `agent` | Cursor, Claude Code, Codex, Gemini, Grok | Exact from agent JSON `usage` block |
134|| 2 | `hermes_insights` | hermes | Authoritative — Hermes insights delta (provider response headers, not self-reported) |
135|| 3 | `estimated` | aider, unknown binaries | Character-count estimation from agent output |
136|
137|**The `hermes` coding agent** uses Tier 2: hermes_token_meter.py snapshots Hermes token state before dispatch, computes the delta after dispatch, and logs authoritative counts to `tokens.jsonl`. This is NOT self-reported — it comes from Hermes' own provider accounting.
138|
139|**Orchestrator checkpoints (mandatory for walk-away mode):**
140|- planning-complete
141|- decompose-complete
142|- audit-start
143|- cleanup-complete
144|
145|All four must log via hermes_insights delta. Deltas must appear in the project `.hermes/kanban/tokens.jsonl`.
146|
147|**Observability requirements (drawn from industry best practices for AI agent workflows):**
148|- Track across the full decision chain (not just final output).
149|- Log input / output / cache tokens separately.
150|- Compute weighted "Effective Tokens" style metric in postmortem (model cost multiplier × (I + 0.1×C + 4×O)).
151|- Enforce workflow-level budget thresholds for the smoke test run.
152|- Capture decision paths, tool calls, and per-step spend for traceability and audit.
153|
154|**The `aider` coding agent** uses Tier 3 estimation. aider produces text-only output with no JSON usage block and no integration with Hermes insights. Consider configuring a JSON-output coding agent for exact token tracking.
155|
156|**How to check your coding agent:**
157|```bash
158|grep 'coding_agent_binary' .hermes/kanban-overrides/kanban-config.yaml
159|# Expected values with full token support: agent, cursor-agent, claude, codex, gemini, grok, hermes
160|# Estimated-only: aider
161|```
162|
163|---
164|
165|
166|**Escalation demo (for next run):** Card 4 (E002 negative test) is expected to block at least twice.
167|Board-keeper detects the second block (re-block count >=2), forces `[escalation:worker:attempt:2]`,
168|calls tracker, and escalates to orchestrator (unblocks with tag + comment). Orchestrator resolves
169|before a third block. Use local override `escalation_max_attempts.worker: 2` (orchestrator: 1-2)
170|for the smoke test to make thresholds hit cleanly at 2.
171|
172|## Workstream 1 — Create Utility Module
173|
174|**Priority:** 1 (no dependencies)
175|
176|**File:** `test-plan/scripts/smoke_utils.py`
177|**Mode:** create-only
178|
179|**Approach:** Create a Python utility module with three simple functions that cover different code patterns (string return, arithmetic, string formatting). This exercises basic agent code generation and the E001 (file compliance) gate.
180|
181|**Tests:** Included inline — the agent creates both the module and an inline assertion.
182|
183|### Card body
184|
185|```agent
186|agent -p "Create test-plan/scripts/smoke_utils.py with three utility functions.
187|plan_id: kanban-standard-smoke-test
188|Files: test-plan/scripts/smoke_utils.py
189|Mode: create-only
190|Spec:
191|- def greet() -> str: returns 'hello from kanban'
192|- def add(a: int, b: int) -> int: returns a + b
193|- def format_name(first: str, last: str) -> str: returns '{last}, {first}' (Last, First format)
194|- Include a __main__ guard that runs all three and prints results
195|Acceptance:
196|- Done when: test-plan/scripts/smoke_utils.py exists with all three functions
197|- Verify: python3 -c \"from scripts.smoke_utils import greet, add, format_name; assert greet() == 'hello from kanban'; assert add(2,3) == 5; assert format_name('Jane','Doe') == 'Doe, Jane'; print('OK')\"
198|Tests: python3 -c \"from scripts.smoke_utils import greet, add, format_name; assert greet() == 'hello from kanban'; assert add(2,3) == 5; assert format_name('Jane','Doe') == 'Doe, Jane'; print('ALL TESTS PASSED')\"
199|Commit: feat: add smoke_utils module with greet, add, format_name
200|Diff cap: if >30 net lines, STOP and report.
201|Do NOT push to main — commit to worktree branch only."
202|```
203|
204|---
205|
206|## Workstream 2 — Create Tests
207|
208|**Priority:** 2 (depends on Card 1 — needs test-plan/scripts/smoke_utils.py to exist)
209|
210|**File:** `test-plan/scripts/test_smoke_utils.py`
211|**Mode:** create-only
212|
213|**Approach:** Create a proper pytest test file covering all three functions from Card 1. Tests edge cases: negative numbers for `add()`, single-name input for `format_name()`. Exercises E003 (test pass) and E021 (acceptance test coverage) gates.
214|
215|### Card body
216|
217|```agent
218|agent -p "Create test-plan/scripts/test_smoke_utils.py with pytest tests for smoke_utils.
219|plan_id: kanban-standard-smoke-test
220|Files: test-plan/scripts/test_smoke_utils.py
221|Mode: create-only
222|Spec:
223|- test_greet_returns_string: calls greet(), asserts isinstance(result, str) and result != ''
224|- test_add_positive: add(2, 3) == 5
225|- test_add_negative: add(-1, -1) == -2
226|- test_add_zero: add(0, 5) == 5
227|- test_format_name_standard: format_name('Jane', 'Doe') == 'Doe, Jane'
228|- test_format_name_single: format_name('Madonna', '') == ', Madonna'
229|- Import smoke_utils from scripts.smoke_utils
230|Acceptance:
231|- Done when: pytest test-plan/scripts/test_smoke_utils.py passes all 6 tests (or runs all collected tests with 0 failures)
232|- Verify: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
233|Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
234|Commit: test: add pytest suite for smoke_utils
235|Diff cap: if >50 net lines, STOP and report.
236|Do NOT push to main — commit to worktree branch only."
237|```
238|
239|---
240|
241|## Workstream 3 — Modify Utility Module
242|
243|**Priority:** 3 (depends on Cards 1 and 2 — modifies test-plan/scripts/smoke_utils.py, needs tests to exist for verification)
244|
245|**File:** `test-plan/scripts/smoke_utils.py`
246|**Mode:** modify-only
247|
248|**Approach:** Add a `multiply()` function to the existing module AND add a corresponding test to the test file. This exercises E001 (modify-only file compliance), E003 (existing tests still pass), and E017 (excessive churn — should be well under budget).
249|
250|### Card body
251|
252|```agent
253|agent -p "Add a multiply() function to test-plan/scripts/smoke_utils.py and a test to test-plan/scripts/test_smoke_utils.py.
254|plan_id: kanban-standard-smoke-test
255|Files: test-plan/scripts/smoke_utils.py (modify-only), test-plan/scripts/test_smoke_utils.py
256|Mode: modify-only
257|Spec:
258|- Add def multiply(a: int, b: int) -> int: returns a * b to test-plan/scripts/smoke_utils.py
259|- Add test_multiply_positive and test_multiply_zero to test-plan/scripts/test_smoke_utils.py
260|- Do NOT modify existing functions — only add the new one
261|- Do NOT create any new files
262|Acceptance:
263|- Done when: multiply(3, 4) == 12 and pytest passes all tests including new ones
264|- Verify: python3 -c \"from scripts.smoke_utils import multiply; assert multiply(3,4) == 12; assert multiply(0,5) == 0; print('OK')\" && python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
265|Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
266|Commit: feat: add multiply function to smoke_utils with tests
267|Diff cap: if >40 net lines, STOP and report.
268|Do NOT push to main — commit to worktree branch only."
269|```
270|
271|---
272|
273|## Workstream 4 — Negative Governance Test (E002 Gate)
274|
275|**Priority:** 4 (depends on Card 3 completing first — needs the worktree to have current code)
276|
277|**File:** `test-plan/scripts/smoke_utils.py`
278|**Mode:** modify-only
279|
280|**Approach:** This card **intentionally** instructs the agent to create a file NOT listed in `Files:`. The agent is told to add a docstring to `test-plan/scripts/smoke_utils.py` (which is on `Files:`) BUT ALSO to create a `scripts/_smoke_scratchpad.md` file (which is NOT on `Files:`). The evaluation chain Step 2 (E002) should detect the unlisted file and auto-revert it. If the revert succeeds, the card completes. If unlisted changes remain after revert, the card blocks.
281|
282|**Expected behavior:** E002_UNLISTED_FILE_CHANGE triggers. The unlisted file is either auto-reverted (card completes with warning) or blocks if revert fails. Either outcome is valid — the test verifies that the E002 gate is operational.
283|
284|### Card body
285|
286|```agent
287|agent -p "Add a module-level docstring to test-plan/scripts/smoke_utils.py AND create a scratchpad file.
288|plan_id: kanban-standard-smoke-test
289|Files: test-plan/scripts/smoke_utils.py
290|Mode: modify-only
291|Spec:
292|- Add a module-level docstring to test-plan/scripts/smoke_utils.py: '\"\"\"Kanban smoke test utility functions.\"\"\"' at the top of the file (after the hashbang if present, before imports)
293|- ALSO create scripts/_smoke_scratchpad.md with content '# Smoke Test Scratchpad' and today's date
294|- This second file is INTENTIONALLY not on the Files: line — the governance gate should catch it
295|Acceptance:
296|- Verify: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
297|- The _smoke_scratchpad.md file will be auto-reverted by the eval chain — this is EXPECTED
298|Tests: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
299|Commit: docs: add module docstring to smoke_utils
300|Diff cap: if >20 net lines, STOP and report.
301|Do NOT push to main — commit to worktree branch only."
302|```
303|
304|> **Operator note:** If this card completes (E002 auto-revert succeeded), the governance gate worked silently — the unlisted file was created then removed. Check `scope_violations.jsonl` in the kanban logs for the recorded violation. If this card blocks (E002 revert failed), the gate prevented unlisted changes from being committed — archive the blocked card. Either result validates the E002 gate.
305|
306|---
307|
308|## Workstream 5 — Verification and Artifact Check
309|
310|**Priority:** 5 (depends on Cards 1–4 completing)
311|
312|**Type:** verification-local
313|
314|**Approach:** Run the full test suite and verify that all expected artifacts exist. This card does NOT invoke a coding agent — it's a supervisor-worker card that validates the entire test run's outputs.
315|
316|### Card body
317|
318|```
319|Type: verification-local
320|plan_id: kanban-standard-smoke-test
321|Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
322|Commit: N/A (verification only)
323|Mode: read-only
324|```
325|
326|**Additional verification checks (run manually after card completion):**
327|
328|```bash
329|# 1. Token log populated
330|python3 scripts/kanban_token_report.py --plan kanban-standard-smoke-test
331|
332|# 2. Postmortem generated (run after all cards complete)
333|python3 scripts/generate_postmortem.py --plan-id kanban-standard-smoke-test
334|
335|# 3. Verify postmortem artifacts exist
336|ls -la .hermes/kanban/reports/kanban-standard-smoke-test_*.md
337|ls -la .hermes/kanban/reports/kanban-standard-smoke-test_kpi.json
338|
339|# 4. Run reconciliation
340|# Follow kanban-advanced:kanban-reconciliation skill
341|```
342|
343|---
344|
345|## Kanban optimization
346|
347|### Dependency graph
348|
349|```
350|Card 1 (create test-plan/scripts/smoke_utils.py)
351|  └─→ Card 2 (create tests)
352|        └─→ Card 3 (modify smoke_utils + tests)
353|              └─→ Card 4 (negative E002 test)
354|                    └─→ Card 5 (verification + artifact check)
355|```
356|
357|| Parent | Child | Relationship |
358||--------|-------|-------------|
359|| — | Card 1 | Root — no dependencies |
360|| Card 1 | Card 2 | Card 2 needs test-plan/scripts/smoke_utils.py to exist |
361|| Card 2 | Card 3 | Card 3 modifies files Card 2 tests; needs tests as safety net |
362|| Card 3 | Card 4 | Card 4 runs after module is stable to test E002 gate cleanly |
363|| Card 4 | Card 5 | Card 5 verifies everything after all cards complete |
364|
365|All cards are serial (wave_parent chain) because each depends on the prior card's output file.
366|
367|### Dispatch order
368|
369|| Wave | Cards | Parallel? |
370||------|-------|-----------|
371|| 1 | Card 1 — Create Utility Module | Solo |
372|| 2 | Card 2 — Create Tests | Solo (depends on Card 1) |
373|| 3 | Card 3 — Modify Utility Module | Solo (depends on Card 2) |
374|| 4 | Card 4 — Negative E002 Test | Solo (depends on Card 3) |
375|| 5 | Card 5 — Verification | Solo (depends on Card 4) |
376|
377|---
378|
379|#### Card 1 — Create Utility Module
380|plan_id: kanban-standard-smoke-test
381|files:
382|  - test-plan/scripts/smoke_utils.py
383|mode: create-only
384|wave: 1
385|estimated_lines: 25
386|
387|```agent
388|agent -p "Create test-plan/scripts/smoke_utils.py with three utility functions.
389|plan_id: kanban-standard-smoke-test
390|Files: test-plan/scripts/smoke_utils.py
391|Mode: create-only
392|Spec:
393|- def greet() -> str: returns 'hello from kanban'
394|- def add(a: int, b: int) -> int: returns a + b
395|- def format_name(first: str, last: str) -> str: returns '{last}, {first}' (Last, First format)
396|- Include a __main__ guard that runs all three and prints results
397|Acceptance:
398|- Done when: test-plan/scripts/smoke_utils.py exists with all three functions
399|- Verify: python3 -c \"from scripts.smoke_utils import greet, add, format_name; assert greet() == 'hello from kanban'; assert add(2,3) == 5; assert format_name('Jane','Doe') == 'Doe, Jane'; print('OK')\"
400|Tests: python3 -c \"from scripts.smoke_utils import greet, add, format_name; assert greet() == 'hello from kanban'; assert add(2,3) == 5; assert format_name('Jane','Doe') == 'Doe, Jane'; print('ALL TESTS PASSED')\"
401|Commit: feat: add smoke_utils module with greet, add, format_name
402|Diff cap: if >30 net lines, STOP and report.
403|Do NOT push to main — commit to worktree branch only."
404|```
405|
406|#### Card 2 — Create Tests
407|plan_id: kanban-standard-smoke-test
408|files:
409|  - test-plan/scripts/test_smoke_utils.py
410|mode: create-only
411|wave: 2
412|wave_parent: card1
413|estimated_lines: 40
414|
415|```agent
416|agent -p "Create test-plan/scripts/test_smoke_utils.py with pytest tests for smoke_utils.
417|plan_id: kanban-standard-smoke-test
418|Files: test-plan/scripts/test_smoke_utils.py
419|Mode: create-only
420|Spec:
421|- test_greet_returns_string: calls greet(), asserts isinstance(result, str) and result != ''
422|- test_add_positive: add(2, 3) == 5
423|- test_add_negative: add(-1, -1) == -2
424|- test_add_zero: add(0, 5) == 5
425|- test_format_name_standard: format_name('Jane', 'Doe') == 'Doe, Jane'
426|- test_format_name_single: format_name('Madonna', '') == ', Madonna'
427|- Import smoke_utils from scripts.smoke_utils
428|Acceptance:
429|- Done when: pytest test-plan/scripts/test_smoke_utils.py passes all 6 tests (or runs all collected tests with 0 failures)
430|- Verify: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
431|Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
432|Commit: test: add pytest suite for smoke_utils
433|Diff cap: if >50 net lines, STOP and report.
434|Do NOT push to main — commit to worktree branch only."
435|```
436|
437|#### Card 3 — Modify Utility Module
438|plan_id: kanban-standard-smoke-test
439|files:
440|  - test-plan/scripts/smoke_utils.py
441|  - test-plan/scripts/test_smoke_utils.py
442|mode: modify-only
443|wave: 3
444|wave_parent: card2
445|estimated_lines: 35
446|
447|```agent
448|agent -p "Add a multiply() function to test-plan/scripts/smoke_utils.py and a test to test-plan/scripts/test_smoke_utils.py.
449|plan_id: kanban-standard-smoke-test
450|Files: test-plan/scripts/smoke_utils.py (modify-only), test-plan/scripts/test_smoke_utils.py
451|Mode: modify-only
452|Spec:
453|- Add def multiply(a: int, b: int) -> int: returns a * b to test-plan/scripts/smoke_utils.py
454|- Add test_multiply_positive and test_multiply_zero to test-plan/scripts/test_smoke_utils.py
455|- Do NOT modify existing functions — only add the new one
456|- Do NOT create any new files
457|Acceptance:
458|- Done when: multiply(3, 4) == 12 and pytest passes all tests including new ones
459|- Verify: python3 -c \"from scripts.smoke_utils import multiply; assert multiply(3,4) == 12; assert multiply(0,5) == 0; print('OK')\" && python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
460|Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
461|Commit: feat: add multiply function to smoke_utils with tests
462|Diff cap: if >40 net lines, STOP and report.
463|Do NOT push to main — commit to worktree branch only."
464|```
465|
466|#### Card 4 — Negative Governance Test (E002)
467|plan_id: kanban-standard-smoke-test
468|files:
469|  - test-plan/scripts/smoke_utils.py
470|mode: modify-only
471|wave: 4
472|wave_parent: card3
473|estimated_lines: 10
474|
475|```agent
476|agent -p "Add a module-level docstring to test-plan/scripts/smoke_utils.py AND create a scratchpad file.
477|plan_id: kanban-standard-smoke-test
478|Files: test-plan/scripts/smoke_utils.py
479|Mode: modify-only
480|Spec:
481|- Add a module-level docstring to test-plan/scripts/smoke_utils.py: '\"\"\"Kanban smoke test utility functions.\"\"\"' at the top of the file (after the hashbang if present, before imports)
482|- ALSO create scripts/_smoke_scratchpad.md with content '# Smoke Test Scratchpad' and today's date
483|- This second file is INTENTIONALLY not on the Files: line — the governance gate should catch it
484|Acceptance:
485|- Verify: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
486|- The _smoke_scratchpad.md file will be auto-reverted by the eval chain — this is EXPECTED
487|Tests: python3 -c \"import scripts.smoke_utils; assert scripts.smoke_utils.__doc__ is not None; print('OK')\"
488|Commit: docs: add module docstring to smoke_utils
489|Diff cap: if >20 net lines, STOP and report.
490|Do NOT push to main — commit to worktree branch only."
491|```
492|
493|#### Card 5 — Verification and Artifact Check
494|plan_id: kanban-standard-smoke-test
495|type: verification-local
496|wave: 5
497|wave_parent: card4
498|Tests: python3 -m pytest test-plan/scripts/test_smoke_utils.py -v
499|Commit: N/A (verification only)
500|Mode: read-only
501|