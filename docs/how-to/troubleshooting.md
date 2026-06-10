# How to: troubleshoot

```bash
hermes kanban list
hermes kanban show <task_id>
python hermes-kanban-advanced-workflow/scripts/kanban_recover.py --list
bash hermes-kanban-advanced-workflow/scripts/preflight.sh
```

## Frequent issues

| Symptom | Fix |
| --- | --- |
| PR001 — no `config.yaml` on profile | Copy template into profile dir from `$HERMES_HOME` |
| A001 — attestation missing | Re-run preflight + `kanban_attestation.py` |
| torn-extend / dispatch stuck | `hermes gateway restart`; see `references/sqlite-kanban-db-recovery.md` |
| Plugin not loading | `hermes plugins list`; restart Hermes after install |
| Working branch reset to `main` after `hermes update` | Restore in `kanban-config.yaml` or dashboard **Save**; set `KANBAN_PROJECT_ROOT`; re-init now preserves branches — [wiki/troubleshooting.md](../../wiki/troubleshooting.md) |
| Plugin update / `git pull`: local changes would be overwritten | Install dir is upstream mirror only — **Update Plugin** auto-resets; or `git reset --hard HEAD && git clean -fd` in `plugin_install_path` — [wiki/troubleshooting.md](../../wiki/troubleshooting.md) |
| Cross-mount / dual clone | `docs/examples/cross-mount-filesystems.md` |

Full symptom list: [wiki/troubleshooting.md](../../wiki/troubleshooting.md).
