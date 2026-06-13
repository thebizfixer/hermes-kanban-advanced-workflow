#!/usr/bin/env bash
# verify_anchors.sh — thin wrapper for verify_anchors.py
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/verify_anchors.py" "$@"
