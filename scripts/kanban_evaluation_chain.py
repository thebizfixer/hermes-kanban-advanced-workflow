#!/usr/bin/env python3
"""
kanban_evaluation_chain.py — Deterministic evaluation chain for kanban task completion.

AEP Deterministic Adjudication Lattice (DAL) pattern applied to kanban-workflow.
Each step returns (allow: bool, error_code: str | None).
The chain stops at the first DENY.

Usage:
    python kanban_evaluation_chain.py <task_id> <workspace_path>
    python kanban_evaluation_chain.py <task_id> <workspace_path> --baseline HEAD~2

Environment:
    KANBAN_PRE_AGENT_SHA   Baseline commit for diff (default: HEAD~1)
    KANBAN_TOKEN_LOG       Path to token log (default: ~/.hermes/kanban/tokens.jsonl)
    KANBAN_LATTICE_MEMORY  Path to lattice memory file (default: .hermes/kanban/lattice-memory.json)
    KANBAN_REGISTRY_PATH   Path to error-codes.yaml (default: hermes-kanban-advanced-workflow/registry/error-codes.yaml)
"""

import subprocess
import sys
import json
import os
import shlex
import hashlib
import datetime
import re
import yaml
from pathlib import Path
from typing import Tuple, Optional, List


# ── Error registry loader ──────────────────────────────────────────────

