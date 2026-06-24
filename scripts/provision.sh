#!/usr/bin/env bash
# provision.sh — materialize kanban-advanced skills into the project's skills tree.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/hermes_home.sh
source "$SCRIPT_DIR/lib/hermes_home.sh"

KANBAN_WORKFLOW_DIR="${KANBAN_WORKFLOW_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
HERMES_PROJECT_OVERLAY="${HERMES_PROJECT_OVERLAY:-$REPO_ROOT/.hermes/kanban-overrides}"
KANBAN_CONFIG_FILE="${KANBAN_CONFIG_FILE:-$HERMES_PROJECT_OVERLAY/kanban-config.yaml}"

MODE="apply"
PROFILES_ONLY=0
DRIFT_FILES=()
declare -A CONFIG

for arg in "$@"; do
  case "$arg" in
    --check)          MODE="check" ;;
    --dry-run)        MODE="dry-run" ;;
    --profiles-only)  PROFILES_ONLY=1; MODE="check" ;;
    --help|-h)
      grep '^#' "$0" | head -40 | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 1
      ;;
  esac
done

# set -e treats failed [[ ]] tests as fatal; disable for read-only check/dry-run modes.
if [[ "$MODE" == "check" || "$MODE" == "dry-run" ]]; then
  set +e
fi

