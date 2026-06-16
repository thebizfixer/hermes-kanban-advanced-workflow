# SQLite kanban.db recovery

**Symptom:** `torn-extend detected: page count mismatch` or dispatcher promotes zero triage cards despite completed parents.

## Steps

1. **Restart gateway** (reopens DB, often heals WAL torn-extend):

```bash
hermes gateway restart
```

2. **Integrity check:**

```bash
sqlite3 "$HERMES_HOME/kanban.db" "PRAGMA integrity_check;"
```

3. **Stale init lock** (preflight removes automatically):

```bash
rm -f "$HERMES_HOME/kanban.db.init.lock"
```

4. **Prevention:** stagger card creates (≥1s apart, pause every 5 cards); avoid rapid archive→recreate.

If integrity still fails, restore from backup or export board state before rebuilding `kanban.db`.
