#!/usr/bin/env python3
"""Verify plan goal_card annotations for kanban-advanced optimization gate."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


DEFAULT_BUDGET = 2
GOAL_TRUE_RE = re.compile(
    r"goal_card\s*:\s*true",
    re.IGNORECASE,
)
ACCEPTANCE_RE = re.compile(r"^Acceptance\s*:", re.MULTILINE | re.IGNORECASE)
AGENT_BLOCK_RE = re.compile(r"```agent\b")
GOAL_RATIONALE_RE = re.compile(
    r"goal_rationale\s*:",
    re.IGNORECASE,
)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    body = parts[2]
    if yaml is None:
        return {}, body
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, body


def _goal_true_sections(body: str) -> list[str]:
    """Split on ### headers; return section titles with goal_card: true."""
    sections: list[str] = []
    chunks = re.split(r"(?=^###\s+)", body, flags=re.MULTILINE)
    for chunk in chunks:
        if not chunk.strip().startswith("###"):
            continue
        first_line = chunk.split("\n", 1)[0]
        if GOAL_TRUE_RE.search(chunk):
            sections.append(first_line.strip().lstrip("#").strip())
    return sections


def verify_plan(plan_path: Path) -> tuple[int, int, list[str]]:
    text = plan_path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    failures: list[str] = []
    warnings: list[str] = []

    budget = DEFAULT_BUDGET
    if "goal_card_budget" in meta:
        try:
            budget = int(meta["goal_card_budget"])
        except (TypeError, ValueError):
            warnings.append(f"Invalid goal_card_budget in frontmatter; using {DEFAULT_BUDGET}")

    goal_count = len(GOAL_TRUE_RE.findall(text))
    if goal_count > budget:
        failures.append(
            f"goal_card: true count ({goal_count}) exceeds goal_card_budget ({budget})"
        )
    if goal_count > DEFAULT_BUDGET and budget > DEFAULT_BUDGET:
        warnings.append(f"goal_card count {goal_count} > recommended max {DEFAULT_BUDGET}")

    if goal_count > 0 and not GOAL_RATIONALE_RE.search(text):
        failures.append("At least one goal_card: true but no goal_rationale: found in plan")

    for title in _goal_true_sections(body):
        section_chunks = re.split(r"(?=^###\s+)", body, flags=re.MULTILINE)
        section_text = ""
        for chunk in section_chunks:
            if title in chunk.split("\n", 1)[0]:
                section_text = chunk
                break
        if section_text and not ACCEPTANCE_RE.search(section_text):
            failures.append(f"goal_card section missing Acceptance: block — {title}")
        if section_text and not AGENT_BLOCK_RE.search(section_text):
            failures.append(f"goal_card section missing ```agent block — {title}")

    # Frontmatter workstreams list (optional structured form)
    workstreams = meta.get("workstreams")
    if isinstance(workstreams, list):
        ws_goal = sum(1 for w in workstreams if isinstance(w, dict) and w.get("goal_card") is True)
        if ws_goal != goal_count and goal_count > 0:
            warnings.append(
                f"Frontmatter workstreams goal_card count ({ws_goal}) "
                f"may not match inline goal_card: true markers ({goal_count})"
            )

    for msg in warnings:
        print(f"WARN: {msg}", file=sys.stderr)
    for msg in failures:
        print(f"FAIL: {msg}", file=sys.stderr)

    return len(failures), len(warnings), failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify plan goal_card annotations")
    parser.add_argument("--plan", required=True, help="Path to plan markdown file")
    args = parser.parse_args()
    plan_path = Path(args.plan)
    if not plan_path.is_file():
        print(f"FAIL: plan not found: {plan_path}", file=sys.stderr)
        return 2

    n_fail, n_warn, _ = verify_plan(plan_path)
    if n_fail:
        return 1
    if n_warn:
        print(f"PASS with {n_warn} warning(s)")
    else:
        print("PASS: goal_card checks OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
