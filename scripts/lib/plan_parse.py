#!/usr/bin/env python3
"""SSOT for kanban plan markdown parsing (platform-neutral; no grep -P)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_CARD_HEADING_RE = re.compile(r"^#### (Card \d+.*?)$", re.MULTILINE)
_CARD_ORDINAL_RE = re.compile(r"^#### Card (\d+)", re.MULTILINE)
_OPT_SECTION_RE = re.compile(
    r"## Kanban optimization.*?(?=^## \w|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)
_PLAN_ID_RE = re.compile(r"^plan_id:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
_BACKTICK_FILE_RE = re.compile(
    r"`([^`]+\.(?:py|ts|js|sh|yaml|md|mdc))`",
    re.IGNORECASE,
)
_LINE_NUM_RE = re.compile(r"L(\d+)")
_FILE_FIELD_RE = re.compile(r"\*\*Files?:\*\*\s+(.+)", re.IGNORECASE)
_BOLD_FILES_RE = _FILE_FIELD_RE
_YAML_FILES_LIST_RE = re.compile(
    r"^\s*-\s+(\S+\.(?:py|ts|js|sh|yaml|md|mdc))",
    re.MULTILINE | re.IGNORECASE,
)
_PLAIN_FILES_RE = re.compile(
    r"^Files:\s+(\S+\.(?:py|ts|js|sh|yaml|md|mdc))",
    re.MULTILINE | re.IGNORECASE,
)
_DEF_CLASS_RE = re.compile(r"(?:def|class|function|async def)\s+(\w+)")
_SYMBOL_BACKTICK_RE = re.compile(r"`([a-zA-Z_][a-zA-Z0-9_]*)`")
_WORKSTREAM_START_RE = re.compile(r"^### Workstream", re.MULTILINE | re.IGNORECASE)
_SECTION_BREAK_RE = re.compile(r"^(?:---|## |\Z)", re.MULTILINE)


@dataclass
class AnchorRef:
    file: str
    line: int
    symbol_hint: str | None
    source_line: str
    source_lineno: int


def load_plan_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    block = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    fm: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, body


def extract_optimization_section(content: str, *, exit_on_missing: bool = False) -> str:
    opt_match = _OPT_SECTION_RE.search(content)
    if not opt_match:
        if exit_on_missing:
            sys.exit("ERROR: No '## Kanban optimization' section found in plan (case-insensitive)")
        return ""
    return opt_match.group(0)


def _extract_optimization_section(content: str) -> str:
    """Backward-compatible alias used by kanban_decompose tests."""
    return extract_optimization_section(content, exit_on_missing=True)


def split_card_blocks(section: str) -> list[str]:
    matches = list(_CARD_HEADING_RE.finditer(section))
    if not matches:
        return []
    blocks: list[str] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        blocks.append(section[start:end].rstrip())
    return blocks


def _split_card_blocks(section: str) -> list[str]:
    return split_card_blocks(section)


def list_card_ordinals(section: str) -> list[int]:
    return [int(m.group(1)) for m in _CARD_ORDINAL_RE.finditer(section)]


def validate_card_ordinals(ordinals: list[int]) -> str | None:
    if not ordinals:
        return "Kanban optimization has no '#### Card N' headings"
    expected = 1
    for n in ordinals:
        if n != expected:
            return (
                f"expected Card {expected} next, found Card {n} "
                "(arrange cards first, then renumber 1..N in file order)"
            )
        expected += 1
    return None


def extract_plan_id_from_content(content: str) -> str | None:
    m = _PLAN_ID_RE.search(content)
    return m.group(1).strip() if m else None


def _extract_plan_id_from_content(content: str) -> str | None:
    return extract_plan_id_from_content(content)


def extract_markdown_field(block: str, name: str) -> str | None:
    m = re.search(rf"\*\*{re.escape(name)}:\*\*\s*(.+)", block, re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip().strip("`").strip()


def _extract_markdown_field(block: str, name: str) -> str | None:
    return extract_markdown_field(block, name)


def extract_files_from_block(block: str) -> list[str]:
    return _extract_markdown_files(block)


def _extract_markdown_files(block: str) -> list[str]:
    m = re.search(r"\*\*Files:\*\*\s*(.+)", block, re.IGNORECASE)
    if not m:
        return []
    raw = m.group(1).strip()
    files: list[str] = []
    for part in re.split(r",\s*", raw):
        path = _normalize_file_path(part)
        if path:
            files.append(path)
    return files


def extract_files_from_text(text: str) -> list[str]:
    files: list[str] = []
    for m in re.finditer(r"\*\*Files:\*\*\s*(.+)", text, re.IGNORECASE):
        raw = m.group(1).strip()
        for part in re.split(r",\s*", raw):
            path = _normalize_file_path(part)
            if path and path not in files:
                files.append(path)
    return files


def _normalize_file_path(path: str) -> str:
    return path.strip().strip("`").strip().rstrip(".").rstrip(",")


def iter_lines_with_line_numbers(text: str):
    for i, line in enumerate(text.splitlines(), start=1):
        yield i, line


def iter_workstream_sections(content: str) -> list[str]:
    sections: list[str] = []
    starts = [m.start() for m in _WORKSTREAM_START_RE.finditer(content)]
    if not starts:
        return sections
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(content)
        chunk = content[start:end]
        break_m = _SECTION_BREAK_RE.search(chunk, 1)
        if break_m:
            chunk = chunk[: break_m.start()]
        sections.append(chunk)
    return sections


def workstream_file_conflict_flag(plan_text: str) -> int:
    """Return 1 if same file appears in multiple workstreams (heuristic warn)."""
    conflict = 0
    for section in iter_workstream_sections(plan_text):
        for f in extract_files_from_text(section):
            appearances = len(re.findall(rf"Files:.*{re.escape(f)}", plan_text, re.IGNORECASE))
            if appearances > 1:
                conflict = 1
                break
        if conflict:
            break
    return conflict


def find_backtick_file_refs(line: str) -> list[str]:
    return [m.group(1) for m in _BACKTICK_FILE_RE.finditer(line)]


def find_line_number_refs(line: str) -> list[int]:
    return sorted({int(m.group(1)) for m in _LINE_NUM_RE.finditer(line)})


def find_section_file_above(text: str, line_no: int, lookback: int = 50) -> str | None:
    lines = text.splitlines()
    start = max(0, line_no - lookback - 1)
    window = "\n".join(lines[start:line_no])

    bold_matches = list(_BOLD_FILES_RE.finditer(window))
    if bold_matches:
        raw = bold_matches[-1].group(1).strip()
        first_part = re.split(r",\s*", raw)[0]
        path = _normalize_file_path(first_part)
        if path:
            return path

    last_files_hdr: re.Match[str] | None = None
    for hdr in re.finditer(r"^files:\s*$", window, re.MULTILINE | re.IGNORECASE):
        last_files_hdr = hdr
    if last_files_hdr:
        sub = window[last_files_hdr.end() :]
        yaml_entries = _YAML_FILES_LIST_RE.findall(sub)
        if yaml_entries:
            return _normalize_file_path(yaml_entries[0])

    plain_matches = list(_PLAIN_FILES_RE.finditer(window))
    if plain_matches:
        return _normalize_file_path(plain_matches[-1].group(1))

    return None


def find_anchor_symbol_above(text: str, line_no: int, lookback: int = 10) -> str | None:
    lines = text.splitlines()
    start = max(0, line_no - lookback - 1)
    window = "\n".join(lines[start:line_no])
    matches = list(_DEF_CLASS_RE.finditer(window))
    if matches:
        return matches[-1].group(1)
    return None


def find_symbol_on_line(line: str) -> str | None:
    syms = _SYMBOL_BACKTICK_RE.findall(line)
    return syms[0] if syms else None


def extract_anchors(plan_text: str) -> list[AnchorRef]:
    anchors: list[AnchorRef] = []
    seen: set[tuple[str, int]] = set()
    for lineno, line in iter_lines_with_line_numbers(plan_text):
        if not _LINE_NUM_RE.search(line):
            continue
        file_refs = find_backtick_file_refs(line)
        file_field = extract_markdown_field(line, "File") or extract_markdown_field(line, "Files")
        file_name = file_refs[0] if file_refs else (file_field or "")
        if not file_name:
            file_name = find_section_file_above(plan_text, lineno) or ""
        if not file_name:
            continue
        file_name = _normalize_file_path(file_name)
        symbol = find_anchor_symbol_above(plan_text, lineno) or find_symbol_on_line(line)
        for ln in find_line_number_refs(line):
            key = (file_name, ln)
            if key in seen:
                continue
            seen.add(key)
            anchors.append(
                AnchorRef(
                    file=file_name,
                    line=ln,
                    symbol_hint=symbol,
                    source_line=line.strip(),
                    source_lineno=lineno,
                )
            )
    return anchors


def _extract_field(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else None


def parse_card_block(block: str) -> dict | None:
    title_match = re.match(r"#### (Card \d+.*?)(?:\s*\(.*?\))?\s*$", block, re.MULTILINE)
    if not title_match:
        return None
    title = title_match.group(1).strip()

    card_type_field = extract_markdown_field(block, "Type")

    card_type = "code-gen"
    assignee = None
    is_manual = "(manual)" in title.lower() or "manual)" in title.lower()
    if "ROOT" in title or "root" in title.lower():
        card_type = "root"
        assignee = "orchestrator"
    elif "Gate" in title or "gate" in title.lower():
        card_type = "gate"
        assignee = "orchestrator"
    elif is_manual:
        card_type = "manual"
        assignee = "orchestrator"
    elif "audit" in title.lower() or "final audit" in title.lower():
        card_type = "audit"
        assignee = "orchestrator"
    if card_type_field:
        ct = card_type_field.lower()
        if ct == "verification":
            card_type = "verification"
        elif "gate" in ct:
            card_type = "gate"
            assignee = assignee or "orchestrator"
        elif "audit" in ct:
            card_type = "audit"
            assignee = assignee or "orchestrator"
        elif "root" in ct:
            card_type = "root"
            assignee = assignee or "orchestrator"

    plan_id = _extract_field(block, r"plan_id:\s*(.+)")
    files_raw = _extract_field(block, r"files:\s*\n((?:\s{2}- .+\n?)+)")
    files: list[str] = []
    if files_raw:
        files = [
            _normalize_file_path(f.strip().lstrip("- "))
            for f in files_raw.strip().split("\n")
            if f.strip().startswith("- ")
        ]
    if not files:
        files = extract_files_from_block(block)
    mode = _extract_field(block, r"mode:\s*(.+)") or extract_markdown_field(block, "Mode")
    tests = _extract_field(block, r"tests:\s*(.+)") or extract_markdown_field(block, "Tests")
    commit = _extract_field(block, r'commit:\s*"?(.+?)"?\s*$')
    estimated_lines = _extract_field(block, r"estimated_lines:\s*(\d+)")
    wave = _extract_field(block, r"wave:\s*(\d+)")
    wave_parent = _extract_field(block, r"wave_parent:\s*(.+)")
    ordinal_parent = _extract_field(block, r"ordinal_parent:\s*(.+)")
    workspace = _extract_field(block, r"workspace:\s*(.+)")
    branch = _extract_field(block, r"branch:\s*(.+)")
    card_assignee = _extract_field(block, r"assignee:\s*(.+)")

    if card_assignee:
        assignee = card_assignee
    elif not assignee:
        assignee = "worker" if card_type == "code-gen" else "orchestrator"

    agent_body = None
    agent_match = re.search(r"```agent\s*\n(.*?)```", block, re.DOTALL)
    if agent_match:
        agent_body = agent_match.group(1).strip()

    body_lines = [f"plan_id: {plan_id or 'unknown'}"]
    if card_type in ("gate", "audit", "root"):
        body_lines.append("pre_existing: true")
    if files:
        body_lines.append("files:")
        for f in files:
            body_lines.append(f"  - {f}")
    body_lines.append(f"mode: {mode or 'modify-only'}")
    if tests:
        body_lines.append(f"tests: {tests}")
    if commit:
        body_lines.append(f'commit: "{commit}"')
    if estimated_lines:
        body_lines.append(f"estimated_lines: {estimated_lines}")

    if agent_body:
        body_lines.extend(["", "---", "```agent", agent_body, "```"])

    full_body = "\n".join(body_lines)

    key_match = re.search(r"(card\d+)", title.lower().replace(" ", "").replace("-", ""))
    card_key = key_match.group(1) if key_match else title.lower().replace(" ", "_")

    return {
        "key": card_key,
        "title": title,
        "type": card_type,
        "assignee": assignee,
        "plan_id": plan_id or "",
        "files": files,
        "mode": mode or "modify-only",
        "tests": tests or "",
        "commit": commit or "",
        "estimated_lines": int(estimated_lines) if estimated_lines else 0,
        "wave": int(wave) if wave else 1,
        "wave_parent": wave_parent.strip() if wave_parent else None,
        "ordinal_parent": ordinal_parent.strip() if ordinal_parent else None,
        "workspace": workspace,
        "branch": branch,
        "body": full_body,
        "agent_body": agent_body,
    }


def parse_plan(plan_path: str) -> dict:
    content = load_plan_text(plan_path)
    section = _extract_optimization_section(content)
    blocks = split_card_blocks(section)

    cards = []
    for block in blocks:
        card = parse_card_block(block)
        if card:
            cards.append(card)

    if not cards:
        sys.exit("ERROR: No card definitions found in optimization section")

    plan_id = extract_plan_id_from_content(content) or Path(plan_path).stem.replace(".plan", "")
    return {"cards": cards, "plan_id": plan_id}


def _cmd_card_ordinals(args: argparse.Namespace) -> int:
    text = load_plan_text(args.plan)
    section = extract_optimization_section(text)
    ordinals = list_card_ordinals(section)
    err = validate_card_ordinals(ordinals)
    if args.json:
        print(json.dumps({"ordinals": ordinals, "error": err}))
    else:
        if err:
            print(err, file=sys.stderr)
            return 1
        print(" ".join(str(n) for n in ordinals))
    return 1 if err else 0


def extract_acceptance_matrix(plan_text: str) -> dict:
    """Surface slots + per-card presentation acceptance for plan memory."""
    from presentation_acceptance import parse_presentation_acceptance, parse_surface_slots

    matrix: dict = {
        "surface_slots": parse_surface_slots(plan_text),
        "presentation_cards": [],
    }
    opt = extract_optimization_section(plan_text)
    if not opt:
        return matrix
    for block in split_card_blocks(opt):
        pa = parse_presentation_acceptance(block)
        if pa.get("layout") or pa.get("a11y"):
            matrix["presentation_cards"].append(pa)
    return matrix


def integration_verify_warnings(cards: list[dict], plan_text: str) -> list[str]:
    """Advisory when frontend route micro-cards lack a closing integration-verify gate."""
    warnings: list[str] = []
    route_cards = [
        c for c in cards if re.search(r"route-", c.get("key", ""), re.IGNORECASE)
    ]
    has_integration = any(c.get("key") == "integration-verify" for c in cards)
    has_frontend = bool(
        re.search(r"Files:.*\.(tsx|vue|svelte)", plan_text, re.IGNORECASE)
        or re.search(r"^Surface-slots:", plan_text, re.MULTILINE | re.IGNORECASE)
    )
    if route_cards and not has_integration:
        warnings.append(
            "Plan has route-* cards but no integration-verify card — add "
            "Type: verification-local after route-layout group (kanban-planning § Frontend decomposition)."
        )
    elif has_frontend and not has_integration and not route_cards:
        if re.search(r"Acceptance \(layout\)|Acceptance \(presentation\)", plan_text, re.I):
            warnings.append(
                "Frontend plan declares presentation acceptance but no integration-verify card — "
                "add orchestrator/worker verification-local gate before verification-deploy."
            )
    return warnings


def _cmd_workstream_conflict(args: argparse.Namespace) -> int:
    text = load_plan_text(args.plan)
    flag = workstream_file_conflict_flag(text)
    if args.json:
        print(json.dumps({"conflict": bool(flag)}))
    else:
        print(flag)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan markdown parsing utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ord = sub.add_parser("card-ordinals", help="List/validate Card N ordinals")
    p_ord.add_argument("--plan", required=True)
    p_ord.add_argument("--json", action="store_true")
    p_ord.set_defaults(func=_cmd_card_ordinals)

    p_ws = sub.add_parser("workstream-conflict", help="Workstream file overlap heuristic")
    p_ws.add_argument("--plan", required=True)
    p_ws.add_argument("--json", action="store_true")
    p_ws.set_defaults(func=_cmd_workstream_conflict)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
