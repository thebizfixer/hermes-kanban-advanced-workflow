#!/usr/bin/env python3
"""Plan fidelity checks for decomposed card bodies (v7 validate_card_bodies)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.card_body import (
    body_tests_valid,
    extract_tests_line,
    normalize_file_path,
    sanitize_tests_command,
)
from decompose_stamp import extract_agent_field
from plan_parse import (
    _block_start_lineno,
    extract_files_from_text,
    extract_optimization_section,
    find_backtick_file_refs,
    load_plan_text,
    split_card_blocks,
)

_VERIFY_RG_RE = re.compile(
    r"Verify:\s*rg\s+(?:-n\s+)?['\"]?([^'\"]+)['\"]?\s+(\S+\.(?:py|ts|tsx|js|sh|md|yaml|yml))",
    re.IGNORECASE,
)
_CREDENTIAL_WARN_RE = re.compile(
    r"(TESTSPRITE_|_(?:KEY|TOKEN|SECRET)\b)",
    re.IGNORECASE,
)
_CODE_FILE_RE = re.compile(r"\S+\.(?:py|ts|tsx|js|sh)$", re.IGNORECASE)


@dataclass
class FidelityViolation:
    code: str
    severity: str  # warn | block
    message: str
    card_key: str | None = None
    plan_lineno: int | None = None
    plan_file: str = ""


def _plan_file_label(plan_path: Path | str | None) -> str:
    if not plan_path:
        return "plan"
    return Path(plan_path).as_posix()


def _fmt_violation(v: FidelityViolation) -> str:
    loc = ""
    if v.plan_file and v.plan_lineno:
        loc = f"{v.plan_file}:{v.plan_lineno}: "
    elif v.plan_file:
        loc = f"{v.plan_file}: "
    prefix = "WARN" if v.severity == "warn" else "FAIL"
    key = f" [{v.card_key}]" if v.card_key else ""
    return f"{prefix}: {loc}{v.message}{key} ({v.code})"


def collect_plan_required_files(plan_text: str, cards: list[dict[str, Any]]) -> set[str]:
    """Files explicitly required by plan Spec / Verify / **Files:** — not card assignment union."""
    required: set[str] = set()
    opt = extract_optimization_section(plan_text)
    if opt:
        required.update(extract_files_from_text(opt))
    for block in split_card_blocks(plan_text):
        agent_match = re.search(r"```agent\s*\n(.*?)```", block, re.DOTALL | re.IGNORECASE)
        if not agent_match:
            continue
        agent = agent_match.group(1)
        spec = extract_agent_field(agent, "Spec")
        for ref in find_backtick_file_refs(spec or agent):
            required.add(normalize_file_path(ref))
        for m in _VERIFY_RG_RE.finditer(agent):
            required.add(normalize_file_path(m.group(2)))
        for m in re.finditer(r"^Files:\s*(.+)$", agent, re.MULTILINE | re.IGNORECASE):
            for part in m.group(1).split(","):
                p = normalize_file_path(part.strip())
                if p:
                    required.add(p)
    # Plan-level Contracts / workstream file refs
    for ref in find_backtick_file_refs(plan_text):
        p = normalize_file_path(ref)
        if _CODE_FILE_RE.search(p):
            required.add(p)
    return {p for p in required if p and not p.startswith("#")}


def collect_assigned_files(cards: list[dict[str, Any]]) -> set[str]:
    assigned: set[str] = set()
    for card in cards:
        if card.get("type") in ("gate", "root", "audit"):
            continue
        for f in card.get("files") or []:
            norm = normalize_file_path(str(f))
            if norm:
                assigned.add(norm)
    return assigned


def validate_parsed_cards(
    *,
    plan_path: Path | str | None,
    plan_text: str,
    cards: list[dict[str, Any]],
    repo_root: Path,
    plan_id: str = "",
    profile: str = "balanced",
) -> list[FidelityViolation]:
    """Run plan-fidelity checks on parsed cards before board create or at gate."""
    violations: list[FidelityViolation] = []
    plan_label = _plan_file_label(plan_path)
    advisory = profile == "advisory"
    block_sev = "warn" if advisory else "block"

    decomposing_plan_id = plan_id or ""
    if not decomposing_plan_id and plan_text.startswith("---"):
        m = re.search(r"^plan_id:\s*(\S+)", plan_text, re.MULTILINE | re.IGNORECASE)
        if m:
            decomposing_plan_id = m.group(1).strip()

    required = collect_plan_required_files(plan_text, cards)
    assigned = collect_assigned_files(cards)
    missing_from_cards = sorted(required - assigned)
    if missing_from_cards:
        opt = extract_optimization_section(plan_text)
        lineno = _block_start_lineno(plan_text, opt) if opt else 1
        violations.append(
            FidelityViolation(
                code="V001_SPEC_FILE_UNASSIGNED",
                severity=block_sev,
                message=(
                    "Plan Spec requires files not assigned to any card: "
                    + ", ".join(missing_from_cards[:8])
                    + ("..." if len(missing_from_cards) > 8 else "")
                ),
                plan_lineno=lineno,
                plan_file=plan_label,
            )
        )

    opt_blocks = split_card_blocks(extract_optimization_section(plan_text) or plan_text)
    block_by_key: dict[str, str] = {}
    for block in opt_blocks:
        km = re.search(r"#### Card (\d+)", block)
        if km:
            block_by_key[f"card{km.group(1)}"] = block

    for card in cards:
        if card.get("type") in ("gate", "root", "audit"):
            continue
        key = str(card.get("key", ""))
        card_plan_id = ""
        body = card.get("body") or ""
        for line in body.splitlines():
            if line.strip().lower().startswith("plan_id:"):
                card_plan_id = line.split(":", 1)[1].strip()
                break
        if decomposing_plan_id and card_plan_id and card_plan_id != decomposing_plan_id:
            violations.append(
                FidelityViolation(
                    code="V002_PLAN_ID_MISMATCH",
                    severity=block_sev,
                    message=f"card plan_id '{card_plan_id}' != decomposing plan '{decomposing_plan_id}'",
                    card_key=key,
                    plan_file=plan_label,
                )
            )

        est = card.get("estimated_lines")
        if est is not None:
            try:
                if int(est) > 500:
                    violations.append(
                        FidelityViolation(
                            code="V003_LINES_BUDGET",
                            severity="warn",
                            message=f"estimated_lines {est} exceeds 500 ceiling",
                            card_key=key,
                            plan_file=plan_label,
                        )
                    )
            except (TypeError, ValueError):
                pass

        tests_raw = card.get("tests") or extract_tests_line(body)
        if tests_raw and tests_raw.upper() != "N/A":
            if not body_tests_valid(f"Tests: {tests_raw}\n"):
                block = block_by_key.get(key, "")
                lineno = _block_start_lineno(plan_text, block) if block else None
                violations.append(
                    FidelityViolation(
                        code="V004_TESTS_MALFORMED",
                        severity=block_sev,
                        message=f"Tests: line not valid shell: {tests_raw[:120]}",
                        card_key=key,
                        plan_lineno=lineno,
                        plan_file=plan_label,
                    )
                )
            sanitized = sanitize_tests_command(tests_raw)
            if sanitized != tests_raw.strip():
                violations.append(
                    FidelityViolation(
                        code="V005_TESTS_SANITIZE",
                        severity="warn",
                        message=f"Tests: will sanitize to: {sanitized}",
                        card_key=key,
                        plan_file=plan_label,
                    )
                )
            if _CREDENTIAL_WARN_RE.search(tests_raw):
                violations.append(
                    FidelityViolation(
                        code="V006_TESTS_CREDENTIAL_PATTERN",
                        severity="warn",
                        message="Tests: line may embed credential-like env var names",
                        card_key=key,
                        plan_file=plan_label,
                    )
                )

        card_type = card.get("type") or ""
        if card_type == "verification-deploy":
            if not tests_raw or tests_raw.upper() != "N/A":
                violations.append(
                    FidelityViolation(
                        code="V007_DEPLOY_TESTS_NOT_NA",
                        severity=block_sev,
                        message=(
                            f"verification-deploy card Tests: must be 'N/A' — "
                            "operator smoke/browser steps belong in Acceptance:"
                        ),
                        card_key=key,
                        plan_file=plan_label,
                    )
                )

        for f in card.get("files") or []:
            norm = normalize_file_path(str(f))
            if not norm:
                continue
            if norm != str(f).strip():
                violations.append(
                    FidelityViolation(
                        code="V007_FILES_NORMALIZE",
                        severity="warn",
                        message=f"Files: entry '{f}' normalizes to '{norm}'",
                        card_key=key,
                        plan_file=plan_label,
                    )
                )
            # create-only cards are expected to create their Files: — skip existence check
            mode = (card.get("mode") or "").lower()
            if mode != "create-only":
                full = repo_root / norm
                if not full.is_file():
                    violations.append(
                        FidelityViolation(
                            code="V008_PATH_MISSING",
                            severity=block_sev,
                            message=f"Files: path not in repo: {norm}",
                            card_key=key,
                            plan_file=plan_label,
                        )
                    )

    return violations


def validate_plan_file(
    plan_path: Path,
    repo_root: Path,
    *,
    profile: str = "balanced",
) -> list[FidelityViolation]:
    from plan_parse import parse_plan

    plan_text = load_plan_text(plan_path)
    parsed = parse_plan(str(plan_path))
    return validate_parsed_cards(
        plan_path=plan_path,
        plan_text=plan_text,
        cards=parsed.get("cards") or [],
        repo_root=repo_root,
        plan_id=parsed.get("plan_id", ""),
        profile=profile,
    )
