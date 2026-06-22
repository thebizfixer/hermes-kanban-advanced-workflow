"""Parse kanban card bodies and classify verification / orchestrator-only cards."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from typing import List, Optional, Tuple

_VERIFICATION_COMMIT_RE = re.compile(r"(?i)N/A|verification only")
_LEGACY_VERIFICATION_BODY_RE = re.compile(r"(?i)\bverification only\b")
_MODE_SUFFIX_RE = re.compile(r"\s*\((?:modify-only|read-only)\)\s*$", re.IGNORECASE)
_MARKDOWN_LINK_PATH_RE = re.compile(r"^\[`([^`]+)`\]\([^)]+\)")
_PAREN_SUFFIX_RE = re.compile(r"\s+\([^)]*\)\s*$")


def normalize_file_path(path: str) -> str:
    """Strip mode suffixes, anchor pins, and markdown link wrappers from a Files: entry."""
    raw = path.strip().strip("`").strip().rstrip(".").rstrip(",")
    link = _MARKDOWN_LINK_PATH_RE.match(raw)
    if link:
        raw = link.group(1).strip()
    raw = _MODE_SUFFIX_RE.sub("", raw).strip()
    if "@L" in raw.upper():
        raw = re.split(r"@L\d+", raw, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if "::" in raw:
        raw = raw.split("::", 1)[0].strip()
    return raw


def sanitize_tests_command(cmd: str) -> str:
    """Strip trailing parenthetical prose from Tests: — logistics only, not intent change.
    
    Also handles common quoting artifacts from markdown rendering:
    - \" → " 
    - \' → '
    """
    if not cmd:
        return cmd
    stripped = cmd.strip()
    if stripped.upper() == "N/A":
        return stripped
    
    # Fix common markdown escaping artifacts
    stripped = stripped.replace('\\"', '"').replace("\\'", "'")
    
    return _PAREN_SUFFIX_RE.sub("", stripped).strip()


_KNOWN_TEST_RUNNERS = frozenset(
    {
        "pytest", "python", "python3", "bash", "sh", "./",
        "npm", "npx", "node", "yarn", "make", "cargo", "go",
        "pip", "uv", "tox", "mypy", "ruff", "black", "flake8",
        "eslint", "tsc", "mvn", "gradle", "dotnet", "deno",
        "just", "pre-commit", "rstest",
    }
)

_PROSE_SIGNAL_WORDS = frozenset(
    {
        "row", "rows", "operator", "manual", "manually",
        "verify", "check", "ensure", "confirm", "validate",
        "and", "then", "after", "before", "finally",
        "matrix", "merge", "rerun", "re-run", "step",
        "browser", "smoke", "click", "navigate",
    }
)


def validate_tests_command_syntax(cmd: str) -> Tuple[bool, Optional[str]]:
    """Return (ok, error_message). N/A and empty are valid."""
    if not cmd or cmd.strip().upper() == "N/A":
        return True, None
    sanitized = sanitize_tests_command(cmd)
    check = sanitized if sanitized else cmd.strip()
    if check.count("(") != check.count(")"):
        return False, "unbalanced parentheses in Tests: line"
    try:
        tokens = shlex.split(check, posix=(os.name != "nt"))
    except ValueError as exc:
        return False, str(exc)
    if not tokens:
        return False, "empty Tests: line after sanitize"
    first = tokens[0].lower()
    has_runner = first in _KNOWN_TEST_RUNNERS or "/" in tokens[0]
    if not has_runner:
        signal_count = sum(1 for t in tokens if t.lower() in _PROSE_SIGNAL_WORDS)
        barewords = sum(1 for t in tokens if t.isalpha())
        if signal_count >= 2 or barewords >= 4:
            return False, "Tests: line looks like prose — use a valid test command or 'N/A'"
    return True, None


def extract_tests_line(body: str) -> str:
    for line in body.split("\n"):
        stripped = line.strip()
        if line.startswith("Tests:") or stripped.startswith("tests:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def body_tests_valid(body: str) -> bool:
    """True when Tests: is absent, N/A, or parses as valid shell after sanitize."""
    tests = extract_tests_line(body)
    if not tests:
        return True
    ok, _ = validate_tests_command_syntax(tests)
    return ok


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
        if line.startswith("Files:") and not files_line:
            raw = line.replace("Files:", "").strip()
            files_line = [
                normalize_file_path(f.strip()) for f in raw.split(",") if f.strip()
            ]
        elif stripped.startswith("files:") and not files_line:
            rest = stripped.split(":", 1)[1].strip()
            if rest:
                files_line = [
                    normalize_file_path(f.strip()) for f in rest.split(",") if f.strip()
                ]
            else:
                in_files_yaml = True
        elif in_files_yaml:
            if stripped.startswith("- "):
                files_line.append(normalize_file_path(stripped[2:].strip()))
            elif stripped and not stripped.startswith("#"):
                in_files_yaml = False
        elif line.startswith("Mode:") or stripped.startswith("mode:"):
            mode_line = stripped.split(":", 1)[1].strip()
        elif line.startswith("Tests:") or stripped.startswith("tests:"):
            tests_cmd = sanitize_tests_command(stripped.split(":", 1)[1].strip())
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

    presentation = _parse_presentation_from_text(body)

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
        "presentation_acceptance": presentation,
    }


def _parse_presentation_from_text(body: str) -> dict:
    try:
        from presentation_acceptance import parse_presentation_acceptance

        return parse_presentation_acceptance(body)
    except ImportError:
        return {"layout": [], "a11y": [], "surface_slots": []}


def is_verification_local(parsed: dict, body: str | None = None) -> bool:
    """True for pytest/grep verification gates (worker may run tests)."""
    card_type = (parsed.get("type") or "").strip().lower()
    if card_type in ("verification", "verification-local"):
        return True
    return is_verification_only(parsed, body) and card_type != "verification-deploy"


def is_verification_deploy(parsed: dict, body: str | None = None) -> bool:
    """True when card requires operator card-attestation before archive."""
    text = body if body is not None else parsed.get("body", "")
    card_type = (parsed.get("type") or "").strip().lower()
    return card_type == "verification-deploy" or bool(
        re.search(r"^Deploy:", text, re.MULTILINE | re.IGNORECASE)
    )


def is_verification_only(parsed: dict, body: str | None = None) -> bool:
    """True when card is a test-only verification gate (no coding-agent dispatch).
    
    Detection order:
    1. Explicit Type: verification-local + Mode: read-only + no agent block → True
    2. verification-deploy → False (separate path)
    3. Legacy: commit=N/A + read-only + no files + "verification only" in body → True
    4. No files + read-only + Type: verification → True
    """
    if is_verification_deploy(parsed, body):
        return False
    text = body if body is not None else parsed.get("body", "")
    card_type = (parsed.get("type") or "").strip().lower()
    
    # Explicit verification-local: any combination that declares read-only
    # and has no coding-agent dispatch (no Files + no agent block)
    if card_type in ("verification", "verification-local"):
        if (parsed.get("mode") or "").lower() == "read-only":
            if not parsed.get("agent_block"):
                return True
        # Also catch: tests-only with no scope declaration
        if not parsed.get("files") and not parsed.get("agent_block"):
            return True
    
    # Legacy: commit=N/A style
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
    parsed = parse_card_body(body)
    return is_verification_local(parsed, body) or is_verification_deploy(parsed, body)


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
