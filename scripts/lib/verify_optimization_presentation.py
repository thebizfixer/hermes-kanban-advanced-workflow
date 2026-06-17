"""Presentation-related verify_optimization checks (19–21)."""

from __future__ import annotations

import re
from pathlib import Path


def count_presentation_acceptance_gaps(plan_text: str) -> int:
    """Check 19 — layout verbs in agent blocks require Acceptance (layout|presentation)."""
    blocks = re.findall(r"```agent\s*\n(.*?)```", plan_text, re.DOTALL)
    fail = 0
    for block in blocks:
        if not re.search(
            r"(layout|above|below|fade|choreograph|render order|surface.?slot)",
            block,
            re.I,
        ):
            continue
        if not re.search(r"route shell|page_glob|\.tsx|\.vue|\.svelte", block, re.I):
            continue
        if "Acceptance (layout):" not in block and "Acceptance (presentation):" not in block:
            fail += 1
    return fail


def missing_ui_stack_or_surface_slots(plan_text: str) -> int:
    """Check 20 — frontend plans need ui_stack: or Surface-slots: (0 = ok)."""
    has_frontend = bool(re.search(r"Files:.*\.(tsx|vue|svelte)", plan_text, re.I))
    if not has_frontend:
        return 0
    if re.search(r"^ui_stack:", plan_text, re.M) or re.search(r"^Surface-slots:", plan_text, re.M):
        return 0
    return 1


def count_motion_without_a11y(plan_text: str) -> int:
    """Check 21 — motion verbs require Acceptance (a11y):."""
    blocks = re.findall(r"```agent\s*\n(.*?)```", plan_text, re.DOTALL)
    fail = 0
    for block in blocks:
        if re.search(r"\b(fade|slide|choreograph|animate)\b", block, re.I):
            if "Acceptance (a11y):" not in block:
                fail += 1
    return fail


def load_plan_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: verify_optimization_presentation.py <pres|ui|a11y> <plan.md>", file=sys.stderr)
        raise SystemExit(2)
    mode, plan_path = sys.argv[1], sys.argv[2]
    text = load_plan_text(plan_path)
    if mode == "pres":
        print(count_presentation_acceptance_gaps(text))
    elif mode == "ui":
        print(missing_ui_stack_or_surface_slots(text))
    elif mode == "a11y":
        print(count_motion_without_a11y(text))
    else:
        raise SystemExit(f"unknown mode: {mode}")
