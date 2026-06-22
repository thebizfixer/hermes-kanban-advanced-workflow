#!/usr/bin/env python3
"""Auto-stamp card bodies at decomposition from plan bundles and parent graph."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_LIB = Path(__file__).resolve().parent
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from plan_parse import load_plan_text, parse_frontmatter  # noqa: E402

_PARENT_KEY_RE = re.compile(r"card\s*(\d+)", re.IGNORECASE)
_AGENT_FIELD_RE = re.compile(
    r"^(Call-sites|Acceptance|Spec|Forbidden):\s*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)


def normalize_parent_key(ref: str) -> str:
    raw = (ref or "").strip().lower().replace(" ", "").replace("-", "")
    if not raw:
        return ""
    if raw.startswith("card") and raw[4:].isdigit():
        return raw
    m = _PARENT_KEY_RE.search(ref)
    if m:
        return f"card{m.group(1)}"
    return raw


def parent_keys_for_card(card: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for field in ("wave_parent", "ordinal_parent"):
        raw = card.get(field)
        if not raw:
            continue
        for part in re.split(r"[,;]\s*", str(raw)):
            key = normalize_parent_key(part)
            if key and key not in keys:
                keys.append(key)
    return keys


def parent_branches_for(card: dict[str, Any], plan_id: str) -> list[str]:
    branches: list[str] = []
    for key in parent_keys_for_card(card):
        branch = f"kanban/{plan_id}/{key}"
        if branch not in branches:
            branches.append(branch)
    return branches


def extract_agent_field(agent_body: str, field_name: str) -> str:
    if not agent_body:
        return ""
    lines: list[str] = []
    capture = False
    for line in agent_body.splitlines():
        m = re.match(rf"^{re.escape(field_name)}:\s*(.*)$", line, re.IGNORECASE)
        if m:
            capture = True
            rest = m.group(1).strip()
            if rest:
                lines.append(rest)
            continue
        if capture:
            if re.match(r"^[A-Za-z][A-Za-z0-9_-]*:", line) and not line.startswith("-"):
                break
            if line.strip():
                lines.append(line.rstrip())
    return "\n".join(lines).strip()


def load_acceptance_matrix(plan_path: str | Path | None) -> dict[str, Any]:
    """Frontmatter ``acceptance_matrix`` wins; else derive from optimization section."""
    if not plan_path:
        return {}
    path = Path(plan_path)
    if not path.is_file():
        return {}
    try:
        text = load_plan_text(path)
        fm, _ = parse_frontmatter(text)
    except Exception:
        return {}
    raw = fm.get("acceptance_matrix")
    if raw:
        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    try:
        from plan_parse import extract_acceptance_matrix

        return extract_acceptance_matrix(text)
    except Exception:
        return {}


def _matrix_items(matrix: dict[str, Any], card_key: str) -> list[str]:
    for candidate in (card_key, card_key.replace("card", "Card ")):
        val = matrix.get(candidate)
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
        if isinstance(val, str) and val.strip():
            return [val.strip()]
    return []


def stamp_impl_card(
    card: dict[str, Any],
    *,
    plan_id: str,
    plan_file_rel: str = "",
    acceptance_matrix: dict[str, list[str]] | None = None,
    wave_baseline: str = "",
) -> None:
    """Mutate card body with decomposition auto-stamps (idempotent)."""
    if card.get("type") not in ("code-gen", "verification", "manual"):
        return

    body = card.get("body", "") or ""
    agent = card.get("agent_body") or ""
    stamps: list[str] = []

    if plan_id and not re.search(r"^plan_id:\s*\S+", body, re.MULTILINE | re.IGNORECASE):
        stamps.append(f"plan_id: {plan_id}")
    if plan_file_rel and "plan_file:" not in body:
        stamps.append(f"plan_file: {plan_file_rel}")
    key = card.get("key", "")
    if key and "card_key:" not in body:
        stamps.append(f"card_key: {key}")

    parents = parent_keys_for_card(card)
    if parents and not re.search(r"^parents:\s*\S+", body, re.MULTILINE | re.IGNORECASE):
        stamps.append(f"parents: {', '.join(parents)}")

    branches = parent_branches_for(card, plan_id)
    if branches and "Parent-branches:" not in body:
        stamps.append(f"Parent-branches: {', '.join(branches)}")

    call_sites = extract_agent_field(agent, "Call-sites")
    if call_sites and "Call-sites:" not in body:
        stamps.append(f"Call-sites: {call_sites}")

    acceptance = extract_agent_field(agent, "Acceptance")
    if acceptance and "Acceptance:" not in body:
        stamps.append("Acceptance:")
        stamps.extend(f"- {line}" if not line.startswith("-") else line for line in acceptance.splitlines())

    matrix = acceptance_matrix or {}
    checklist = _matrix_items(matrix, key) if key else []
    if checklist and "Acceptance-checklist:" not in body:
        stamps.append("Acceptance-checklist:")
        stamps.extend(f"- {item}" if not item.startswith("-") else item for item in checklist)

    # Wave baseline for verification cards (tracks the commit SHA at decompose time)
    if wave_baseline and card.get("type") == "verification":
        if "Baseline:" not in body:
            stamps.append(f"Baseline: {wave_baseline}")
        if "Wave-baseline:" not in body:
            stamps.append(f"Wave-baseline: {wave_baseline}")

    if not stamps:
        return
    card["body"] = "\n".join(stamps) + "\n\n" + body


def stamp_all_impl_cards(
    cards: list[dict[str, Any]],
    *,
    plan_id: str,
    plan_file_rel: str = "",
    plan_path: str | Path | None = None,
    wave_baseline: str = "",
) -> None:
    matrix = load_acceptance_matrix(plan_path)
    for card in cards:
        if card.get("type") in ("gate", "root", "audit"):
            continue
        stamp_impl_card(
            card,
            plan_id=plan_id,
            plan_file_rel=plan_file_rel,
            acceptance_matrix=matrix,
            wave_baseline=wave_baseline,
        )
