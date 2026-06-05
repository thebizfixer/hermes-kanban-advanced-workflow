#!/usr/bin/env bash
# Increment the kanban intervention counter.
#
# Writes to the project's .hermes/kanban/logs/interventions.count
# (same directory as postmortem reports, attestation, and token log).
#
# Usage:
#   bash hermes-kanban-advanced-workflow/scripts/kanban_intervention_inc.sh
#   bash scripts/kanban_intervention_inc.sh

set -euo pipefail

# Find project root by walking up from script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
for _ in {1..6}; do
    if [[ -d "$PROJECT_ROOT/.hermes/kanban" ]]; then
        break
    fi
    PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done

LOGDIR="$PROJECT_ROOT/.hermes/kanban/logs"
COUNTER="$LOGDIR/interventions.count"

mkdir -p "$LOGDIR"

if [[ -f "$COUNTER" ]]; then
    count=$(<"$COUNTER")
    if [[ "$count" =~ ^[0-9]+$ ]]; then
        new=$((count + 1))
    else
        new=1
    fi
else
    new=1
fi

echo "$new" > "$COUNTER"
echo "$new"
