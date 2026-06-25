"""dashboard_server_restart.py — Graceful sidecar restart without force-kill.

Usage: python3 scripts/dashboard_server_restart.py

- Sends graceful shutdown (SIGTERM / WM_CLOSE) to the current sidecar process
- Waits for it to exit (up to 10s)
- Only force-kills if it won't exit after timeout
- Starts a fresh instance
- Safe for gateway — targets only the sidecar PID, not all Python processes
"""
import os
import sys
import time
import signal
import subprocess
from pathlib import Path

PORT = os.environ.get("KA_DASHBOARD_PORT", "18900")
HEALTH_URL = f"http://127.0.0.1:{PORT}/health"

# Find plugin root (this script is at <plugin_root>/scripts/)
script_dir = Path(__file__).resolve().parent
plugin_root = script_dir.parent
server_script = plugin_root / "scripts" / "dashboard_server.py"

def get_sidecar_pid():
    """Get the sidecar PID from its health endpoint."""
    try:
        import urllib.request
        import json
        req = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            return data.get("pid")
    except Exception:
        return None

def is_port_listening():
    """Check if anything is listening on the dashboard port."""
    try:
        import urllib.request
        req = urllib.request.Request(HEALTH_URL, method="GET")
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False

def graceful_kill(pid):
    """Kill a process gracefully (WM_CLOSE on Windows, SIGTERM on Unix)."""
    try:
        if sys.platform == "win32":
            # taskkill without /F sends WM_CLOSE → Python can handle as SIGTERM
            subprocess.run(
                ["cmd.exe", "/c", f"taskkill /PID {pid}"],
                capture_output=True, timeout=10
            )
        else:
            os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False

def force_kill(pid):
    """Last resort: force kill (only if graceful shutdown timed out)."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["cmd.exe", "/c", f"taskkill /PID {pid} /F"],
                capture_output=True, timeout=5
            )
        else:
            os.kill(pid, signal.SIGKILL)
        return True
    except Exception:
        return False

def wait_for_exit(pid, timeout=30):
    """Wait for a process to exit gracefully."""
    import psutil
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            proc = psutil.Process(pid)
            if not proc.is_running():
                return True
        except psutil.NoSuchProcess:
            return True
        time.sleep(0.5)
    return False

def main():
    print("[dashboard_restart] Checking current sidecar state...")

    # 1. Get current PID from health endpoint
    current_pid = get_sidecar_pid()

    if current_pid is None:
        print("[dashboard_restart] No running sidecar detected (health check failed)")
        if is_port_listening():
            print("[dashboard_restart] WARNING: Port is occupied but health check fails — stale process likely")
            # Try to find PID from netstat
            try:
                result = subprocess.run(
                    ["cmd.exe", "/c", f'netstat -ano | findstr :{PORT} | findstr LISTENING'],
                    capture_output=True, text=True, timeout=5
                )
                if result.stdout.strip():
                    parts = result.stdout.strip().split()
                    stale_pid = int(parts[-1])
                    print(f"[dashboard_restart] Found stale PID {stale_pid} on port {PORT}")
                    current_pid = stale_pid
            except Exception:
                pass

    if current_pid is not None:
        print(f"[dashboard_restart] Gracefully shutting down PID {current_pid}...")
        graceful_kill(current_pid)

        # Wait for graceful exit (up to 30s)
        if wait_for_exit(current_pid, timeout=30):
            print(f"[dashboard_restart] PID {current_pid} exited gracefully")
        else:
            print(f"[dashboard_restart] PID {current_pid} didn't exit — force-killing...")
            force_kill(current_pid)
            time.sleep(2)

    # ── Mandatory cooldown: let gateway close its connections ──
    COOLDOWN = int(os.environ.get("KA_RESTART_COOLDOWN", "30"))
    print(f"[dashboard_restart] Cooling down {COOLDOWN}s to let gateway recover...")
    for i in range(COOLDOWN, 0, -5):
        print(f"[dashboard_restart]   {i}s...")
        time.sleep(min(5, i))

    # Verify port is free
    deadline = time.time() + 5
    while time.time() < deadline:
        if not is_port_listening():
            break
        time.sleep(0.5)
    else:
        print(f"[dashboard_restart] WARNING: Port {PORT} still occupied after waiting")
        # Proceed anyway — PID lock in dashboard_server.py handles duplicates

    # 3. Start fresh sidecar
    print("[dashboard_restart] Starting fresh sidecar...")
    subprocess.Popen(
        [sys.executable, str(server_script)],
        cwd=str(plugin_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 4. Wait for health check
    deadline = time.time() + 10
    while time.time() < deadline:
        if is_port_listening():
            new_pid = get_sidecar_pid()
            print(f"[dashboard_restart] Sidecar restarted successfully (PID {new_pid})")
            return 0
        time.sleep(0.5)

    print("[dashboard_restart] WARNING: Sidecar started but health check still failing")
    return 1

if __name__ == "__main__":
    sys.exit(main())
