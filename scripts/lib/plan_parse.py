#!/usr/bin/env python3
"""SSOT for kanban plan markdown parsing (platform-neutral; no grep -P)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from lib.card_body import normalize_file_path, sanitize_tests_command  # noqa: E402

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
_ANCHOR_LINE_RE = re.compile(r"^Anchor:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_CANONICAL_PIN_RE = re.compile(
    r"^(?P<file>[^\s:@]+(?:::(?P<sym>[\w]+))?)\s*@L(?P<line>\d+)\s*$",
    re.IGNORECASE,
)
_RELAXED_PIN_RE = re.compile(
    r"(?:`(?P<sym1>[\w]+)`\s+at\s+|(?:(?:class|def|async def)\s+)?(?P<sym2>[\w]+)\s+)?L(?P<line>\d+)",
    re.IGNORECASE,
)
_CONTRACT_ENTRY_RE = re.compile(r"^-\s*(?P<body>.+)$", re.MULTILINE)
_FILES_LINE_RE = re.compile(r"^Files:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_MARKDOWN_LINK_IN_FILES_RE = re.compile(r"\[`")
_MARKDOWN_LINK_PATH_RE = re.compile(r"^\[`([^`]+)`\]\([^)]+\)")


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
        path = normalize_file_path(part)
        if path:
            files.append(path)
    return files


def extract_files_from_text(text: str) -> list[str]:
    files: list[str] = []
    for m in re.finditer(r"\*\*Files:\*\*\s*(.+)", text, re.IGNORECASE):
        raw = m.group(1).strip()
        for part in re.split(r",\s*", raw):
            path = normalize_file_path(part)
            if path and path not in files:
                files.append(path)
    return files


def _normalize_file_path(path: str) -> str:
    """Backward-compatible alias — prefer normalize_file_path from card_body."""
    return normalize_file_path(path)


def parse_anchor_body(
    body: str,
    default_files: list[str] | None = None,
) -> tuple[str, int, str | None] | None:
    """Parse Anchor: body — canonical ``path::sym@L42`` or relaxed ```sym` at L42``."""
    text = body.strip()
    canon = _CANONICAL_PIN_RE.match(text)
    if canon:
        file_part = canon.group("file")
        sym = canon.group("sym")
        if sym is None and "::" in file_part:
            file_path, sym = file_part.split("::", 1)
        else:
            file_path = file_part.split("::", 1)[0] if "::" in file_part else file_part
        return _normalize_file_path(file_path), int(canon.group("line")), sym

    relaxed = _RELAXED_PIN_RE.search(text)
    if not relaxed:
        return None
    sym = relaxed.group("sym1") or relaxed.group("sym2")
    line = int(relaxed.group("line"))
    backtick_paths = find_backtick_file_refs(text)
    if backtick_paths:
        return _normalize_file_path(backtick_paths[0]), line, sym
    if default_files:
        return _normalize_file_path(default_files[0]), line, sym
    return None


def _block_start_lineno(plan_text: str, block: str) -> int:
    idx = plan_text.find(block)
    if idx < 0:
        return 1
    return plan_text[:idx].count("\n") + 1


def _is_trivial_agent_block(agent_body: str) -> bool:
    files = len(_FILES_LINE_RE.findall(agent_body))
    return (
        files <= 1
        and "Call-sites:" not in agent_body
        and not re.search(r"\bwire\b", agent_body, re.IGNORECASE)
    )


def _anchor_from_parsed(
    file_name: str,
    line: int,
    symbol: str | None,
    source_line: str,
    source_lineno: int,
    seen: set[tuple[str, int]],
    anchors: list[AnchorRef],
) -> None:
    key = (file_name, line)
    if key in seen:
        return
    seen.add(key)
    anchors.append(
        AnchorRef(
            file=file_name,
            line=line,
            symbol_hint=symbol,
            source_line=source_line,
            source_lineno=source_lineno,
        )
    )


def extract_anchors_from_contracts(plan_text: str, opt_section: str) -> list[AnchorRef]:
    anchors: list[AnchorRef] = []
    seen: set[tuple[str, int]] = set()
    if not opt_section:
        return anchors
    contracts_m = re.search(r"^Contracts:\s*$", opt_section, re.MULTILINE | re.IGNORECASE)
    if not contracts_m:
        return anchors
    opt_base = _block_start_lineno(plan_text, opt_section)
    tail = opt_section[contracts_m.end() :]
    card_m = re.search(r"^#### Card \d+", tail, re.MULTILINE)
    contracts_blob = tail[: card_m.start()] if card_m else tail
    contracts_start = opt_base + opt_section[: contracts_m.start()].count("\n")
    for i, line in enumerate(contracts_blob.splitlines()):
        entry = _CONTRACT_ENTRY_RE.match(line.strip())
        if not entry:
            continue
        parsed = parse_anchor_body(entry.group("body").strip())
        if not parsed:
            continue
        file_name, ln, sym = parsed
        _anchor_from_parsed(
            file_name,
            ln,
            sym,
            line.strip(),
            contracts_start + 1 + i,
            seen,
            anchors,
        )
    return anchors


def extract_anchors_from_cards(plan_text: str) -> list[AnchorRef]:
    anchors: list[AnchorRef] = []
    seen: set[tuple[str, int]] = set()
    opt = extract_optimization_section(plan_text)
    if not opt:
        return anchors
    for block in split_card_blocks(opt):
        card = parse_card_block(block)
        if not card:
            continue
        default_files = card.get("files") or []
        agent_body = card.get("agent_body") or ""
        block_start = _block_start_lineno(plan_text, block)
        for i, line in enumerate(block.splitlines()):
            m = _ANCHOR_LINE_RE.match(line.strip())
            if not m:
                continue
            parsed = parse_anchor_body(m.group(1), default_files)
            if not parsed:
                continue
            file_name, ln, sym = parsed
            _anchor_from_parsed(
                file_name,
                ln,
                sym,
                line.strip(),
                block_start + i,
                seen,
                anchors,
            )
    return anchors


def extract_colocated_anchors(plan_text: str) -> list[AnchorRef]:
    """Same-line backtick repo path + L ref (no lookback)."""
    anchors: list[AnchorRef] = []
    seen: set[tuple[str, int]] = set()
    for lineno, line in iter_lines_with_line_numbers(plan_text):
        if not _LINE_NUM_RE.search(line):
            continue
        if _ANCHOR_LINE_RE.match(line.strip()):
            continue
        file_refs = find_backtick_file_refs(line)
        if not file_refs:
            continue
        file_name = _normalize_file_path(file_refs[0])
        if "/" not in file_name and "\\" not in file_name:
            continue
        symbol = find_symbol_on_line(line)
        for ln in find_line_number_refs(line):
            _anchor_from_parsed(
                file_name,
                ln,
                symbol,
                line.strip(),
                lineno,
                seen,
                anchors,
            )
    return anchors


def audit_anchors(plan_text: str) -> dict:
    """Report declared-pin gaps vs prose-only line refs (sanity check / optimize gate)."""
    opt = extract_optimization_section(plan_text)
    cards_missing: list[str] = []
    files_not_plain: list[dict[str, str | int]] = []
    for block in split_card_blocks(opt):
        card = parse_card_block(block)
        if not card or card.get("type") != "code-gen":
            continue
        if not card.get("files"):
            continue
        agent_body = card.get("agent_body") or ""
        block_start = _block_start_lineno(plan_text, block)
        for i, line in enumerate(block.splitlines()):
            fm = _FILES_LINE_RE.match(line.strip())
            if not fm or not _MARKDOWN_LINK_IN_FILES_RE.search(fm.group(1)):
                continue
            files_not_plain.append(
                {
                    "card": card["key"],
                    "lineno": block_start + i,
                    "raw": fm.group(1).strip()[:160],
                }
            )
        if _is_trivial_agent_block(agent_body):
            continue
        if not _ANCHOR_LINE_RE.search(agent_body):
            cards_missing.append(card["key"])

    prose_refs: list[dict[str, str | int]] = []
    for lineno, line in iter_lines_with_line_numbers(plan_text):
        if not _LINE_NUM_RE.search(line):
            continue
        stripped = line.strip()
        if _ANCHOR_LINE_RE.match(stripped):
            continue
        file_refs = find_backtick_file_refs(line)
        if file_refs and "/" in _normalize_file_path(file_refs[0]):
            continue
        prose_refs.append({"lineno": lineno, "text": stripped[:160]})

    declared = extract_anchors(plan_text)
    return {
        "cards_missing_anchor": cards_missing,
        "files_not_plain_path": files_not_plain,
        "prose_line_refs": prose_refs,
        "declared_anchor_count": len(declared),
    }


def suggest_anchors_for_card(
    plan_text: str,
    card_key: str,
    repo_root: Path,
) -> list[dict[str, str | int | None]]:
    """rg-backed pin suggestions for Harden — agent pastes into Anchor: lines."""
    opt = extract_optimization_section(plan_text)
    card_data: dict | None = None
    for block in split_card_blocks(opt):
        card = parse_card_block(block)
        if card and card["key"] == card_key:
            card_data = card
            break
    if not card_data:
        return []

    agent_body = card_data.get("agent_body") or ""
    symbols: list[str] = []
    for m in re.finditer(r"Call-sites:\s*([^\n]+)", agent_body, re.IGNORECASE):
        for part in re.split(r",\s*", m.group(1).strip()):
            part = part.strip()
            if part.lower() in ("none", "n/a"):
                continue
            if ":" in part:
                symbols.append(part.rsplit(":", 1)[-1].strip())
            elif part:
                symbols.append(part)

    suggestions: list[dict[str, str | int | None]] = []
    for file_path in card_data.get("files") or []:
        norm = _normalize_file_path(file_path)
        resolved = repo_root / norm
        if not resolved.is_file():
            continue
        search_syms = symbols or [None]
        for sym in search_syms:
            if sym:
                try:
                    proc = subprocess.run(
                        [
                            "rg",
                            "-n",
                            rf"(?:def|class|async def)\s+{re.escape(sym)}\b",
                            str(resolved),
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                    )
                except FileNotFoundError:
                    return suggestions
                if proc.returncode != 0 or not proc.stdout.strip():
                    continue
                first = proc.stdout.strip().splitlines()[0]
                ln_s, _sep, _rest = first.partition(":")
                if ln_s.isdigit():
                    suggestions.append(
                        {
                            "card": card_key,
                            "file": norm,
                            "symbol": sym,
                            "line": int(ln_s),
                            "suggested_anchor": f"Anchor: {norm}::{sym}@L{ln_s}",
                            "source": "rg",
                        }
                    )
            else:
                suggestions.append(
                    {
                        "card": card_key,
                        "file": norm,
                        "symbol": None,
                        "line": None,
                        "suggested_anchor": f"Anchor: {norm}::<symbol>@L<line>",
                        "source": "template",
                    }
                )
    return suggestions


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
    """Declared pins only: Contracts:, card Anchor:, co-located path+L on same line."""
    opt = extract_optimization_section(plan_text)
    combined: list[AnchorRef] = []
    seen: set[tuple[str, int]] = set()
    for batch in (
        extract_anchors_from_contracts(plan_text, opt),
        extract_anchors_from_cards(plan_text),
        extract_colocated_anchors(plan_text),
    ):
        for anchor in batch:
            key = (anchor.file, anchor.line)
            if key in seen:
                continue
            seen.add(key)
            combined.append(anchor)
    return combined


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
    elif re.search(r"\bgate\b", title, re.IGNORECASE):
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
    if tests:
        tests = sanitize_tests_command(tests)
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


def _cmd_anchor_audit(args: argparse.Namespace) -> int:
    text = load_plan_text(args.plan)
    report = audit_anchors(text)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        missing = report["cards_missing_anchor"]
        plain = report["files_not_plain_path"]
        prose = report["prose_line_refs"]
        print(f"Declared anchors: {report['declared_anchor_count']}")
        if missing:
            print(f"Cards missing Anchor: ({len(missing)}): {', '.join(missing)}")
        if plain:
            print(f"Files: markdown links ({len(plain)}) - use plain repo-relative paths")
        if prose:
            print(f"Prose line refs not auto-verified ({len(prose)})")
        if not missing and not plain:
            print("Anchor shape OK for non-trivial code-gen cards")
    return 1 if report["cards_missing_anchor"] and args.strict else 0


def _cmd_suggest_anchors(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve() if args.repo_root else Path(".").resolve()
    text = load_plan_text(args.plan)
    keys: list[str] = []
    if args.card:
        keys = [args.card]
    else:
        report = audit_anchors(text)
        keys = report["cards_missing_anchor"]
    all_suggestions: list[dict] = []
    for key in keys:
        all_suggestions.extend(suggest_anchors_for_card(text, key, repo))
    if args.json:
        print(json.dumps(all_suggestions, indent=2))
    else:
        for s in all_suggestions:
            print(s.get("suggested_anchor", s))
    return 0


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

    p_aa = sub.add_parser("anchor-audit", help="Audit declared Anchor: pins vs prose L refs")
    p_aa.add_argument("--plan", required=True)
    p_aa.add_argument("--json", action="store_true")
    p_aa.add_argument("--strict", action="store_true", help="Exit 1 when cards lack Anchor:")
    p_aa.set_defaults(func=_cmd_anchor_audit)

    p_sa = sub.add_parser("suggest-anchors", help="rg-backed Anchor: suggestions for Harden")
    p_sa.add_argument("--plan", required=True)
    p_sa.add_argument("--card", default="", help="Card key (default: all missing Anchor:)")
    p_sa.add_argument("--repo-root", default=".")
    p_sa.add_argument("--json", action="store_true")
    p_sa.set_defaults(func=_cmd_suggest_anchors)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
