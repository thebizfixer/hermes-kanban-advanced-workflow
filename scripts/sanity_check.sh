#!/usr/bin/env bash
# sanity_check.sh — environmentally neutral validation of kanban-advanced-workflow
# No external dependencies (no MongoDB, no API, no gateway). Validates structure only.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0
WARN=0

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
check "skills dir exists" "test -d skills"
check "scripts dir exists" "test -d scripts"
check "registry dir exists" "test -d registry"
check "references dir exists" "test -d references"
check "policies dir exists" "test -d policies"
check "bundles dir exists" "test -d bundles"
check "wiki dir exists" "test -d wiki"
check "prompts dir exists" "test -d prompts"

echo ""
echo "=== Scripts executable ==="
for s in scripts/*.sh; do
  check "$s executable" "test -x $s"
done

echo ""
echo "=== Skill frontmatter integrity ==="
for skill in plugin/skills/*/SKILL.md; do
  name=$(basename "$skill")
  check "$name: has name" "grep -q '^name:' $skill"
  check "$name: has version" "grep -q '^version:' $skill"
  check "$name: has description" "grep -q '^description:' $skill"
done

echo ""
echo "=== Error code registry ==="
check "registry/error-codes.yaml exists" "test -f registry/error-codes.yaml"
check "E001 defined" "grep -q 'E001:' registry/error-codes.yaml"
check "E006 defined" "grep -q 'E006:' registry/error-codes.yaml"
check "E017 defined" "grep -q 'E017:' registry/error-codes.yaml"
check "P001 defined" "grep -q 'P001:' registry/error-codes.yaml"
check "P005 defined" "grep -q 'P005:' registry/error-codes.yaml"
check "A001 defined" "grep -q 'A001:' registry/error-codes.yaml"

echo ""
echo "=== Version consistency ==="
# Extract versions from skills
ORCH_VER=$(grep '^version:' plugin/skills/kanban-orchestrator/SKILL.md | head -1 | awk '{print $2}')
WORK_VER=$(grep '^version:' plugin/skills/kanban-worker/SKILL.md | head -1 | awk '{print $2}')
PLAN_VER=$(grep '^version:' plugin/skills/kanban-planning/SKILL.md | head -1 | awk '{print $2}')
echo "  orchestrator: $ORCH_VER"
echo "  worker:       $WORK_VER"
echo "  planning:     $PLAN_VER"
# All versions should be >= 5.0.0
check "orchestrator >= 5.0" "echo $ORCH_VER | awk -F. '{exit !(\$1>=5)}'"
check "worker >= 5.0" "echo $WORK_VER | awk -F. '{exit !(\$1>=5)}'"
check "planning >= 5.0" "echo $PLAN_VER | awk -F. '{exit !(\$1>=5)}'"

echo ""
echo "=== Cross-references valid ==="
# Check that referenced scripts exist
check "pre_dispatch_gate.sh referenced + exists" "grep -q 'pre_dispatch_gate.sh' plugin/skills/kanban-orchestrator/SKILL.md && test -f scripts/pre_dispatch_gate.sh"
check "post_merge_gate.sh referenced + exists" "grep -q 'post_merge_gate.sh' plugin/skills/kanban-orchestrator/SKILL.md && test -f scripts/post_merge_gate.sh"
check "auto_unblock.sh referenced + exists" "grep -q 'auto_unblock.sh' plugin/skills/kanban-orchestrator/SKILL.md && test -f scripts/auto_unblock.sh"
check "coding-agent-governance.md referenced + exists" "grep -q 'coding-agent-governance.md' plugin/skills/kanban-worker/SKILL.md && test -f plugin/data/references/coding-agent-governance.md"
check "error-codes.yaml referenced + exists" "grep -q 'error-codes.yaml' plugin/skills/kanban-orchestrator-governance/SKILL.md && test -f plugin/data/registry/error-codes.yaml"
check "no ~/ hardcodes in skills" "! grep -rq '\$HOME/' plugin/skills/ 2>/dev/null || true"

echo ""
echo "=== No environment-specific paths ==="
check "no /mnt/ in scripts" "! grep -rq '/mnt/' scripts/*.sh 2>/dev/null || true"
check "no ~/ hardcodes in skills" "! grep -rq '\$HOME/' skills/*.md 2>/dev/null || true"
check "no Windows paths in references" "! grep -rq 'C:\\\\\|D:\\\\' references/ 2>/dev/null || true"

echo ""
echo "=== Coding agent governance ==="
GOV="skills/references/coding-agent-governance.md"
check "governance template exists" "test -f $GOV"
check "ordinal contract present" "grep -q 'Ordinal Contract\|idempotent' $GOV"
check "positive space (Q1-6)" "grep -q 'What is Needed\|How is it Needed\|What is Wanted\|How is it Wanted\|Where does it belong\|How does it belong' $GOV"
check "negative space (Q9-14)" "grep -q 'NOT Wanted\|NOT belong\|NOT be received' $GOV"

echo ""
echo "========================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================"
[ "$FAIL" -eq 0 ] && echo "SANITY CHECK PASSED" || echo "SANITY CHECK FAILED"
exit $FAIL
