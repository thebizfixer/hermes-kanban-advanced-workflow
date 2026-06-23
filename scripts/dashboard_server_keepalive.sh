#!/usr/bin/env bash
# dashboard_server_keepalive.sh — Crash-recovery safety net.
#
# The sidecar server self-manages its lifecycle (starts when dashboard is alive,
# self-terminates when it disappears). This script is a backup: if the server
# crashes, this restarts it within 60s.
#
# Invoked by a script-only cron job every 60s.
# Empty stdout = silent. Non-empty = action was taken.

set -euo pipefail

PORT="${KA_DASHBOARD_PORT:-18900}"
PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_SCRIPT="$PLUGIN_ROOT/scripts/dashboard_server.py"

# Check if server is already running via health endpoint
if curl -s --max-time 2 "http://127.0.0.1:${PORT}/health" > /dev/null 2>&1; then
    exit 0  # running — silent
fi

# Server not running — start it (PID locking in Python prevents duplicates)
cd "$PLUGIN_ROOT"
nohup python3 "$SERVER_SCRIPT" > /dev/null 2>&1 &
echo "[dashboard_server] Crash recovery: restarted on port $PORT"
