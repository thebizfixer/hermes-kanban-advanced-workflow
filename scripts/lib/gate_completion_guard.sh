#!/usr/bin/env bash
# gate_completion_guard.sh — detect resurrected gates (completed then unblocked)
# Exit 0: no resurrected gates found. Exit 1: resurrected gates detected.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=hermes_home.sh
source "$SCRIPT_DIR/hermes_home.sh" 2>/dev/null || {
    HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
}

DB="${HERMES_HOME}/kanban.db"
if [[ ! -f "$DB" ]]; then
    echo "PASS: no kanban.db (no gates to resurrect)"
    exit 0
fi

RESURRECTED=$(python3 - "$DB" <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.row_factory = sqlite3.Row
rows = db.execute(
    "SELECT id, title FROM tasks WHERE (title LIKE 'Gate — %' OR title LIKE 'Gate:%')"
    " AND completed_at IS NOT NULL AND status NOT IN ('done', 'archived')"
).fetchall()
for r in rows:
    print(f"  {r['id']} [{r['title'][:60]}]")
sys.exit(1 if rows else 0)
PY
)

if [[ -n "$RESURRECTED" ]]; then
    echo "FAIL: Resurrected gates detected:"
    echo "$RESURRECTED"
    echo "Archive these gates before proceeding: hermes kanban archive <id>"
    exit 1
fi

echo "PASS: no resurrected gates"
