"""Parse kanban card bodies and classify verification / orchestrator-only cards."""

from __future__ import annotations

import re
import subprocess
from typing import List, Optional

_VERIFICATION_COMMIT_RE = re.compile(r"(?i)N/A|verification only")
_LEGACY_VERIFICATION_BODY_RE = re.compile(r"(?i)\bverification only\b")


def parse_card_body(body: str) -> dict:
    """Extract structured fields from a kanban card body."""
    files_line: List[str] = []
    mode_line = "any"
    tests_cmd = ""
    commit_line = ""
    plan_id = ""
    plan_file = ""
    card_type = ""
    estimated_lines = 200
    agent_block = ""

    in_files_yaml = False
    for line in body.split("\n"):
        stripped = line.strip()
        if line.startswith("Files:"):
            raw = line.replace("Files:", "").strip()
            files_line = [f.strip() for f in raw.split(",") if f.strip()]
        elif stripped.startswith("files:") and not files_line:
            rest = stripped.split(":", 1)[1].strip()
            if rest:
                files_line = [f.strip() for f in rest.split(",") if f.strip()]
            else:
                in_files_yaml = True
        elif in_files_yaml:
            if stripped.startswith("- "):
                files_line.append(stripped[2:].strip())
            elif stripped and not stripped.startswith("#"):
                in_files_yaml = False
        elif line.startswith("Mode:") or stripped.startswith("mode:"):
            mode_line = stripped.split(":", 1)[1].strip()
        elif line.startswith("Tests:") or stripped.startswith("tests:"):
            tests_cmd = stripped.split(":", 1)[1].strip()
        elif line.startswith("Commit:") or stripped.startswith("commit:"):
            commit_line = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("Lines:") or stripped.startswith("estimated_lines:"):
            try:
                estimated_lines = int(stripped.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif stripped.startswith("plan_id:"):
            plan_id = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("plan_file:"):
            plan_file = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Plan:"):
            if not plan_file:
                plan_file = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Type:") or stripped.startswith("type:"):
            card_type = stripped.split(":", 1)[1].strip()

    agent_match = re.search(r"```agent\n(.*?)```", body, re.DOTALL)
    if agent_match:
        agent_block = agent_match.group(1).strip()

    return {
        "files": files_line,
        "mode": mode_line,
        "tests": tests_cmd,
        "commit": commit_line,
        "estimated_lines": estimated_lines,
        "agent_block": agent_block,
        "plan_id": plan_id,
        "plan_file": plan_file,
        "type": card_type,
        "body": body,
    }


def is_verification_only(parsed: dict, body: str | None = None) -> bool:
    """True when card is a test-only verification gate (no coding-agent dispatch)."""
    text = body if body is not None else parsed.get("body", "")
    card_type = (parsed.get("type") or "").strip().lower()
    if card_type == "verification":
        return True
    commit = parsed.get("commit") or ""
    if commit and _VERIFICATION_COMMIT_RE.search(commit):
        return True
    if not parsed.get("files") and (parsed.get("mode") or "").lower() == "read-only":
        if _LEGACY_VERIFICATION_BODY_RE.search(text):
            return True
    return False


def has_files_declaration(body: str) -> bool:
    """True when card declares file scope (Files: line or decompose files: YAML list)."""
    if parse_card_body(body).get("files"):
        return True
    return "Files:" in body


def has_mode_declaration(body: str) -> bool:
    return bool(re.search(r"^Mode:", body, re.M) or re.search(r"^mode:", body, re.M))


def has_tests_declaration(body: str) -> bool:
    parsed = parse_card_body(body)
    if parsed.get("tests"):
        return True
    return bool(re.search(r"^(Tests:|tests:)", body, re.M))


def is_verification_card(body: str) -> bool:
    return is_verification_only(parse_card_body(body), body)


def is_orchestrator_only(parsed: dict, body: str | None = None) -> bool:
    """True when worker must not dispatch coding agent (no agent block and no Files:)."""
    text = body if body is not None else parsed.get("body", "")
    if "Type: orchestrator-handoff" in text:
        return True
    if is_verification_only(parsed, text):
        return False
    return not parsed.get("agent_block") and not parsed.get("files")


def _commit_touches_files(sha: str, files: List[str], workspace: str) -> bool:
    if not files:
        return False
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=workspace,
    )
    if result.returncode != 0:
        return False
    touched = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return all(f in touched for f in files)


def find_prior_commit(
    commit_line: str,
    files: List[str],
    workspace: str,
    baseline: str = "HEAD~1",
    max_lookback: int = 64,
) -> Optional[str]:
    """Return SHA when an earlier commit matches message and touches all Files: paths."""
    if not commit_line or not files:
        return None
    if _VERIFICATION_COMMIT_RE.search(commit_line):
        return None

    def _search(*rev_args: str) -> Optional[str]:
        log = subprocess.run(
            ["git", "log", "--format=%H %s", *rev_args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=workspace,
        )
        if log.returncode != 0:
            return None
        for line in log.stdout.splitlines():
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            sha, subject = parts[0], parts[1]
            if commit_line not in subject:
                continue
            if _commit_touches_files(sha, files, workspace):
                return sha
        return None

    found = _search(f"{baseline}..HEAD")
    if found:
        return found
    if max_lookback > 0:
        return _search(f"-n{max_lookback}")
    return None
