#!/usr/bin/env python3
"""Kanban-Advanced dashboard sidecar server — self-managing uvicorn process.

Hermes v0.17.0 restricts non-bundled plugins from auto-importing Python API backends
(GHSA-5qr3-c538-wm9j). This script runs the same API router as a standalone process
on localhost.

Lifecycle (self-managing, no cron needed for normal operation):
- Started by: plugin init or keepalive cron (crash recovery)
- Watchdog: checks every 30s if any Hermes process is alive (via psutil)
- Self-terminates: when no Hermes processes are running
- PID file: prevents duplicate instances

Security:
- Binds to 127.0.0.1 only (OWASP best practice)
- CORS: localhost origins only
- No shell subprocess for process detection (psutil, not pgrep)
- PID file with fcntl exclusive lock
"""
from __future__ import annotations

import os
import sys
import time
import threading
import signal
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dashboard.plugin_api import router

app = FastAPI(title="Kanban-Advanced Dashboard API")

# ── CORS: localhost only (remote access uses reverse proxy, same-origin) ──
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ──
@app.get("/health")
async def health():
    return {"status": "ok", "pid": os.getpid()}

app.include_router(router, prefix="/api/plugins/kanban-advanced")


# ═══════════════════════════════════════════════════════════════════════
# Lifecycle management (self-managing — no cron needed)
# ═══════════════════════════════════════════════════════════════════════

def _is_dashboard_running() -> bool:
    """Check if any Hermes process is running (gateway, desktop, or CLI).
    
    The Hermes desktop app (Electron) and gateway (pythonw) don't have
    'hermes' in their process name on Windows, so we can't detect them
    by name alone. Instead, we look for ANY Hermes process — if Hermes
    is running at all, the dashboard might be in use. This is fail-open:
    the sidecar only self-terminates when NO hermes processes exist.
    The keepalive cron (60s) handles crash recovery; the watchdog is for
    clean shutdown when the user exits Hermes.
    """
    try:
        import psutil
    except ImportError:
        return True  # can't check — stay alive
    
    for proc in psutil.process_iter(['name']):
        try:
            name = (proc.info['name'] or '').lower()
            if 'hermes' in name:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _watchdog_loop(check_interval: float = 30.0):
    """Background thread: exit when dashboard process disappears."""
    # Give the dashboard time to start before first check
    time.sleep(check_interval)
    while True:
        if not _is_dashboard_running():
            print("[dashboard_server] Dashboard process not found — shutting down")
            os.kill(os.getpid(), signal.SIGTERM)
            return
        time.sleep(check_interval)


def _acquire_pid_lock(port: int) -> bool:
    """Acquire exclusive PID file lock. Returns True on success."""
    lock_dir = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "run"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"kanban-dashboard-server-{port}.pid"
    
    # Try fcntl-based locking first (Linux/macOS)
    try:
        import fcntl  # noqa: F811
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR | os.O_BINARY if hasattr(os, 'O_BINARY') else 0)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.ftruncate(lock_fd, 0)
        os.write(lock_fd, str(os.getpid()).encode())
        return True
    except Exception:
        pass  # fall through to simple PID file
    
    # Simple PID file with staleness detection (Windows / no-fcntl)
    if lock_path.exists():
        try:
            stale_pid = int(lock_path.read_text().strip())
            try:
                import psutil
                if psutil.pid_exists(stale_pid):
                    proc = psutil.Process(stale_pid)
                    cmdline = ' '.join(proc.cmdline()) if proc.cmdline() else ''
                    if 'dashboard_server' in cmdline:
                        print(f"[dashboard_server] Another instance running (PID {stale_pid})")
                        return False
            except (ImportError, psutil.NoSuchProcess, psutil.AccessDenied):
                pass  # can't verify — assume stale
        except (OSError, ValueError):
            pass  # stale lock
    
    lock_path.write_text(str(os.getpid()))
    return True


if __name__ == "__main__":
    port = int(os.environ.get("KA_DASHBOARD_PORT", "18900"))
    
    # Single-instance guard
    if not _acquire_pid_lock(port):
        sys.exit(1)
    
    # Start watchdog thread
    watchdog = threading.Thread(target=_watchdog_loop, daemon=True)
    watchdog.start()
    
    print(f"[dashboard_server] Starting on 127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", timeout_keep_alive=30)