def load_error_registry(registry_path: str) -> dict:
    """Load canonical error codes from registry YAML. Falls back to built-in defaults."""
    try:
        with open(registry_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return {c["code"]: c for c in (data.get("codes") or {}).values()}
    except Exception:
        pass
    # Built-in fallback (compact subset)
    return {
        "E001_FILE_NOT_IN_DIFF": {"severity": "error", "description": "File has zero changes in diff"},
        "E002_UNLISTED_FILE_CHANGE": {"severity": "warning", "description": "Agent modified unlisted file"},
        "E003_TEST_FAILURE": {"severity": "error", "description": "Tests returned non-zero"},
        "E004_COMMIT_MISMATCH": {"severity": "error", "description": "Commit message mismatch"},
        "E005_TOKEN_LOG_MISSING": {"severity": "warning", "description": "Token log missing (superseded by E018)"},
        "E006_ZERO_OUTPUT": {"severity": "error", "description": "Zero diff on all files"},
        "E013_EVALUATION_CHAIN_MISSING": {"severity": "error", "description": "Chain script missing"},
        "E018_TOKEN_NOT_EXACT": {"severity": "error", "description": "Token log entry not exact — missing, wrong task_id, invalid source, or zero counts. Valid sources: agent, estimated, hermes_insights."},
        "E020_AGENT_OUTPUT_UNPARSEABLE": {"severity": "error", "description": "Agent output file not found, empty, or unparseable. JSON with usage block preferred; text-only output accepted for non-JSON agents."},
        "E019_DESTRUCTIVE_GIT_OP": {"severity": "error", "description": "Destructive git operation detected (checkout --theirs/--ours or reset --hard) — human teams resolve per-hunk"},
        "E021_ACCEPTANCE_TEST_MISSING": {"severity": "error", "description": "Acceptance names test files not present in git diff — worker self-certified without shipping tests"},
        "E022_DOCS_STALE_MARKERS": {"severity": "error", "description": "Docs Verify: rg commands matched stale markers (pending, [new], TODO) against HEAD — docs not reconciled after implementation"},
        "E023_REPEATED_IDENTICAL_ERROR": {"severity": "error", "description": "Identical error from prior run — lattice memory hit. Escalate, do not retry."},
    }


# ── Card body parser (SSOT: scripts/lib/card_body.py) ──────────────────

_LIB = os.path.join(os.path.dirname(__file__), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)
from card_body import (  # noqa: E402
    find_prior_commit,
    is_verification_deploy,
    is_verification_only,
    parse_card_body,
)


# ── Scope violation logger ─────────────────────────────────────────────

def _log_scope_violations(task_id: str, files_reverted: list[str], workspace: str) -> None:
    """Append scope violation entries to plan-level log for postmortem reconciliation."""
    if not task_id or not files_reverted:
        return
    log_path = Path(workspace) / ".hermes" / "kanban" / "logs" / "scope_violations.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "task_id": task_id,
        "files_reverted": files_reverted,
        "count": len(files_reverted),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ── Lattice memory (AEP attractor pattern) ─────────────────────────────

def load_lattice_memory(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"entries": []}


def save_lattice_memory(path: str, memory: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, default=str)


def compute_attractor_hash(files: List[str], tests_cmd: str, workspace: str) -> str:
    """Compute hash over file paths + test command for attractor matching."""
    hasher = hashlib.sha256()
    for f in sorted(files):
        hasher.update(f.encode())
        try:
            filepath = os.path.join(workspace, f)
            if os.path.exists(filepath):
                with open(filepath, "rb") as fh:
                    hasher.update(fh.read())
        except Exception:
            hasher.update(b"UNREADABLE")
    hasher.update(tests_cmd.encode())
    return hasher.hexdigest()[:16]


def compute_workspace_hash(workspace: str) -> str:
    """Hash of git tree for workspace state detection."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD:."],
            capture_output=True, text=True, cwd=workspace, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]
    except Exception:
        pass
    return "unknown"


def _resolve_project_root(workspace: str) -> str:
    """Walk up from workspace to find project root (has .hermes/kanban-overrides/kanban-config.yaml)."""
    d = os.path.abspath(workspace)
    for _ in range(10):
        cfg = os.path.join(d, ".hermes", "kanban-overrides", "kanban-config.yaml")
        if os.path.isfile(cfg):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return ""


def find_attractor(memory: dict, files: List[str], tests_cmd: str, workspace: str) -> Optional[dict]:
    target_hash = compute_attractor_hash(files, tests_cmd, workspace)
    for entry in memory.get("entries", []):
        if entry.get("attractor_hash") == target_hash and entry.get("steps_passed") == 6:
            return entry
    return None


# ── Evaluation steps ───────────────────────────────────────────────────

def resolve_diff_baseline(baseline: str, workspace: str) -> str:
    """Resolve git diff left-hand ref (A in A..HEAD)."""
    if baseline.startswith("merge-base:"):
        ref = baseline.split(":", 1)[1]
        result = subprocess.run(
            ["git", "merge-base", "HEAD", ref],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=workspace,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    if ".." in baseline:
        return baseline.split("..", 1)[0]
    return baseline


def _effective_baseline(baseline: str) -> str:
    override = os.environ.get("KANBAN_EVAL_BASELINE", "").strip()
    return override or baseline


def _diff_range(baseline: str, workspace: str) -> str:
    """Return git diff range (A..HEAD or explicit A..B)."""
    effective = _effective_baseline(baseline)
    if ".." in effective:
        return effective
    base = resolve_diff_baseline(effective, workspace)
    return f"{base}..HEAD"


def _card_pre_existing(card_body: str) -> bool:
    return bool(re.search(r"(?m)^pre_existing:\s*true\s*$", card_body, re.IGNORECASE))


def step_1_file_compliance(
    files: List[str],
    baseline: str,
    workspace: str,
    commit_line: str = "",
    card_body: str = "",
    working_branch: str = "main",
) -> Tuple[bool, Optional[str]]:
    """Every file in card Files: must have >0 changes in git diff (or prior commit)."""
    if not files:
        return True, None
    files = [f.strip().rstrip(".") for f in files if f.strip()]
    diff_range = _diff_range(baseline, workspace)

    if _card_pre_existing(card_body) and files:
        mb = subprocess.run(
            ["git", "merge-base", "HEAD", f"origin/{working_branch}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=workspace,
        )
        if mb.returncode == 0 and mb.stdout.strip():
            mb_range = f"{mb.stdout.strip()}..HEAD"
            mb_result = subprocess.run(
                ["git", "diff", "--stat=200", mb_range],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=workspace,
            )
            for f in files:
                if f in mb_result.stdout:
                    continue
                return False, "E001_FILE_NOT_IN_DIFF"
            print("[E001] ALLOW — pre_existing (merge-base diff)")
            return True, None

    result = subprocess.run(
        ["git", "diff", "--stat=200", diff_range],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=workspace,
    )
    for f in files:
        if f in result.stdout:
            continue
        prior = find_prior_commit(
            commit_line, files, workspace, resolve_diff_baseline(_effective_baseline(baseline), workspace)
        )
        if prior:
            print(f"[E001] ALLOW — already_committed:{prior[:8]}")
            continue
        return False, "E001_FILE_NOT_IN_DIFF"
    return True, None


def step_2_unlisted_changes(files: List[str], baseline: str, workspace: str, task_id: str = "") -> Tuple[bool, Optional[str]]:
    """Any modified file not in Files: gets reverted."""
    diff_range = _diff_range(baseline, workspace)
    result = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=workspace,
    )
    unlisted = []
    for f in result.stdout.strip().split("\n"):
        f = f.strip()
        if f and f not in files and not f.startswith(".hermes/"):
            unlisted.append(f)
    if unlisted:
        revert_failures = []
        for f in unlisted:
            result = subprocess.run(
                ["git", "checkout", "--", f],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                cwd=workspace,
            )
            if result.returncode != 0:
                revert_failures.append(f)
                print(f"[E002] REVERT FAILED for unlisted file: {f} — {result.stderr.strip()[:200]}")
            else:
                print(f"[E002] Reverted unlisted change: {f}")
        if revert_failures:
            print(f"[E002] DENY: {len(revert_failures)} unlisted file(s) could not be reverted")
            return False, "E002_REVERT_FAILED"
        # Double-check: verify no unlisted changes remain
        result2 = subprocess.run(
            ["git", "diff", "--name-only", diff_range],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            cwd=workspace,
        )
        still_unlisted = [
            f.strip() for f in result2.stdout.strip().split("\n")
            if f.strip() and f.strip() not in files and not f.strip().startswith(".hermes/")
        ]
        if still_unlisted:
            print(f"[E002] DENY: {len(still_unlisted)} unlisted file(s) remain after revert: {still_unlisted}")
            return False, "E002_UNLISTED_FILE_CHANGE"
        # Log scope violations for postmortem reconciliation
        _log_scope_violations(task_id, unlisted, workspace)
        return True, None
    return True, None


def step_impl_before_test(
    files: List[str], card_body: str, workspace: str, baseline: str
) -> Tuple[bool, Optional[str]]:
    """Block test-only card when Spec references production file with zero diff (unless TDD: allowed)."""
    if re.search(r"TDD:\s*allowed", card_body, re.I):
        return True, None
    norm = [f.replace("\\", "/") for f in (files or []) if f]
    if not norm or not all("test" in f.lower() for f in norm):
        return True, None
    _lib_fa = os.path.join(os.path.dirname(__file__), "lib")
    if _lib_fa not in sys.path:
        sys.path.insert(0, _lib_fa)
    from final_audit import file_has_diff, git_changed_paths  # noqa: E402

    changed = git_changed_paths(baseline, Path(workspace))
    for m in re.finditer(r"`([^`]+\.(?:py|ts|tsx|js|sh))`", card_body):
        ref = m.group(1).replace("\\", "/")
        if "test" in ref.lower() or ref in norm:
            continue
        full = Path(workspace) / ref
        if not full.is_file():
            continue
        if ref not in changed and not file_has_diff(ref, baseline, Path(workspace)):
            print(f"[E003] impl_before_test_missing: {ref} referenced but no diff")
            return False, "E003_IMPL_BEFORE_TEST_MISSING"
    return True, None


def step_3_tests_pass(tests_cmd: str, workspace: str, files: list | None = None) -> Tuple[bool, Optional[str]]:
    """Run Tests: command. All must pass. Detects common silent failures:
    - 'no tests ran' / 'collected 0 items'
    - Import errors (ModuleNotFoundError, ImportError)
    - Syntax errors in code under test
    - Missing test dependencies (pytest not found)
    - doc: prefix — delegated to verify_doc_tests (no shell)
    - code: prefix — strip prefix and run remainder as shell
    """
    if not tests_cmd:
        return True, None  # No tests specified — allowed for non-code cards
    cmd = tests_cmd.strip()
    if cmd.startswith("doc:"):
        _LIB_FA = os.path.join(os.path.dirname(__file__), "lib")
        if _LIB_FA not in sys.path:
            sys.path.insert(0, _LIB_FA)
        from final_audit import verify_doc_tests  # noqa: E402

        ok, err = verify_doc_tests(cmd, workspace, files or [])
        if not ok:
            print(f"[E003] Doc test failure: {err}")
            return False, "E003_DOC_TEST_FAILURE"
        return True, None
    if cmd.startswith("code:"):
        cmd = cmd[5:].strip()
    result = subprocess.run(
        tests_cmd, shell=True,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=workspace, timeout=300,
    )
    combined = (result.stdout + result.stderr).lower()

    # Detect "no tests actually ran" — the most common silent pass
    if "collected 0 items" in combined or "no tests ran" in combined:
        print(f"[E003] No tests executed: collected 0 items\\n{result.stdout[-500:]}")
        return False, "E003_NO_TESTS_RAN"

    # Detect import/syntax errors that prevent any test from running
    if "modulenotfounderror" in combined or "importerror" in combined:
        print(f"[E003] Import error prevented test execution:\\n{result.stderr[-500:]}")
        return False, "E003_IMPORT_ERROR"

    if "syntaxerror" in combined:
        print(f"[E003] Syntax error in code under test:\\n{result.stderr[-500:]}")
        return False, "E003_SYNTAX_ERROR"

    # Detect missing test runner
    if "pytest: command not found" in combined or "no module named pytest" in combined:
        print(f"[E003] Test runner not available: {result.stderr[-300:]}")
        return False, "E003_TEST_RUNNER_MISSING"

    if result.returncode != 0:
        print(f"[E003] Test failure:\\n{result.stdout[-500:]}\\n{result.stderr[-500:]}")
        return False, "E003_TEST_FAILURE"

    return True, None


def step_4_commit_match(commit_line: str, workspace: str) -> Tuple[bool, Optional[str]]:
    """Last commit message must contain the Commit: line."""
    if not commit_line:
        return True, None  # No commit line specified
    if re.search(r"(?i)N/A|verification only", commit_line):
        return True, None
    result = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=workspace
    )
    if commit_line not in result.stdout:
        print(f"[E004] Commit '{result.stdout.strip()}' != expected '{commit_line}'")
        return False, "E004_COMMIT_MISMATCH"
    return True, None


def step_5_exact_token(token_log_path: str, task_id: str) -> Tuple[bool, Optional[str]]:
    """E018 — Exact token reporting. Replaces the old E005 existence check.

    Verifies:
    1. Token log exists and is non-empty
    2. Most recent entry matches the current task_id (not stale data)
    3. Source is "agent" (exact from CLI JSON) or "estimated" (text-only agents)
    4. Token counts are non-zero (input + output > 0)
    """
    if not os.path.exists(token_log_path):
        return False, "E018_TOKEN_NOT_EXACT"

    try:
        with open(token_log_path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return False, "E018_TOKEN_NOT_EXACT"

    if not lines:
        return False, "E018_TOKEN_NOT_EXACT"

    try:
        last = json.loads(lines[-1].strip())
    except json.JSONDecodeError:
        return False, "E018_TOKEN_NOT_EXACT"

    # Verify this entry belongs to the current card
    if last.get("task_id", "") != task_id:
        print(
            f"[E018] task_id mismatch: log={last.get('task_id')} != current={task_id}"
        )
        return False, "E018_TOKEN_NOT_EXACT"

    # Verify source is "agent" (exact from CLI JSON), "estimated" (text-only agents),
    # or "hermes_insights" (authoritative metering via Hermes insights delta)
    source = last.get("source", "")
    if source not in ("agent", "estimated", "hermes_insights"):
        print(f"[E018] source={source} — must be 'agent', 'estimated', or 'hermes_insights'")
        return False, "E018_TOKEN_NOT_EXACT"

    # Verify at least input tokens are non-zero
    # For hermes_insights: read from 'agent' or 'hermes' section
    # For agent/estimated: read from 'cursor' section
    total = 0
    if source == "hermes_insights":
        agent_section = last.get("agent", last.get("hermes", {}))
        total = agent_section.get("total", 0)
        if total == 0:
            cursor = last.get("cursor", {})
            total = cursor.get("total", cursor.get("input_tokens", 0) + cursor.get("output_tokens", 0))
    else:
        cursor = last.get("cursor", {})
        total = cursor.get("total", cursor.get("input_tokens", 0) + cursor.get("output_tokens", 0))

    if total == 0:
        print("[E018] token counts are zero across all sections")
        return False, "E018_TOKEN_NOT_EXACT"

    print(f"[E018] {total:,} tokens logged (source={source})")
    return True, None


def step_7_agent_output_capture(task_id: str) -> Tuple[bool, Optional[str]]:
    """E020 — Agent output file captured and parseable.

    Verifies the agent's output was saved to disk. For JSON-output agents
    (Cursor, Claude, Codex, Gemini, Grok) the file must contain a 'usage' block.
    For text-only agents (hermes, aider) the file only needs to exist and be
    non-empty — token estimation is handled by log_invoke_tokens.py.

    Runs before E018 since token data is extracted from this file.
    """
    agent_output_file = (
        Path(
            os.environ.get(
                "KANBAN_TEMP",
                os.environ.get("TMPDIR", os.environ.get("TEMP", "/tmp")),
            )
        )
        / f"agent_output_{task_id}.json"
    )
    if not agent_output_file.exists():
        print(f"[E020] agent output file not found: {agent_output_file}")
        return False, "E020_AGENT_OUTPUT_UNPARSEABLE"

    try:
        data = json.loads(agent_output_file.read_text(encoding="utf-8"))
        if "usage" in data:
            return True, None
        # Valid JSON but no usage block — text-only agent fallback.
        # Accept non-empty file (token estimation happened in log_invoke_tokens.py).
        if agent_output_file.stat().st_size > 0:
            print("[E020] agent output is JSON but missing 'usage' block — text-only agent, accepting")
            return True, None
        print("[E020] agent output is empty JSON")
        return False, "E020_AGENT_OUTPUT_UNPARSEABLE"
    except json.JSONDecodeError:
        # Not JSON — text-only agent output (hermes, aider).
        # Accept non-empty file as long as something was captured.
        if agent_output_file.stat().st_size > 0:
            print("[E020] agent output is text-only (not JSON) — accepting")
            return True, None
        print("[E020] agent output is empty")
        return False, "E020_AGENT_OUTPUT_UNPARSEABLE"


def step_8_no_destructive_git(workspace: str, repo_root: str | None = None) -> Tuple[bool, Optional[str]]:
    """E019 — No destructive git operations in reflog.

    Blocks cards that used checkout --theirs, checkout --ours, or reset --hard
    for conflict resolution. These overwrite ENTIRE files on multi-author code,
    silently dropping unrelated changes.
    """
    result = subprocess.run(
        ["git", "reflog", "--format=%gs", "-20"],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=workspace,
    )
    reflog = result.stdout

    danger_patterns = [
        ("checkout --theirs", "checkout --theirs"),
        ("checkout --ours", "checkout --ours"),
        ("reset --hard", "reset --hard"),
    ]

    for display_name, pattern in danger_patterns:
        if pattern not in reflog:
            continue
        # Skip-list: legitimate reset --hard for project artifact restoration
        if pattern == "reset --hard":
            # Check if all reset --hard lines have the skip-list pattern
            reset_lines = [line for line in reflog.split("\n") if "reset --hard" in line]
            from plan_paths import is_governance_artifact_path  # noqa: E402

            root = repo_root or workspace
            legit_resets = sum(
                1 for line in reset_lines
                if is_governance_artifact_path(line, root) or "docs/" in line
            )
            if legit_resets == len(reset_lines):
                print(f"[E019] Skip-list match: reset --hard for project artifacts")
                continue

        print(f"[E019] Destructive git operation: {display_name}")
        print("[E019] Human teams never use --theirs/--ours on multi-author files.")
        print("[E019] Resolve conflicts per-hunk with git mergetool or manual edit.")
        return False, "E019_DESTRUCTIVE_GIT_OP"

    return True, None


def step_6_zero_output(
    files: List[str],
    baseline: str,
    workspace: str,
    commit_line: str = "",
) -> Tuple[bool, Optional[str]]:
    """At least one Files: file must have >0 diff (or prior commit covers scope)."""
    if not files:
        return True, None
    diff_range = _diff_range(baseline, workspace)
    result = subprocess.run(
        ["git", "diff", "--stat=200", diff_range],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=workspace,
    )
    any_change = any(f in result.stdout for f in files)
    if any_change:
        return True, None
    prior = find_prior_commit(
        commit_line, files, workspace, resolve_diff_baseline(_effective_baseline(baseline), workspace)
    )
    if prior:
        print(f"[E006] ALLOW — already_committed:{prior[:8]}")
        return True, None
    return False, "E006_ZERO_OUTPUT"


def _extract_acceptance_test_refs(card_body: str) -> list[str]:
    """Extract test file/case references from Acceptance: lines.

    Scans for patterns like:
      - `rg 'def test_foo' tests/`
      - `rg 'test_bar' tests/test_baz.py`
      - `tests/test_foo.py`
    Returns list of file paths (relative to workspace root).
    """
    refs: list[str] = []
    in_acceptance = False
    for line in card_body.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("acceptance:") or stripped.lower().startswith(
            "acceptance ("
        ):
            in_acceptance = True
            continue
        # Check for Verify: lines too (docs cards use these)
        if re.match(r"^-?\s*(Verify|verify):\s*", stripped):
            in_acceptance = True
        if not in_acceptance:
            continue
        if stripped and not stripped.startswith("-") and not stripped.startswith("Verify"):
            # Walk out of Acceptance block on non-list, non-Verify line
            if not stripped.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                in_acceptance = False
                continue
        # Extract test file references
        # Pattern 1: rg 'def test_*' tests/<file>
        for m in re.finditer(
            r"(?:rg|grep)\s+['\"].*?test\w*.*?['\"]\s+(tests?/[\w/.\-]+)",
            stripped,
        ):
            refs.append(m.group(1))
        # Pattern 2: bare test file path
        for m in re.finditer(r"\b(tests?/[\w/.\-]+test[\w/.\-]*\.(?:py|ts|tsx|js|sh))\b", stripped):
            refs.append(m.group(1))
        # Pattern 3: backtick-wrapped test file
        for m in re.finditer(r"`(tests?/[\w/.\-]+test[\w/.\-]*\.(?:py|ts|tsx|js|sh))`", stripped):
            refs.append(m.group(1))
    return list(dict.fromkeys(refs))  # dedup preserving order


def step_acceptance_test_coverage(
    card_body: str, baseline: str, workspace: str
) -> Tuple[bool, Optional[str]]:
    """E021 — Assert tests named in Acceptance: actually exist in git diff.

    When an agent's Acceptance block claims new test files/cases were added,
    verify those files appear in the git diff (added or modified). Prevents
    workers from self-certifying acceptance without shipping the tests.
    """
    refs = _extract_acceptance_test_refs(card_body)
    if not refs:
        return True, None

    diff_range = _diff_range(baseline, workspace)
    result = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=workspace,
    )
    changed_files = set(result.stdout.strip().split("\n"))

    missing = [r for r in refs if r not in changed_files]
    # Also check if the file at least exists (was added in prior commits)
    for r in missing[:]:
        full_path = os.path.join(workspace, r)
        if os.path.exists(full_path):
            # File exists but wasn't changed in this diff — check if it's in HEAD
            head_result = subprocess.run(
                ["git", "ls-tree", "HEAD", "--", r],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                cwd=workspace,
            )
            if head_result.stdout.strip():
                # File is in HEAD already — might be acceptable if this is an existing test file
                # being referenced. Only flag if the file has NO test function matching the pattern.
                # For now, allow files that exist in HEAD (conservative).
                missing.remove(r)

    if missing:
        print(f"[E021] Acceptance names test files not in diff: {missing}")
        return False, "E021_ACCEPTANCE_TEST_MISSING"

    print(f"[E021] {len(refs)} acceptance test ref(s) verified in diff")
    return True, None


def step_docs_head_verify(
    card_body: str, workspace: str
) -> Tuple[bool, Optional[str]]:
    """E022 — Run docs card Verify: grep commands against HEAD.

    For cards with Verify: rg bullets in Acceptance, runs those commands
    against the current HEAD (not worktree-at-start). Flags stale markers
    like 'pending', '[new]', 'Current build debt' that indicate docs weren't
    reconciled after implementation.
    """
    verify_commands: list[str] = []
    for line in card_body.split("\n"):
        m = re.match(r"^\s*-\s*\d*\.?\s*(?:Verify|verify):\s*rg\s+(.+)$", line.strip(), re.I)
        if m:
            verify_commands.append(m.group(1).strip())

    if not verify_commands:
        return True, None

    stale_signals = ("pending", "[new]", "Current build debt", "TODO", "FIXME", "not yet")
    found_stale: list[str] = []

    for cmd in verify_commands:
        # cmd is like: 'def test_foo' tests/ or "'pending' docs/"
        # Strip all quotes for cross-platform compatibility (shlex handles them
        # differently on POSIX vs Windows)
        clean = cmd.replace("'", "").replace('"', "").strip()
        # Split into rg args: first token is pattern, rest are paths
        parts = shlex_split_safe(clean)
        if not parts:
            continue
        # Build: rg --no-heading -n <pattern> [paths...]
        rg_args = ["rg", "--no-heading", "-n"]
        rg_args.extend(parts)
        result = subprocess.run(
            rg_args,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            cwd=workspace,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            print(f"[E022] Verify: matched — {cmd[:80]}")
            # Check for stale signal words in matched lines
            for matched_line in result.stdout.split("\n")[:20]:
                line_lower = matched_line.lower()
                for signal in stale_signals:
                    if signal.lower() in line_lower:
                        found_stale.append(f"{signal}: {matched_line.strip()[:120]}")

    if found_stale:
        print(f"[E022] Docs stale markers found: {len(found_stale)}")
        for s in found_stale[:5]:
            print(f"  [E022] {s}")
        return False, "E022_DOCS_STALE_MARKERS"

    print(f"[E022] {len(verify_commands)} Verify: command(s) passed, no stale markers")
    return True, None


def shlex_split_safe(s: str) -> list[str]:
    """shlex.split that returns empty list on parse failure."""
    try:
        return shlex.split(s, posix=(os.name != "nt"))
    except ValueError:
        return []


def step_excessive_churn(
    estimated_lines: int, baseline: str, workspace: str
) -> Tuple[bool, Optional[str]]:
    """E017 — Net line changes must not exceed estimate by >3×.

    Extracts total insertions + deletions from git diff --stat.
    Default estimate: 200 lines (generous for a single-card change).
    """
    diff_range = _diff_range(baseline, workspace)
    result = subprocess.run(
        ["git", "diff", "--shortstat", diff_range],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=workspace,
    )
    # Parse "X files changed, Y insertions(+), Z deletions(-)"
    m = re.search(
        r"(\d+)\s+insertions?\(\+\)[,\s]*(\d+)\s+deletions?\(\-\)",
        result.stdout,
    )
    if not m:
        return True, None  # no changes yet or unparseable — let E006 catch

    insertions = int(m.group(1))
    deletions = int(m.group(2))
    total = insertions + deletions
    threshold = max(estimated_lines * 3, 100)  # floor: 100 lines

    if total > threshold:
        print(
            f"[E017] {total} lines changed ({insertions}+/{deletions}-) "
            f"exceeds {estimated_lines} estimate × 3 = {threshold}"
        )
        return False, "E017_EXCESSIVE_CHURN"

    print(f"[E017] {total} lines (budget: {threshold})")
    return True, None


def step_presentation_acceptance(card_body: str, workspace: str) -> Tuple[bool, Optional[str]]:
    """E028/E029 — layout and a11y acceptance when card body declares presentation acceptance."""
    if not any(
        marker in card_body
        for marker in ("Acceptance (layout):", "Acceptance (presentation):", "Acceptance (a11y):")
    ):
        return True, None
    from presentation_acceptance import run_presentation_checks  # noqa: E402

    ok, err = run_presentation_checks(card_body, workspace)
    if not ok:
        return False, err or "E028"
    return True, None


def _card_key_from_body(card_body: str, task_id: str) -> str:
    m = re.search(r"card_key:\s*(\S+)", card_body, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"Task\s+\S+:\s*(.+)", card_body)
    if m:
        slug = re.sub(r"[^a-z0-9]+", "-", m.group(1).lower()).strip("-")
        if slug:
            return slug[:64]
    return task_id.replace("t_", "", 1) if task_id.startswith("t_") else task_id


# ── Main chain ─────────────────────────────────────────────────────────

def run_chain(task_id: str, workspace: str, card_body: str,
              baseline: str = "HEAD~1", token_log: str = "",
              lattice_memory_path: str = "", registry_path: str = "") -> Tuple[bool, str]:
    """Run the full evaluation chain. Returns (passed, reason)."""

    registry = load_error_registry(registry_path)
    parsed = parse_card_body(card_body)
    working_branch = os.environ.get("KANBAN_WORKING_BRANCH", "main").strip() or "main"
    baseline = _effective_baseline(baseline)
    _lib = os.path.join(os.path.dirname(__file__), "lib")
    if _lib not in sys.path:
        sys.path.insert(0, _lib)
    from governance_profile import resolve_governance_profile  # noqa: E402

    policy_profile = resolve_governance_profile(repo_root=workspace)

    def _finish_step(ok: bool, err: Optional[str]) -> Tuple[bool, Optional[str]]:
        if ok:
            return True, None
        if policy_profile == "advisory":
            return True, f"Advisory pass with warnings: {err}"
        return False, err

    if is_verification_deploy(parsed, card_body):
        plan_id = parsed.get("plan_id") or ""
        card_key = _card_key_from_body(card_body, task_id)
        from presentation_acceptance import verification_deploy_attested  # noqa: E402

        if not plan_id:
            return False, "verification_deploy_requires_plan_id"
        if not verification_deploy_attested(Path(workspace), plan_id, card_key):
            return False, "verification_deploy_requires_attestation"
        if parsed.get("tests"):
            ok, err = step_3_tests_pass(parsed["tests"], workspace, parsed.get("files") or [])
            passed, reason = _finish_step(ok, err)
            if not passed:
                return False, reason or err or "verification_deploy test failed"
        return True, "verification_deploy attested"

    if is_verification_only(parsed, card_body):
        # Resolve main project root for test execution (worktree may have stale HEAD)
        config_root = _resolve_project_root(workspace)
        if config_root and os.path.isdir(config_root):
            print(f"[chain] Verification: using project root {config_root} (not worktree)")
            workspace = config_root
        if not parsed.get("tests") and "Acceptance:" not in card_body:
            return False, "verification_only: Tests: or Acceptance: required"
        print("[chain] Verification-only card — running tests + destructive-git checks only")
        for step_name, step_fn in (
            ("Test pass", lambda: step_3_tests_pass(parsed["tests"], workspace, parsed.get("files") or [])),
            ("No destructive git (E019)", lambda: step_8_no_destructive_git(workspace, workspace)),
        ):
            print(f"[chain] Step: {step_name}...", end=" ")
            ok, err = step_fn()
            passed, reason = _finish_step(ok, err)
            if not passed:
                return False, reason or err or "verification check failed"
            print("ALLOW")
        return True, "All checks passed (verification_only)"

    # Lattice memory: skip cold-path validation if attractor matches
    memory = {}
    disable_attractor = (
        "Call-sites:" in card_body
        or "Acceptance (layout):" in card_body
        or "Acceptance (presentation):" in card_body
        or "Acceptance (a11y):" in card_body
        or len([f for f in (parsed.get("files") or []) if f and "test" not in f.lower()]) >= 2
    )
    presentation_step = lambda: step_presentation_acceptance(card_body, workspace)
    if lattice_memory_path and not disable_attractor:
        memory = load_lattice_memory(lattice_memory_path)
        attractor = find_attractor(memory, parsed["files"], parsed["tests"], workspace)
        if attractor:
            print(f"[chain] Attractor match — {attractor['attractor_hash']} (skipping steps 1,3,4)")
            # Verification cards with attractor: only test pass + destructive git
            if is_verification_only(parsed, card_body):
                print("[chain] Verification-only with attractor — tests + E019 only")
                for step_name, step_fn in (
                    ("Test pass", lambda: step_3_tests_pass(parsed["tests"], workspace, parsed.get("files") or [])),
                    ("No destructive git (E019)", lambda: step_8_no_destructive_git(workspace, workspace)),
                ):
                    ok, err = step_fn()
                    passed, reason = _finish_step(ok, err)
                    if not passed:
                        return False, reason or err or "verification check failed"
                return True, "All checks passed (verification_only + attractor)"
            # Still run steps 2 (unlisted changes), 5 (exact token), 6 (zero-output), churn, 7 (agent output capture)
            advisory_notes: list[str] = []
            for step_fn in (
                lambda: step_2_unlisted_changes(parsed["files"], baseline, workspace, task_id),
                presentation_step,
                lambda: step_5_exact_token(token_log, task_id),
                lambda: step_7_agent_output_capture(task_id),
                lambda: step_6_zero_output(
                    parsed["files"], baseline, workspace, parsed.get("commit", "")
                ),
                lambda: step_excessive_churn(parsed["estimated_lines"], baseline, workspace),
                lambda: step_8_no_destructive_git(workspace, workspace),
                lambda: step_acceptance_test_coverage(card_body, baseline, workspace),
                lambda: step_docs_head_verify(card_body, workspace),
            ):
                ok, err = step_fn()
                passed, reason = _finish_step(ok, err)
                if not passed:
                    return False, reason or err or "check failed"
                if reason:
                    advisory_notes.append(reason)
            if advisory_notes:
                return True, "; ".join(advisory_notes)
            return True, "All checks passed (attractor fast-path)"

    # Check error attractors: if this exact files+tests combo DENY'd before, short-circuit
    if lattice_memory_path and not disable_attractor:
        error_entries = memory.get("error_entries", [])
        current_hash = compute_attractor_hash(parsed["files"], parsed["tests"], workspace)
        recent_deny = [e for e in error_entries if e["attractor_hash"] == current_hash and e["outcome"] == "DENY"]
        if recent_deny:
            last = recent_deny[-1]
            print(f"[chain] Error attractor match — same signature DENY'd before: {last['error_code']}")
            print(f"[chain] Short-circuiting: escalate instead of re-running cold path")
            return False, f"E023_REPEATED_IDENTICAL_ERROR: {last['error_code']} — {last['error_reason']} (escalate, do not retry)"

    # Cold path: run all steps
    steps = [
        ("Files: compliance", lambda: step_1_file_compliance(
            parsed["files"], baseline, workspace, parsed.get("commit", ""),
            card_body=card_body, working_branch=working_branch,
        )),
        ("Unlisted changes", lambda: step_2_unlisted_changes(parsed["files"], baseline, workspace, task_id)),
        (
            "Impl before test (E003)",
            lambda: step_impl_before_test(
                parsed.get("files") or [], card_body, workspace, baseline
            ),
        ),
        ("Test pass", lambda: step_3_tests_pass(parsed["tests"], workspace, parsed.get("files") or [])),
        (
            "Acceptance test coverage (E021)",
            lambda: step_acceptance_test_coverage(card_body, baseline, workspace),
        ),
        ("Presentation acceptance (E028/E029)", presentation_step),
        ("Commit match", lambda: step_4_commit_match(parsed["commit"], workspace)),
        ("Exact token (E018)", lambda: step_5_exact_token(token_log, task_id)),
        ("Zero-output check", lambda: step_6_zero_output(
            parsed["files"], baseline, workspace, parsed.get("commit", "")
        )),
        ("Excessive churn (E017)", lambda: step_excessive_churn(parsed["estimated_lines"], baseline, workspace)),
        ("Agent output capture (E020)", lambda: step_7_agent_output_capture(task_id)),
        ("No destructive git (E019)", lambda: step_8_no_destructive_git(workspace, workspace)),
        ("Docs HEAD verify (E022)", lambda: step_docs_head_verify(card_body, workspace)),
    ]

    for step_name, step_fn in steps:
        print(f"[chain] Step: {step_name}...", end=" ")
        passed, error_code = step_fn()
        if not passed:
            err_info = registry.get(error_code, {})
            desc = err_info.get("description", error_code)
            reason = f"{error_code}: {desc}"
            if policy_profile == "advisory":
                print(f"ADVISORY ({reason}) — would deny under balanced/strict")
                return True, f"Advisory pass with warnings: {reason}"
            if policy_profile == "strict":
                print(f"DENY+NOTIFY ({reason})")
            else:
                print(f"DENY ({reason})")
            # Write error attractor so repeated same-error blocks skip cold-path
            if lattice_memory_path:
                try:
                    error_entry = {
                        "attractor_hash": compute_attractor_hash(parsed["files"], parsed["tests"], workspace),
                        "files": parsed["files"],
                        "tests": parsed["tests"],
                        "outcome": "DENY",
                        "error_code": error_code,
                        "error_reason": reason,
                        "workspace_hash": compute_workspace_hash(workspace),
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    }
                    memory.setdefault("error_entries", [])
                    existing = [e for e in memory["error_entries"] if e["attractor_hash"] != error_entry["attractor_hash"]]
                    existing.append(error_entry)
                    memory["error_entries"] = existing[-50:]
                    with open(lattice_memory_path, "w", encoding="utf-8") as f:
                        json.dump(memory, f, indent=2, default=str)
                except Exception:
                    pass  # Non-fatal
            return False, reason
        print("ALLOW")

    # Save lattice memory entry on success
    if lattice_memory_path:
        entry = {
            "task_id": task_id,
            "chain_version": 1,
            "steps_passed": 6,
            "files": parsed["files"],
            "tests_cmd": parsed["tests"],
            "attractor_hash": compute_attractor_hash(parsed["files"], parsed["tests"], workspace),
            "timestamp": datetime.datetime.now().isoformat(),
        }
        memory.setdefault("entries", []).append(entry)
        # Keep last 100 entries
        memory["entries"] = memory["entries"][-100:]
        save_lattice_memory(lattice_memory_path, memory)

    return True, "All checks passed"


# ── CLI ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="kanban evaluation chain")
    parser.add_argument("task_id", help="Kanban task ID (e.g., t_xxxx)")
    parser.add_argument("workspace", help="Path to worktree/repo root")
    parser.add_argument("--baseline", default="HEAD~1", help="Git baseline for diff")
    parser.add_argument("--token-log", default="", help="Path to token log")
    parser.add_argument("--lattice-memory", default="", help="Path to lattice memory JSON")
    parser.add_argument("--registry", default="", help="Path to error-codes.yaml")
    parser.add_argument("--card-body", default="", help="Card body text (or read from stdin)")
    args = parser.parse_args()

    # Resolve paths
    repo_root = args.workspace
    token_log = args.token_log or os.path.join(repo_root, ".hermes", "kanban", "tokens.jsonl")
    lattice_memory = args.lattice_memory or os.path.join(repo_root, ".hermes", "kanban", "lattice-memory.json")
    registry = args.registry or os.path.join(repo_root, "kanban-workflow", "registry", "error-codes.yaml")

    # Get card body
    card_body = args.card_body
    if not card_body:
        # Try reading from kanban show
        try:
            result = subprocess.run(
                ["hermes", "kanban", "show", args.task_id],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=10,
            )
            if result.returncode == 0:
                card_body = result.stdout
        except Exception:
            pass
    if not card_body:
        print("ERROR: Cannot determine card body. Pass --card-body or ensure hermes is available.")
        sys.exit(1)

    print(f"[chain] Task: {args.task_id}")
    print(f"[chain] Workspace: {args.workspace}")
    print(f"[chain] Baseline: {args.baseline}")

    _lib = os.path.join(os.path.dirname(__file__), "lib")
    if _lib not in sys.path:
        sys.path.insert(0, _lib)
    from governance_profile import (  # noqa: E402
        emit_strict_notification,
        resolve_governance_profile,
        should_notify_operator,
    )

    profile = resolve_governance_profile(repo_root=args.workspace)

    passed, reason = run_chain(
        args.task_id, args.workspace, card_body,
        baseline=args.baseline, token_log=token_log,
        lattice_memory_path=lattice_memory, registry_path=registry,
    )

    if passed:
        print(f"[chain] ALLOW — {reason}")
        subprocess.run(["hermes", "kanban", "complete", args.task_id, reason])
        sys.exit(0)
    else:
        print(f"[chain] DENY — {reason}")
        subprocess.run(["hermes", "kanban", "block", args.task_id, reason])
        if should_notify_operator(profile):
            emit_strict_notification(
                task_id=args.task_id,
                reason=reason,
                failure_class="evaluation_chain",
                repo_root=args.workspace,
            )
        sys.exit(1)
