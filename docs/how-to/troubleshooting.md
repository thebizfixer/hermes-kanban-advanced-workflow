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
| Profiles have default Hermes skills after bootstrap | [wiki/bootstrap.md](../../wiki/bootstrap.md) — `HERMES_HOME` mismatch or re-bootstrap after Update Plugin |
| Plugin update / `git pull`: local changes would be overwritten | Install dir is upstream mirror only — **Update Plugin** auto-resets; or `git reset --hard HEAD && git clean -fd` in `plugin_install_path` — [wiki/troubleshooting.md](../../wiki/troubleshooting.md) |
| Cross-mount / dual clone | `docs/examples/cross-mount-filesystems.md` |
| Coding agent smoke failed / E020 (dashboard green, worker blocks) | Worktree smoke: `coding_agent_invoke.sh smoke`; Cursor needs `--trust` in worktree — [wiki/troubleshooting.md](../../wiki/troubleshooting.md) |
| Cursor `agent status` OK but smoke fails / `[escalation:coding_agent:auth]` | Often missing `HOME` in gateway workers, not stale OAuth — see [wiki/troubleshooting.md](../../wiki/troubleshooting.md) |
| Bootstrap passed but preflight blocks on coding agent | Bootstrap smoke is **advisory** — add API keys or vendor login, run `check_coding_agent_cli.py` — [coding-agent auth](../../plugin/data/references/coding-agent-auth.md) |
| Dashboard profile yellow "model unreachable" (not coding agent) | Hermes provider token/model for dispatch profile — re-auth provider; separate from Cursor CLI — [wiki/troubleshooting.md](../../wiki/troubleshooting.md) |
| Handoff/preflight hangs on coding-agent CLI smoke | Fast probe is 15s; fix auth or `PREFLIGHT_SKIP_CODING_AGENT_CLI=1` — [wiki/troubleshooting.md](../../wiki/troubleshooting.md) |
| Tests pass locally but fail in card worktree | Add `.env` / `.venv/` / `node_modules/` to `.worktreeinclude` — [operator provisioning](../../plugin/data/references/operator-provisioning.md) |
| `required_secrets` preflight fails | Fill vars in main repo `.env`; mirror to worktree if coding agent runs those tests |

Full symptom list: [wiki/troubleshooting.md](../../wiki/troubleshooting.md).
