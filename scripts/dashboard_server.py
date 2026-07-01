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

# Capture startup metadata for sidecar staleness detection
START_TIME = time.time()
try:
    import subprocess as _sp
    _r = _sp.run(
        ["git", "log", "-1", "--format=%H"],
        capture_output=True, text=True, cwd=str(PLUGIN_ROOT), timeout=5
    )
    COMMIT = _r.stdout.strip() if _r.returncode == 0 else "unknown"
except Exception:
    COMMIT = "unknown"

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
    return {"status": "ok", "pid": os.getpid(), "started_at": START_TIME, "commit": COMMIT}

app.include_router(router, prefix="/api/plugins/kanban-advanced")

# ── Plugin router discovery (H3 extension hook) ───────────────────────────────
# Discover installed plugins and mount their dashboard FastAPI routers.
# Uses hermes plugins list --json + plugin.yaml dashboard.router metadata.
def _discover_plugin_routers():
    """Mount dashboard routers declared in each plugin's plugin.yaml metadata."""
    import importlib.util
    import json
    import logging
    import subprocess

    try:
        import yaml
    except ImportError:
        return

    log = logging.getLogger("dashboard_server")
    try:
        result = subprocess.run(
            ["hermes", "plugins", "list", "--json"],
            capture_output=True, text=True, encoding="utf-8-sig", errors="replace", timeout=10,
        )
        if result.returncode != 0:
            return
        plugins = json.loads(result.stdout)
    except Exception:
        return

    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    plugin_dirs: dict[str, Path] = {}

    def _scan_plugins(base: Path, depth: int = 0) -> None:
        if not base.is_dir() or depth > 2:
            return
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            manifest = child / "plugin.yaml"
            if manifest.exists():
                try:
                    meta = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
                    plugin_dirs[meta.get("name", child.name)] = child
                except Exception:
                    pass
            elif depth < 2:
                _scan_plugins(child, depth + 1)

    _scan_plugins(hermes_home / "plugins")

    for entry in plugins if isinstance(plugins, list) else []:
        name = entry.get("name", "")
        root = plugin_dirs.get(name)
        if not name or not root:
            continue
        try:
            meta = yaml.safe_load((root / "plugin.yaml").read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        dash = meta.get("dashboard")
        if not isinstance(dash, dict):
            continue
        router_rel = dash.get("router")
        if not router_rel:
            continue
        prefix = dash.get("prefix") or f"/api/plugins/{name}"
        router_path = (root / router_rel).resolve()
        try:
            router_path.relative_to(root.resolve())
        except ValueError:
            log.warning("Plugin %s: refusing router path outside plugin root", name)
            continue
        if not router_path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"plugin_{name}_routes", router_path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            router_obj = getattr(mod, "router", None)
            if router_obj is None:
                continue
            app.include_router(router_obj, prefix=prefix)
            log.info("Mounted dashboard routes for plugin: %s", name)
        except Exception as exc:
            log.warning("Could not mount router for plugin %s: %s", name, exc)

_discover_plugin_routers()


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
