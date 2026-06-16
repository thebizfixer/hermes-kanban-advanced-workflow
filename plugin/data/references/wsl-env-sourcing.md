# WSL `.env` sourcing

When the **WSL repo** lacks `.env` but Windows side holds credentials.

## Read-only probe (WSL)

```bash
WIN_ENV="/mnt/c/path/to/project/.env"
if [ -f "$WIN_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$WIN_ENV"
  set +a
fi
```

Prefer a **symlink or copy** into the WSL repo root for gateway workers — card worktrees only see `.env` if listed in `.worktreeinclude`.

## Gateway / systemd

Set `HOME=` and API keys in the **gateway host** environment (WSL `~/.bashrc`, systemd `Environment=`, or project `.env` on the Linux filesystem).

## Do not

- Commit `.env` with secrets.
- Assume Hermes bootstrap copied application secrets into worktrees — see `operator-provisioning.md`.
