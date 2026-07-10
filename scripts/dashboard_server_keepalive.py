"""dashboard_server_keepalive.py — Crash-recovery safety net (Python, no bash).

The sidecar server self-manages its lifecycle. This script is a backup:
if the server crashes, this restarts it within 60s.

Invoked by a script-only cron job every 60s.
Empty stdout = silent. Non-empty = action was taken.

Platform-neutral: uses sys.executable for the subprocess spawn, resolves
HERMES_HOME with a cross-platform default, and handles stale PID locks
regardless of Windows/Linux/WSL.
"""
import os
import subprocess
import sys
from pathlib import Path

PORT = os.environ.get("KA_DASHBOARD_PORT", "18900")
HEALTH_URL = f"http://127.0.0.1:{PORT}/health"

# Check if server is already running via health endpoint
try:
    import urllib.request
    req = urllib.request.Request(HEALTH_URL, method="GET")
    urllib.request.urlopen(req, timeout=2)
    sys.exit(0)  # running — silent
except Exception:
    pass  # not running — start it

# Find plugin root (this script is at <plugin_root>/scripts/)
script_dir = Path(__file__).resolve().parent
plugin_root = script_dir.parent
server_script = plugin_root / "scripts" / "dashboard_server.py"

# HERMES_HOME — explicit in cron env or cross-platform default
hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))

# Start server (PID locking in Python prevents duplicates)
# Clean stale PID lock from previous dead process
lock_path = hermes_home / "run" / f"kanban-dashboard-server-{PORT}.pid"
if lock_path.exists():
    try:
        lock_path.unlink()
    except OSError:
        pass
subprocess.Popen(
    [sys.executable, str(server_script)],
    cwd=str(plugin_root),
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
print(f"[dashboard_server] Crash recovery: restarted on port {PORT}")