load_config() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "[provision] No config at $file — substitution skipped."
    return
  fi
  echo "[provision] Loading config from $file"
  while IFS=': ' read -r key value; do
    [[ "$key" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${key// }" ]] && continue
    [[ "$key" =~ ^[[:space:]]*schema_version ]] && key="schema_version"
    value="${value//$'\r'/}"
    value="${value%%#*}"
    value="${value#\"}"
    value="${value%\"}"
    value="${value#\'}"
    value="${value%\'}"
    value="${value%"${value##*[![:space:]]}"}"
    [[ -n "$key" && -n "$value" ]] && CONFIG["$key"]="$value"
  done < "$file"
}

if [[ -f "$KANBAN_CONFIG_FILE" ]]; then
  if ! python3 "$SCRIPT_DIR/validate_config.py" "$KANBAN_CONFIG_FILE"; then
    echo "[provision] Config validation failed — fix overlay before provisioning." >&2
    exit 1
  fi
  load_config "$KANBAN_CONFIG_FILE"
fi

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

WORKER_PROFILE_NAME="${CONFIG[worker_profile]:-kanban-advanced-worker}"
ORCH_PROFILE_NAME="${CONFIG[orchestrator_profile]:-kanban-advanced-orchestrator}"
BUNDLE_PATH="${CONFIG[bundle_path]:-hermes-kanban-advanced-workflow}"
if [[ "$BUNDLE_PATH" != /* ]]; then
  BUNDLE_PATH="$REPO_ROOT/$BUNDLE_PATH"
fi
KANBAN_WORKFLOW_DIR="$BUNDLE_PATH"

declare -A PROFILE_SKILL_SETS
PROFILE_SKILL_SETS["$WORKER_PROFILE_NAME"]="kanban-git kanban-worker kanban-worker-governance"
PROFILE_SKILL_SETS["$ORCH_PROFILE_NAME"]="kanban-advanced kanban-cleanup kanban-notify kanban-orchestrator kanban-orchestrator-governance kanban-planning kanban-postmortem kanban-preflight kanban-reconciliation"

check_profile_skills() {
  local profile="$1"
  local expected_str="${PROFILE_SKILL_SETS[$profile]:-}"
  local profile_home="$HERMES_HOME/profiles/$profile"
  local profile_skills="$profile_home/skills"

  if [[ -z "$expected_str" ]]; then
    echo "[provision] SKIP profile $profile: no skill set configured"
    return
  fi
  if [[ ! -d "$profile_home" ]]; then
    echo "[provision] SKIP profile $profile: home not found ($profile_home)"
    return
  fi
  if [[ ! -d "$profile_skills" ]]; then
    echo "[provision] DRIFT profile $profile: skills dir missing ($profile_skills)"
    DRIFT_FILES+=("$profile_skills")
    return
  fi

  read -ra expected_arr <<< "$expected_str"

  for skill in "${expected_arr[@]}"; do
    local src_file="$BUNDLE_PATH/plugin/skills/$skill/SKILL.md"
    local dst_file="$profile_skills/$skill/SKILL.md"
    if [[ ! -f "$dst_file" ]]; then
      echo "[provision] DRIFT profile $profile: missing skill $skill"
      DRIFT_FILES+=("$dst_file")
    elif [[ -f "$src_file" ]]; then
      if [ "$(hash_file "$src_file")" != "$(hash_file "$dst_file")" ]; then
        echo "[provision] DRIFT profile $profile: stale skill $skill"
        DRIFT_FILES+=("$dst_file")
      fi
    fi
  done

  while IFS= read -r -d '' skill_dir; do
    local skill_name
    skill_name="$(basename "$skill_dir")"
    local found=0
    for expected in "${expected_arr[@]}"; do
      [[ "$skill_name" == "$expected" ]] && found=1 && break
    done
    if [[ $found -eq 0 ]]; then
      echo "[provision] DRIFT profile $profile: unexpected skill '$skill_name' (stale built-in?)"
      DRIFT_FILES+=("$skill_dir")
    fi
  done < <(find "$profile_skills" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null)
}

run_profile_skill_checks() {
  echo "[provision] Checking profile skill isolation..."
  check_profile_skills "$WORKER_PROFILE_NAME"
  check_profile_skills "$ORCH_PROFILE_NAME"
}

if [[ "$PROFILES_ONLY" -eq 1 ]]; then
  run_profile_skill_checks
  if [[ ${#DRIFT_FILES[@]} -gt 0 ]]; then
    echo "[provision] PROFILE CHECK FAILED — ${#DRIFT_FILES[@]} drifted or missing item(s)." >&2
    printf '%s\n' "${DRIFT_FILES[@]}" >&2
    exit 1
  fi
  echo "[provision] PROFILE CHECK PASSED"
  exit 0
fi

SKILLS_OUTPUT_PATH="${CONFIG[skills_output_path]:-$REPO_ROOT/.hermes/skills/devops}"
if [[ "$SKILLS_OUTPUT_PATH" != /* ]]; then
  SKILLS_OUTPUT_PATH="$REPO_ROOT/$SKILLS_OUTPUT_PATH"
fi

substitute_vars() {
  local content="$1"
  for key in "${!CONFIG[@]}"; do
    content="${content//\$\{$key\}/${CONFIG[$key]}}"
  done
  if [[ -z "${CONFIG[trigger_branch]:-}" ]]; then
    # trigger_branch unset — drop lines that still reference the placeholder
    content="$(printf '%s\n' "$content" | grep -v '\${trigger_branch}' || true)"
  fi
  echo "$content"
}

materialize_skill() {
  local src="$1"
  local skill_name dir_name output_dir output_file patch_file content
  skill_name="$(basename "$src" .md)"
  dir_name="$skill_name"
  output_dir="$SKILLS_OUTPUT_PATH/$dir_name"
  output_file="$output_dir/SKILL.md"
  patch_file="$HERMES_PROJECT_OVERLAY/patches/${skill_name}.patch"

  content="$(cat "$src")"
  content="$(substitute_vars "$content")"

  if [[ -f "$patch_file" ]]; then
    local patched
    if patched="$(echo "$content" | patch --posix -p0 -i "$patch_file" 2>&1)"; then
      content="$patched"
    else
      echo "[provision] WARNING: patch $patch_file failed (non-fatal)"
    fi
  fi

  case "$MODE" in
    dry-run) echo "[provision] Would write: $output_file" ;;
    check)
      if [[ ! -f "$output_file" ]]; then
        echo "[provision] MISSING: $output_file"
        DRIFT_FILES+=("$output_file")
      elif [ "$(printf '%s\n' "$content" | sha256sum | awk '{print $1}')" = "$(hash_file "$output_file")" ]; then
        :
      else
        echo "[provision] DRIFT: $output_file"
        DRIFT_FILES+=("$output_file")
      fi
      ;;
    apply)
      mkdir -p "$output_dir"
      printf '%s\n' "$content" > "$output_file"
      echo "[provision] Wrote: $output_file"
      ;;
  esac
}

sync_reference_dir() {
  local src_dir="$1"
  local dst_dir="$2"
  local label="$3"
  [[ -d "$src_dir" ]] || return 0
  mkdir -p "$dst_dir"
  local f base expected current
  for f in "$src_dir"/*.md; do
    [[ -f "$f" ]] || continue
    base="$(basename "$f")"
  case "$MODE" in
      apply)
        cp "$f" "$dst_dir/$base"
        echo "[provision] Copied $label reference: $base → $dst_dir/"
        ;;
      check|dry-run)
        if [[ ! -f "$dst_dir/$base" ]]; then
          echo "[provision] MISSING $label reference: $dst_dir/$base"
          DRIFT_FILES+=("$dst_dir/$base")
        else
          expected="$(hash_file "$f")"
          current="$(hash_file "$dst_dir/$base")"
          if [ "$expected" = "$current" ]; then
            :
          else
            echo "[provision] DRIFT $label reference: $dst_dir/$base"
            DRIFT_FILES+=("$dst_dir/$base")
          fi
        fi
        ;;
    esac
  done
}

copy_all_references() {
  local refs_src="$KANBAN_WORKFLOW_DIR/references"
  local skill_dir skill_name
  for src in "$KANBAN_WORKFLOW_DIR/skills/"*.md; do
    [[ -f "$src" ]] || continue
    skill_name="$(basename "$src" .md)"
    sync_reference_dir "$refs_src" "$SKILLS_OUTPUT_PATH/$skill_name/references" "bundle"
  done
  sync_reference_dir "$HERMES_PROJECT_OVERLAY/references" "$SKILLS_OUTPUT_PATH/kanban-orchestrator/references" "overlay"
  for src in "$KANBAN_WORKFLOW_DIR/skills/"*.md; do
    [[ -f "$src" ]] || continue
    skill_name="$(basename "$src" .md)"
    if [[ -d "$HERMES_PROJECT_OVERLAY/references" ]]; then
      sync_reference_dir "$HERMES_PROJECT_OVERLAY/references" "$SKILLS_OUTPUT_PATH/$skill_name/references" "overlay"
    fi
  done
}

copy_bootstrap() {
  local src="$HERMES_PROJECT_OVERLAY/bootstrap/HERMES_BOOTSTRAP.md"
  local dst="$REPO_ROOT/.hermes/HERMES_BOOTSTRAP.md"
  if [[ ! -f "$src" ]]; then
    return
  fi
  case "$MODE" in
    apply) cp "$src" "$dst"; echo "[provision] Copied bootstrap: .hermes/HERMES_BOOTSTRAP.md" ;;
    check)
      if [[ ! -f "$dst" ]]; then
        echo "[provision] DRIFT: bootstrap $dst"
        DRIFT_FILES+=("$dst")
      elif [ "$(hash_file "$src")" = "$(hash_file "$dst")" ]; then
        :
      else
        echo "[provision] DRIFT: bootstrap $dst"
        DRIFT_FILES+=("$dst")
      fi
      ;;
    dry-run) echo "[provision] Would copy bootstrap → $dst" ;;
  esac
}

write_manifest() {
  [[ "$MODE" == "apply" ]] || return
  local manifest="$SKILLS_OUTPUT_PATH/provision-manifest.json"
  local ts config_hash
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  config_hash="none"
  [[ -f "$KANBAN_CONFIG_FILE" ]] && config_hash="$(hash_file "$KANBAN_CONFIG_FILE")"
  printf '{\n  "provisioned_at": "%s",\n  "config_file": "%s",\n  "config_hash": "%s",\n  "source": "%s",\n  "skills_output_path": "%s"\n}\n' \
    "$ts" "$KANBAN_CONFIG_FILE" "$config_hash" "$KANBAN_WORKFLOW_DIR" "$SKILLS_OUTPUT_PATH" \
    > "$manifest"
  echo "[provision] Manifest: $manifest"
}

echo "[provision] Mode: $MODE"
echo "[provision] Source: $KANBAN_WORKFLOW_DIR/skills/"
echo "[provision] Output: $SKILLS_OUTPUT_PATH/"

for src in "$KANBAN_WORKFLOW_DIR/skills/"*.md; do
  [[ -f "$src" ]] || continue
  materialize_skill "$src"
done

copy_all_references
copy_bootstrap

# ── Sync cron scripts to the path crons resolve ─────────────────────
# Governance scripts live in the bundle's scripts/ dir, but workers and crons
# resolve script="scripts/<name>.sh" relative to $HERMES_HOME/scripts/.
# Sync them so dispatch does not pick up stale copies.
CRON_SCRIPTS_DIR="${HERMES_HOME}/scripts"
mkdir -p "$CRON_SCRIPTS_DIR"
for script in auto_unblock.sh auto_unblock.py board_keeper.sh board_keeper.py coding_agent_invoke.sh worktree_setup.sh install_pre_push_hook.sh install_pre_commit_hook.sh; do
    if [ -f "${BUNDLE_PATH}/scripts/${script}" ]; then
        case "$MODE" in
            apply)
                cp "${BUNDLE_PATH}/scripts/${script}" "${CRON_SCRIPTS_DIR}/${script}"
                echo "[provision] Synced cron script: ${script} → ${CRON_SCRIPTS_DIR}/"
                ;;
            check|dry-run)
                if [[ ! -f "${CRON_SCRIPTS_DIR}/${script}" ]]; then
                    echo "[provision] MISSING cron script: ${CRON_SCRIPTS_DIR}/${script}"
                    DRIFT_FILES+=("${CRON_SCRIPTS_DIR}/${script}")
                elif [ "$(hash_file "${BUNDLE_PATH}/scripts/${script}")" != "$(hash_file "${CRON_SCRIPTS_DIR}/${script}")" ]; then
                    echo "[provision] DRIFT cron script: ${CRON_SCRIPTS_DIR}/${script}"
                    DRIFT_FILES+=("${CRON_SCRIPTS_DIR}/${script}")
                fi
                ;;
        esac
    fi
done

# coding_agent_invoke.sh sources $HERMES_HOME/scripts/lib/coding_agent_env.sh
LIB_SCRIPTS_DIR="${CRON_SCRIPTS_DIR}/lib"
mkdir -p "$LIB_SCRIPTS_DIR"
for libscript in coding_agent_env.sh coding_agent_auth_lock.sh kanban_config.sh kanban_bundle.sh worktree_include.sh plan_paths.sh plan_paths.py kanban_cli_parse.sh kanban_logs.sh plan_parse.py cli_output_parse.py governance_profile.py bash_counters.sh card_body.py presentation_acceptance.py verify_optimization_presentation.py; do
    if [ -f "${BUNDLE_PATH}/scripts/lib/${libscript}" ]; then
        case "$MODE" in
            apply)
                cp "${BUNDLE_PATH}/scripts/lib/${libscript}" "${LIB_SCRIPTS_DIR}/${libscript}"
                echo "[provision] Synced lib script: lib/${libscript} → ${LIB_SCRIPTS_DIR}/"
                ;;
            check|dry-run)
                if [[ ! -f "${LIB_SCRIPTS_DIR}/${libscript}" ]]; then
                    echo "[provision] MISSING lib script: ${LIB_SCRIPTS_DIR}/${libscript}"
                    DRIFT_FILES+=("${LIB_SCRIPTS_DIR}/${libscript}")
                elif [ "$(hash_file "${BUNDLE_PATH}/scripts/lib/${libscript}")" != "$(hash_file "${LIB_SCRIPTS_DIR}/${libscript}")" ]; then
                    echo "[provision] DRIFT lib script: ${LIB_SCRIPTS_DIR}/${libscript}"
                    DRIFT_FILES+=("${LIB_SCRIPTS_DIR}/${libscript}")
                fi
                ;;
        esac
    fi
done
write_manifest

# ── Sync prompts (orchestrator SOUL.md, worker instructions) ──────────
PROMPTS_SRC="${KANBAN_WORKFLOW_DIR}/prompts"
PROMPTS_DST="${SKILLS_OUTPUT_PATH}/prompts"
if [ -d "$PROMPTS_SRC" ]; then
    mkdir -p "$PROMPTS_DST"
    for prompt_file in "$PROMPTS_SRC"/*.md; do
        [ -f "$prompt_file" ] || continue
        base="$(basename "$prompt_file")"
        case "$MODE" in
            apply)
                cp "$prompt_file" "$PROMPTS_DST/$base"
                echo "[provision] Synced prompt: ${base} → ${PROMPTS_DST}/"
                ;;
            check|dry-run)
                if [[ ! -f "${PROMPTS_DST}/${base}" ]]; then
                    echo "[provision] MISSING prompt: ${PROMPTS_DST}/${base}"
                    DRIFT_FILES+=("${PROMPTS_DST}/${base}")
                elif [ "$(hash_file "$prompt_file")" != "$(hash_file "${PROMPTS_DST}/${base}")" ]; then
                    echo "[provision] DRIFT prompt: ${PROMPTS_DST}/${base}"
                    DRIFT_FILES+=("${PROMPTS_DST}/${base}")
                fi
                ;;
        esac
    done
fi


# ── Post-sync verification: confirm critical worker patches survived ──
# skill_manage patches are not always persisted — verify marker strings.
WORKER_SKILL="${SKILLS_OUTPUT_PATH}/kanban-worker/SKILL.md"
if [ -f "$WORKER_SKILL" ] && [[ "$MODE" == "apply" || "$MODE" == "check" ]]; then
    if ! grep -q "coding_agent_invoke.sh smoke" "$WORKER_SKILL" 2>/dev/null; then
        echo "[provision] WARNING: coding-agent smoke patch missing from $WORKER_SKILL"
        echo "[provision] This patch prevents false-positive [unauthenticated] worker blocks."
    fi
    if ! grep -q "workspace-trusted" "$WORKER_SKILL" 2>/dev/null; then
        echo "[provision] WARNING: Workspace trust pre-provisioning patch missing from $WORKER_SKILL"
        echo "[provision] This patch prevents agent hang on interactive trust prompt."
    fi
fi

if [[ "$MODE" == "check" || "$MODE" == "apply" ]]; then
  run_profile_skill_checks
fi

if [[ "$MODE" == "check" ]]; then
  set -e
  if [[ ${#DRIFT_FILES[@]} -gt 0 ]]; then
    echo "[provision] CHECK FAILED — ${#DRIFT_FILES[@]} drifted or missing file(s)." >&2
    printf '%s\n' "${DRIFT_FILES[@]}" >&2
    exit 1
  fi
  echo "[provision] CHECK PASSED"
  exit 0
fi

echo "[provision] Done."
