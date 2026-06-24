#!/usr/bin/env bash
# sanity_check.sh — environmentally neutral validation of kanban-advanced-workflow
# No external dependencies (no MongoDB, no API, no gateway). Validates structure only.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0

check() {
  local name="$1" condition="$2"
  echo -n "  [$name] "
  if eval "$condition" 2>/dev/null; then
    echo "PASS"
    PASS=$((PASS + 1))
  else
    echo "FAIL"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Structure checks ==="
check "plugin/skills dir" "test -d plugin/skills"
check "scripts dir" "test -d scripts"
check "plugin/data/registry" "test -d plugin/data/registry"
check "plugin/data/references" "test -d plugin/data/references"
check "wiki dir" "test -d wiki"
check "tests dir" "test -d tests"

echo ""
echo "=== Platform-neutral parsing ==="
check "plan_parse.py" "test -f scripts/lib/plan_parse.py"
check "cli_output_parse.py" "test -f scripts/lib/cli_output_parse.py"
check "verify_anchors.py" "test -f scripts/verify_anchors.py"
check "audit_anchors.py" "test -f scripts/audit_anchors.py"
if command -v rg >/dev/null 2>&1; then
  if rg 'grep -oP|grep -P' scripts/ --glob '!sanity_check.sh' 2>/dev/null \
      | rg -v '(#.*grep -P|no grep -P|"""SSOT)' | rg -q .; then
    echo "  [no grep -P in scripts/] FAIL"
    rg 'grep -oP|grep -P' scripts/ --glob '!sanity_check.sh' 2>/dev/null \
      | rg -v '(#.*grep -P|no grep -P|"""SSOT)' || true
    FAIL=$((FAIL + 1))
  else
    echo "  [no grep -P in scripts/] PASS"
    PASS=$((PASS + 1))
  fi
else
  if grep -rE 'grep -oP|grep -P' scripts/ --exclude=sanity_check.sh 2>/dev/null \
      | grep -vE '(#.*grep -P|no grep -P|"""SSOT)' >/dev/null 2>&1; then
    echo "  [no grep -P in scripts/] FAIL"
    grep -rE 'grep -oP|grep -P' scripts/ --exclude=sanity_check.sh 2>/dev/null \
      | grep -vE '(#.*grep -P|no grep -P|"""SSOT)' || true
    FAIL=$((FAIL + 1))
  else
    echo "  [no grep -P in scripts/] PASS"
    PASS=$((PASS + 1))
  fi
fi
check "auto_unblock uses kanban_cli_parse" "grep -q 'kanban_cli_parse.sh' scripts/${AUTO_UNBLOCK_SCRIPT:-auto_unblock.sh}"

echo ""
echo "=== Shell scripts: LF line endings ==="
while IFS= read -r -d '' sh; do
  rel="${sh#./}"
  if grep -q $'\r' "$sh" 2>/dev/null; then
    echo "  [$rel] FAIL (CRLF)"
    FAIL=$((FAIL + 1))
  else
    echo "  [$rel] PASS (LF)"
    PASS=$((PASS + 1))
  fi
done < <(find scripts -name '*.sh' -print0)

echo ""
echo "=== Bash syntax (bash -n) ==="
while IFS= read -r -d '' sh; do
  rel="${sh#./}"
  if bash -n "$sh" 2>/dev/null; then
    echo "  [$rel] PASS"
    PASS=$((PASS + 1))
  else
    echo "  [$rel] FAIL"
    FAIL=$((FAIL + 1))
  fi
done < <(find scripts -name '*.sh' -print0)

echo ""
echo "=== Skill frontmatter integrity ==="
for skill in plugin/skills/*/SKILL.md; do
  name=$(basename "$(dirname "$skill")")
  check "$name: has name" "grep -q '^name:' '$skill'"
  check "$name: has description" "grep -q '^description:' '$skill'"
done

echo ""
echo "=== Error code registry ==="
REG="plugin/data/registry/error-codes.yaml"
check "error-codes.yaml exists" "test -f $REG"
check "E001 defined" "grep -q 'E001:' $REG"
check "E006 defined" "grep -q 'E006:' $REG"
check "E017 defined" "grep -q 'E017:' $REG"
check "E022 defined" "grep -q 'E022:' $REG"
check "E028 defined" "grep -q 'E028:' $REG"
check "E029 defined" "grep -q 'E029:' $REG"

echo ""
echo "=== Presentation acceptance ==="
check "frontend-neutrality.md" "test -f plugin/data/references/frontend-neutrality.md"
check "presentation_acceptance.py" "test -f scripts/lib/presentation_acceptance.py"
check "verify_optimization_presentation.py" "test -f scripts/lib/verify_optimization_presentation.py"
check "bash_counters.sh" "test -f scripts/lib/bash_counters.sh"
check "kanban_layout_acceptance.sh" "test -f scripts/kanban_layout_acceptance.sh"

echo ""
echo "=== Parallel subagent gate prompts ==="
check "gate-subagent-plan.md" "test -f plugin/data/prompts/gate-subagent-plan.md"
check "gate-subagent-env.md" "test -f plugin/data/prompts/gate-subagent-env.md"
check "gate-subagent-infra.md" "test -f plugin/data/prompts/gate-subagent-infra.md"
check "gate-subagent-plan-parse.md" "test -f plugin/data/prompts/gate-subagent-plan-parse.md"
check "gate-subagent-cron-setup.md" "test -f plugin/data/prompts/gate-subagent-cron-setup.md"
check "parallel-subagent-gate.md ref" "test -f plugin/data/references/parallel-subagent-gate.md"

echo ""
echo "=== Cross-references ==="
check "pre_dispatch_gate.sh exists" "test -f scripts/pre_dispatch_gate.sh"
check "auto_unblock.sh exists" "test -f scripts/${AUTO_UNBLOCK_SCRIPT:-auto_unblock.sh}"
check "coding-agent-auth.md exists" "test -f plugin/data/references/coding-agent-auth.md"
check "coding agents doc lists binaries" "grep -q 'claude' docs/reference/coding-agents.md && grep -q 'codex' docs/reference/coding-agents.md"

echo ""
echo "=== Platform neutrality (scripts) ==="
check "coding_agent_env resolves HOME" "grep -q 'Path.home' scripts/lib/coding_agent_env.sh || grep -q python3 scripts/lib/coding_agent_env.sh"
check "preflight has macOS vm_stat path" "grep -q vm_stat scripts/preflight.sh"
check "auth prewarm respects KANBAN_CODING_AGENT" "grep -q 'KANBAN_CODING_AGENT' scripts/pre_dispatch_gate.sh"
check "hermes_home supports USERPROFILE" "grep -q USERPROFILE scripts/lib/hermes_home.sh"
check "auto_unblock portable task id parse" "grep -q 'kanban_extract_task_ids' scripts/${AUTO_UNBLOCK_SCRIPT:-auto_unblock.sh} scripts/lib/kanban_cli_parse.sh scripts/lib/auto_unblock_core.sh"

echo ""
echo "=== Python unit tests ==="
_run_unit_tests() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -m unittest discover -s tests -p 'test_*.py' -q
  elif command -v python >/dev/null 2>&1; then
    python -m unittest discover -s tests -p 'test_*.py' -q
  elif command -v py >/dev/null 2>&1; then
    py -3 -m unittest discover -s tests -p 'test_*.py' -q
  else
    return 2
  fi
}
set +e
_run_unit_tests 2>/dev/null
_ut_rc=$?
set -e
if [[ $_ut_rc -eq 0 ]]; then
  echo "  [unittest discover] PASS"
  PASS=$((PASS + 1))
elif [[ $_ut_rc -eq 2 ]]; then
  echo "  [unittest discover] SKIP (no python on PATH — run in WSL or install Python)"
  PASS=$((PASS + 1))
else
  echo "  [unittest discover] FAIL"
  FAIL=$((FAIL + 1))
fi

echo ""
echo "========================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================"
[ "$FAIL" -eq 0 ] && echo "SANITY CHECK PASSED" || echo "SANITY CHECK FAILED"
exit "$FAIL"
