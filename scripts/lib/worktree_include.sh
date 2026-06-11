#!/usr/bin/env bash
# worktree_include.sh — copy .worktreeinclude paths into a kanban card worktree.
#
# Source from worktree_setup.sh:
#   source "$SCRIPT_DIR/lib/worktree_include.sh"
#   sync_worktree_include "$REPO_ROOT" "$WORKTREE_PATH"

_is_safe_worktree_include_path() {
  local p="$1"
  case "$p" in
    /*|..|../*|*/..|*/../*) return 1 ;;
  esac
  return 0
}

sync_worktree_include() {
  local repo_root="$1" worktree_path="$2"
  local include_file="$repo_root/.worktreeinclude"
  [ -f "$include_file" ] || return 0

  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -n "$line" ] || continue
    if ! _is_safe_worktree_include_path "$line"; then
      echo "[kanban-governance] WARNING: skipping unsafe .worktreeinclude path: $line" >&2
      continue
    fi

    local src="$repo_root/$line"
    local dst="$worktree_path/$line"
    [ -e "$src" ] || continue

    if [ -d "$src" ]; then
      mkdir -p "$dst"
      cp -a "$src/." "$dst/" 2>/dev/null || cp -r "$src"/* "$dst/" 2>/dev/null || true
    else
      mkdir -p "$(dirname "$dst")"
      cp -a "$src" "$dst" 2>/dev/null || cp "$src" "$dst"
    fi
    echo "[kanban-governance] worktreeinclude: $line" >&2
  done < "$include_file"
}
