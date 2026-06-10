#!/usr/bin/env bash
# verify_anchors.sh — Pre-hardening anchor verification gate.
#
# Parses a plan markdown file for line-number references (L123, L123-456, at L789)
# and verifies each against current HEAD by checking the expected function/class
# is at that line position.
#
# Usage:
#   bash verify_anchors.sh --plan <plan.md>
#   bash verify_anchors.sh --plan <plan.md> --strict    # WARN becomes FAIL
#
# Exit codes:
#   0 — All anchors verified (or only advisories in non-strict mode)
#   1 — Stale or missing anchors found (or any WARN in strict mode)
#   2 — Usage error (no plan file, missing deps)

set -euo pipefail

PLAN=""
STRICT=false
PROFILE_OVERRIDE=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --plan) PLAN="$2"; shift 2 ;;
        --strict) STRICT=true; PROFILE_OVERRIDE="strict"; shift ;;
        --profile) PROFILE_OVERRIDE="$2"; shift 2 ;;
        *) echo "Unknown flag: $1"; exit 2 ;;
    esac
done

if [[ -z "$PLAN" ]]; then
    echo "Usage: verify_anchors.sh --plan <plan.md> [--strict]" >&2
    exit 2
fi
if [[ ! -f "$PLAN" ]]; then
    echo "ERROR: Plan file not found: $PLAN" >&2
    exit 2
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
# shellcheck source=lib/kanban_config.sh
source "$SCRIPT_DIR/lib/kanban_config.sh"
# shellcheck source=lib/governance_profile.sh
source "$SCRIPT_DIR/lib/governance_profile.sh"
load_governance_profile "$REPO_ROOT" "$PROFILE_OVERRIDE"
if [ "$GOVERNANCE_PROFILE" = "strict" ]; then
    STRICT=true
fi
echo "Governance profile: $GOVERNANCE_PROFILE"

FAILURES=0
WARNINGS=0
STALE_THRESHOLD=5  # Lines off before flagging as stale

