"""Presentation acceptance checks (layout, a11y) for evaluation chain."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


def parse_acceptance_section(body: str, heading: str) -> list[str]:
    """Return bullet lines under ``Acceptance (layout):`` style headings."""
    pattern = re.compile(
        rf"^{re.escape(heading)}\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(body)
    if not match:
        return []
    rest = body[match.end() :]
    bullets: list[str] = []
    for line in rest.splitlines():
        stripped = line.strip()
        if not stripped:
            if bullets:
                break
            continue
        if re.match(r"^Acceptance\s*\(", stripped, re.I):
            break
        if re.match(r"^(Spec|Call-sites|Forbidden|Tests|Commit|Self-audit):", stripped, re.I):
            break
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
        elif bullets:
            break
    return bullets


def parse_surface_slots(text: str) -> list[str]:
    """Extract slot names from ``Surface-slots:`` block."""
    match = re.search(r"^Surface-slots:\s*$", text, re.I | re.MULTILINE)
    if not match:
        return []
    slots: list[str] = []
    for line in text[match.end() :].splitlines():
        stripped = line.strip()
        if not stripped:
            if slots:
                break
            continue
        if stripped.startswith("#") or re.match(r"^####", stripped):
            break
        m = re.match(r"^([a-z][a-z0-9_]*)\s*:", stripped)
        if m:
            slots.append(m.group(1))
        elif slots:
            break
    return slots


def parse_presentation_acceptance(body: str) -> dict[str, Any]:
    """Structured presentation acceptance from card/plan body."""
    layout_bullets = parse_acceptance_section(body, "Acceptance (layout)")
    if not layout_bullets:
        layout_bullets = parse_acceptance_section(body, "Acceptance (presentation)")
    a11y_bullets = parse_acceptance_section(body, "Acceptance (a11y)")
    slots = parse_surface_slots(body)
    layout_rules: list[dict[str, str]] = []
    for bullet in layout_bullets:
        lo = re.search(
            r"line number of [`']?([^`']+)[`']?\s*<\s*line number of [`']?([^`']+)[`']?",
            bullet,
            re.I,
        )
        if lo:
            layout_rules.append(
                {"kind": "line_order", "before": lo.group(1).strip(), "after": lo.group(2).strip()}
            )
        if re.search(r"matches|transition|fade|pattern", bullet, re.I):
            layout_rules.append({"kind": "css_class", "bullet": bullet})
    a11y_rules: list[dict[str, str]] = []
    for bullet in a11y_bullets:
        if re.search(r"aria-live|live.region", bullet, re.I):
            a11y_rules.append({"kind": "live_region", "bullet": bullet})
        if re.search(r"reduced.motion|prefers-reduced-motion|motion-reduce", bullet, re.I):
            a11y_rules.append({"kind": "reduced_motion", "bullet": bullet})
    return {
        "layout": layout_rules,
        "a11y": a11y_rules,
        "surface_slots": slots,
    }


def load_ui_stack(repo_root: Path) -> dict[str, Any]:
    """Read ui_stack from overlay YAML (minimal parse)."""
    overlay = repo_root / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
    if not overlay.is_file():
        return {}
    in_ui = False
    ui: dict[str, Any] = {}
    motion: dict[str, str] = {}
    for line in overlay.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("ui_stack:"):
            in_ui = True
            continue
        if not in_ui:
            continue
        if stripped and not line.startswith(" ") and not line.startswith("\t"):
            break
        if stripped.startswith("framework:"):
            ui["framework"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif stripped.startswith("page_glob:"):
            ui["page_glob"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif stripped.startswith("test_command:"):
            ui["test_command"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif stripped.startswith("reduced_query:"):
            motion["reduced_query"] = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif stripped.startswith("entry_transition_pattern:"):
            motion["entry_transition_pattern"] = (
                stripped.split(":", 1)[1].strip().strip('"').strip("'")
            )
        elif stripped == "motion:":
            continue
    if motion:
        ui["motion"] = motion
    return ui


def _rg_line_number(pattern: str, path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        result = subprocess.run(
            ["rg", "-n", "-m", "1", pattern, str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(pattern, line):
                return i
        return None
    if result.returncode != 0:
        return None
    first = result.stdout.splitlines()[0]
    return int(first.split(":", 1)[0])


def _find_route_shell(repo_root: Path, ui_stack: dict[str, Any]) -> Path | None:
    page_glob = (ui_stack or {}).get("page_glob") or "frontend/**/page.tsx"
    # naive: take first glob match via rg file list
    try:
        result = subprocess.run(
            ["rg", "--files", "-g", page_glob.replace("**/", "*/")],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
        )
        if result.returncode == 0 and result.stdout.strip():
            rel = result.stdout.strip().splitlines()[0]
            return repo_root / rel
    except FileNotFoundError:
        pass
    for candidate in repo_root.rglob("page.tsx"):
        if "frontend" in candidate.parts:
            return candidate
    return None


def check_line_order(
    repo_root: Path,
    before_anchor: str,
    after_anchor: str,
    ui_stack: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    shell = _find_route_shell(repo_root, ui_stack or {})
    if shell is None:
        return True, "no route shell found — skip line_order"
    lb = _rg_line_number(re.escape(before_anchor), shell)
    la = _rg_line_number(re.escape(after_anchor), shell)
    if lb is None or la is None:
        return False, f"anchors not found in {shell.name}: before={lb} after={la}"
    if lb >= la:
        return False, f"line_order fail: {before_anchor}@{lb} >= {after_anchor}@{la} in {shell}"
    return True, f"line_order ok: {lb} < {la}"


def check_reduced_motion(repo_root: Path, ui_stack: dict[str, Any] | None = None) -> tuple[bool, str]:
    shell = _find_route_shell(repo_root, ui_stack or {})
    if shell is None:
        return True, "no route shell — skip reduced_motion"
    text = shell.read_text(encoding="utf-8", errors="replace")
    patterns = [
        r"prefers-reduced-motion",
        r"motion-reduce",
        r"reduce-motion",
    ]
    rq = ((ui_stack or {}).get("motion") or {}).get("reduced_query", "")
    if rq:
        patterns.insert(0, re.escape(rq.split(":")[0].strip()))
    for pat in patterns:
        if re.search(pat, text, re.I):
            return True, f"reduced_motion guard found ({pat})"
    return False, "E029: no reduced-motion guard in route shell"


def check_entry_transition(
    repo_root: Path,
    ui_stack: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    shell = _find_route_shell(repo_root, ui_stack or {})
    if shell is None:
        return True, "no route shell — skip entry_transition"
    pattern = ((ui_stack or {}).get("motion") or {}).get(
        "entry_transition_pattern",
        r"fade-in|transition-opacity|animate-in",
    )
    text = shell.read_text(encoding="utf-8", errors="replace")
    if re.search(pattern, text, re.I):
        return True, "entry transition pattern found"
    return False, "E028: entry transition pattern missing in route shell"


def run_presentation_checks(
    card_body: str,
    workspace: str,
    rules_json: str = "",
) -> tuple[bool, str | None]:
    """Run all presentation acceptance checks. Returns (ok, error_code_or_none)."""
    repo = Path(workspace)
    ui_stack = load_ui_stack(repo)
    if rules_json:
        try:
            ui_stack = {**ui_stack, **json.loads(rules_json)}
        except json.JSONDecodeError:
            pass
    parsed = parse_presentation_acceptance(card_body)
    if not parsed["layout"] and not parsed["a11y"]:
        if any(
            x in card_body
            for x in ("Acceptance (layout):", "Acceptance (presentation):", "Acceptance (a11y):")
        ):
            return False, "E028"
        return True, None
    for rule in parsed["layout"]:
        if rule.get("kind") == "line_order":
            ok, msg = check_line_order(
                repo,
                rule["before"],
                rule["after"],
                ui_stack,
            )
            if not ok:
                return False, "E028"
    needs_transition = any(r.get("kind") == "css_class" for r in parsed["layout"])
    if needs_transition:
        ok, _ = check_entry_transition(repo, ui_stack)
        if not ok:
            return False, "E028"
    if parsed["a11y"]:
        ok, _ = check_reduced_motion(repo, ui_stack)
        if not ok:
            return False, "E029"
    return True, None


def card_attestation_path(repo_root: Path, plan_id: str, card_key: str) -> Path:
    return repo_root / ".hermes" / "kanban" / "card-attestations" / f"{plan_id}-{card_key}.json"


def verification_deploy_attested(repo_root: Path, plan_id: str, card_key: str) -> bool:
    path = card_attestation_path(repo_root, plan_id, card_key)
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return bool(data.get("plan_id")) and bool(data.get("card_key") or data.get("card"))
