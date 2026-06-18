#!/usr/bin/env bash
# audit_anchors.sh — thin wrapper for audit_anchors.py
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/audit_anchors.py" "$@"
