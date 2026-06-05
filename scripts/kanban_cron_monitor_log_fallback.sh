#!/usr/bin/env bash
# Fallback log inspector for walk-away cron monitoring.
#
# When chat delivery fails for ~2 consecutive ticks (~10 min), this script
# lets the operator inspect cron-monitor.log to confirm the poll still ran
# and surface any intervention events that would have been paged.
#
# Log directory: $KANBAN_CRON_LOG_DIR or $HERMES_HOME/kanban/logs
# (HERMES_HOME falls back to $HOME/.hermes).
#
# Usage:
#   bash scripts/kanban_cron_monitor_log_fallback.sh
#   bash scripts/kanban_cron_monitor_log_fallback.sh | tail -50

set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DEFAULT_LOG_DIR="$HERMES_HOME/kanban/logs"
LOG_DIR="${KANBAN_CRON_LOG_DIR:-$DEFAULT_LOG_DIR}"
LOG_FILE="$LOG_DIR/cron-monitor.log"

mkdir -p "$LOG_DIR"

if [[ -f "$LOG_FILE" ]]; then
    tail -30 "$LOG_FILE"
else
    echo "(cron-monitor.log not found at $LOG_FILE — no walk-away cron has logged yet)"
fi