red()    { echo -e "\033[31m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
green()  { echo -e "\033[32m$*\033[0m"; }

echo "=== Anchor Verification: $PLAN ==="
echo ""

# ── Extract line-number references from plan ────────────────────────────
# Patterns:
#   - `path/to/file.py` L123         (function at line 123)
#   - `path/to/file.py` L123-456     (range)
#   - `path/to/file.py` (L123–L456)  (parenthetical range)
#   - at L123                         (bare anchor, file from prior context)

# Strategy: Scan for file references first, then associate nearby L<num> patterns.

# Store plan content
PLAN_CONTENT=$(cat "$PLAN")

# Step 1: Find all file:lineno patterns
# Pattern: backtick-quoted path with .py/.ts/.js/.sh/.md ending, followed by L<num>
ANCHORS_FOUND=0
ANCHORS_CHECKED=0

while IFS= read -r line; do
    # Skip empty lines and lines without L-pattern
    [[ "$line" =~ L[0-9]+ ]] || continue

    # Extract file references from this line or prior context
    # Look for file path in backticks on the same line
    FILE=$(echo "$line" | grep -oP '`[^`]+\.(py|ts|js|sh|yaml|md|mdc)`' | head -1 | sed 's/`//g')
    # Also look for bare file: pattern
    [[ -z "$FILE" ]] && FILE=$(echo "$line" | grep -oP '\*\*File:\*\*\s+\S+' | sed 's/\*\*File:\*\*\s*//')

    # Extract all L<num> patterns from this line
    LNUMBERS=($(echo "$line" | grep -oP 'L[0-9]+' | sed 's/L//' | sort -nu))

    for LN in "${LNUMBERS[@]}"; do
        if [[ -z "$FILE" ]]; then
            # No file found — try to find it from the section header above
            SECTION_FILE=$(echo "$PLAN_CONTENT" | grep -B 50 "$line" | grep -oP '\*\*File:\*\*\s+\S+' | tail -1 | sed 's/\*\*File:\*\*\s*//')
            SECTION_FILE=$(echo "$SECTION_FILE" | sed 's/`//g')
            FILE="$SECTION_FILE"
        fi

        if [[ -z "$FILE" ]]; then
            # Still no file — try to find in same paragraph
            continue
        fi

        ((ANCHORS_FOUND++))
        echo "Anchor: $FILE L$LN"

        # Resolve the file path — try relative to repo root
        REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
        RESOLVED="$REPO_ROOT/$FILE"

        if [[ ! -f "$RESOLVED" ]]; then
            # Try without repo root prefix
            if [[ -f "$FILE" ]]; then
                RESOLVED="$FILE"
            else
                red "  ✗ FAIL: File not found: $FILE"
                ((FAILURES++))
                continue
            fi
        fi

        # Get the content at that line number
        TARGET_LINE=$(sed -n "${LN}p" "$RESOLVED" 2>/dev/null || echo "")
        if [[ -z "$TARGET_LINE" ]]; then
            red "  ✗ FAIL: Line $LN does not exist in $FILE"
            ((FAILURES++))
            continue
        fi

        # Try to match the function/class name from the plan context
        # Look for def/class/function names mentioned near this anchor in the plan
        ANCHOR_CONTEXT=$(echo "$PLAN_CONTENT" | grep -B 10 "$line" | grep -oP '(def|class|function|async def)\s+\w+' | tail -1 | awk '{print $2}')
        [[ -z "$ANCHOR_CONTEXT" ]] && ANCHOR_CONTEXT=$(echo "$line" | grep -oP '`[a-zA-Z_][a-zA-Z0-9_]*`' | head -1 | sed 's/`//g')

        if [[ -n "$ANCHOR_CONTEXT" ]]; then
            # Search for this function/class name near the stated line
            CONTEXT_START=$(( LN - STALE_THRESHOLD ))
            [[ $CONTEXT_START -lt 1 ]] && CONTEXT_START=1
            CONTEXT_END=$(( LN + STALE_THRESHOLD ))

            FOUND_AT=$(sed -n "${CONTEXT_START},${CONTEXT_END}p" "$RESOLVED" | grep -n "^\s*\(def\|class\|async def\)\s\+${ANCHOR_CONTEXT}\b" | head -1 | cut -d: -f1)
            if [[ -z "$FOUND_AT" ]]; then
                red "  ✗ FAIL: '$ANCHOR_CONTEXT' not found ±$STALE_THRESHOLD lines of L$LN in $FILE"
                ((FAILURES++))
            else
                ACTUAL_LN=$(( CONTEXT_START + FOUND_AT - 1 ))
                OFFSET=$(( ACTUAL_LN - LN ))
                OFFSET_ABS=${OFFSET#-}
                if [[ $OFFSET_ABS -eq 0 ]]; then
                    green "  ✓ '$ANCHOR_CONTEXT' at L$ACTUAL_LN (exact match)"
                elif [[ $OFFSET_ABS -le $STALE_THRESHOLD ]]; then
                    yellow "  ⚠ WARN: '$ANCHOR_CONTEXT' at L$ACTUAL_LN (offset ${OFFSET}) — anchor is L$LN"
                    ((WARNINGS++))
                fi
                ((ANCHORS_CHECKED++))
            fi
        else
            # No function name to verify — just confirm the line exists
            green "  ✓ Line L$LN exists in $FILE (no function name to cross-reference)"
            ((ANCHORS_CHECKED++))
        fi
    done
done <<< "$PLAN_CONTENT"

# ── Summary ─────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $ANCHORS_FOUND anchors found, $ANCHORS_CHECKED verified, $FAILURES failures, $WARNINGS warnings ==="

EXIT_CODE=0
if [[ $FAILURES -gt 0 ]]; then
    if governance_failures_block; then
        red "BLOCKED: $FAILURES anchor(s) could not be verified against HEAD."
        EXIT_CODE=1
    else
        yellow "PASS (advisory): $FAILURES anchor failure(s) downgraded — review before hardening."
    fi
fi

if [[ $WARNINGS -gt 0 ]]; then
    if governance_warnings_block; then
        yellow "BLOCKED (strict profile): $WARNINGS warning(s) treated as failures."
        EXIT_CODE=1
    else
        yellow "PASS with $WARNINGS stale anchor warning(s). Re-verify line numbers before hardening."
    fi
fi

if [[ $FAILURES -eq 0 ]] && [[ $WARNINGS -eq 0 ]]; then
    green "PASS: All $ANCHORS_FOUND anchors verified against HEAD."
fi

exit $EXIT_CODE
