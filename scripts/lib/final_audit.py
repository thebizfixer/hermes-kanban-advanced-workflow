"""Core logic for final_audit_sanity.py — Tier 1/2 audits and remediation spawn."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DOC_PATH_PREFIXES = (
    "plugin/",
    "wiki/",
    "docs/",
    "dashboard/",
    "AGENTS.md",
    "llms.txt",
    "kanban-config.example.yaml",
    "schema/",
)
_DOC_EXTENSIONS = {".md", ".yaml", ".yml", ".txt", ".json"}
_UNPLANNED_ALLOWLIST = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "uv.lock",
}
_PROCEDURAL_ACCEPTANCE_RE = re.compile(
    r"(?i)(done when|verify:|pytest|bash\s|python3?\s|\brg\b|hermes\s)",
)


@dataclass
class Violation:
    tier: str
    class_name: str
    path: str
    detail: str
    source_card_key: str = ""
    remediates_task_id: str = ""
    severity: str = "fail"

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": self.class_name,
            "path": self.path,
            "detail": self.detail,
            "source_card_key": self.source_card_key,
            "remediates_task_id": self.remediates_task_id,
            "severity": self.severity,
            "tier": self.tier,
        }


@dataclass
class AuditContext:
    plan_id: str
    repo_root: Path
    baseline: str
    plan_path: Path
    plan_text: str
    cards: list[dict[str, Any]]
    overrides: list[dict[str, str]] = field(default_factory=list)
    max_remediation_rounds: int = 2


def _run_git(args: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(repo_root),
        timeout=120,
    )


def resolve_working_branch(repo_root: Path) -> str:
    overlay = repo_root / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
    if overlay.is_file():
        for line in overlay.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("working_branch:"):
                return line.split(":", 1)[1].strip().strip('"').strip("'") or "main"
    return "main"


def read_overlay_audit_settings(repo_root: Path) -> tuple[list[dict[str, str]], int]:
    """Load final_audit_overrides and final_audit_max_remediation_rounds from overlay."""
    overlay = repo_root / ".hermes" / "kanban-overrides" / "kanban-config.yaml"
    overrides: list[dict[str, str]] = []
    max_rounds = 2
    if not overlay.is_file():
        return overrides, max_rounds
    try:
        import yaml

        data = yaml.safe_load(overlay.read_text(encoding="utf-8")) or {}
        raw = data.get("final_audit_overrides") or []
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict):
                    overrides.append(
                        {
                            "signal": str(entry.get("signal", "")),
                            "path": str(entry.get("path", "")).replace("\\", "/"),
                            "rationale": str(entry.get("rationale", "")),
                        }
                    )
        mr = data.get("final_audit_max_remediation_rounds")
        if isinstance(mr, int) and mr >= 1:
            max_rounds = mr
    except Exception:
        pass
    return overrides, max_rounds


def extract_field(body: str, field_name: str) -> str:
    m = re.search(rf"(?m)^{re.escape(field_name)}:\s*(.+)$", body, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def extract_list_field(body: str, field_name: str) -> list[str]:
    val = extract_field(body, field_name)
    if not val:
        return []
    return [p.strip() for p in val.replace("\n", " ").split(",") if p.strip()]


def extract_acceptance_bullets(body: str) -> list[str]:
    m = re.search(r"(?m)^Acceptance:\s*(.*)$", body)
    if not m:
        return []
    rest = body[m.start() :]
    lines: list[str] = []
    for line in rest.splitlines()[1:]:
        if re.match(r"^[A-Za-z_-]+:", line) and not line.strip().startswith("-"):
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            lines.append(stripped[2:].strip())
    if not lines and m.group(1).strip():
        lines.append(m.group(1).strip())
    return lines


def extract_call_sites(body: str) -> list[str]:
    m = re.search(r"(?m)^Call-sites:\s*(.*)$", body)
    if not m:
        return []
    val = m.group(1).strip()
    if val:
        return [s.strip() for s in val.split(",") if s.strip()]
    sites: list[str] = []
    for line in body.splitlines():
        if line.strip().startswith("- ") and ":" in line:
            sites.append(line.strip()[2:].strip())
    return sites


def resolve_baseline_sha(
    audit_body: str,
    repo_root: Path,
    working_branch: str | None = None,
) -> str:
    stamped = extract_field(audit_body, "Audit-baseline-sha")
    if stamped:
        return stamped
    branch = working_branch or resolve_working_branch(repo_root)
    result = _run_git(["rev-parse", f"origin/{branch}"], repo_root)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    result = _run_git(["rev-parse", "HEAD"], repo_root)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return f"origin/{branch}"


def git_changed_paths(baseline: str, repo_root: Path) -> set[str]:
    if ".." in baseline:
        diff_range = baseline
    else:
        diff_range = f"{baseline}..HEAD"
    result = _run_git(["diff", "--name-only", diff_range], repo_root)
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return {p.strip().replace("\\", "/") for p in result.stdout.splitlines() if p.strip()}


def file_has_diff(path: str, baseline: str, repo_root: Path) -> bool:
    if ".." in baseline:
        diff_range = baseline
    else:
        diff_range = f"{baseline}..HEAD"
    result = _run_git(["diff", "--stat", diff_range, "--", path], repo_root)
    if result.returncode != 0:
        return False
    return path in result.stdout and "|" in result.stdout


def collect_plan_files(plan_text: str) -> set[str]:
    from plan_parse import extract_files_from_text

    return {p.replace("\\", "/") for p in extract_files_from_text(plan_text)}


def collect_card_surfaces(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map task_id -> parsed surfaces for done impl/remediation cards."""
    from card_body import parse_card_body

    out: dict[str, dict[str, Any]] = {}
    for card in cards:
        body = card.get("body", "")
        if re.search(r"Type:\s*audit", body, re.I):
            continue
        if card.get("status", "").lower() not in {"done", "completed", "archived"}:
            continue
        tid = card.get("task_id", "")
        parsed = parse_card_body(body)
        files = extract_list_field(body, "Files")
        if not files:
            files = parsed.get("files") or []
        out[tid] = {
            "task_id": tid,
            "body": body,
            "files": [f.replace("\\", "/") for f in files],
            "acceptance": extract_acceptance_bullets(body),
            "call_sites": extract_call_sites(body),
            "plan_file": extract_field(body, "plan_file"),
            "commit": (parsed.get("commit") or extract_field(body, "Commit")).strip(),
        }
    return out


def _prior_commit_search_baseline(baseline: str) -> str:
    """Git rev for find_prior_commit log scan (matches eval-chain baseline resolution)."""
    if ".." in baseline:
        return baseline.split("..", 1)[0]
    return baseline


def _path_cleared_by_prior_commit(
    path: str,
    card_surfaces: dict[str, dict[str, Any]],
    baseline: str,
    repo_root: Path,
) -> str | None:
    """
    Return prior commit SHA when E001-equivalent evidence clears a zero-diff plan file.

    Scans done cards whose Files: include path and reuses find_prior_commit (same helper
    as kanban_evaluation_chain.py step 1 / E001).
    """
    from card_body import find_prior_commit

    norm = path.replace("\\", "/")
    search_base = _prior_commit_search_baseline(baseline)
    workspace = str(repo_root)
    for surf in card_surfaces.values():
        files = [f.replace("\\", "/") for f in surf.get("files") or []]
        if norm not in files:
            continue
        commit_line = (surf.get("commit") or "").strip()
        if not commit_line:
            continue
        prior = find_prior_commit(commit_line, files, workspace, baseline=search_base)
        if prior:
            return prior
    return None


def run_tier1(ctx: AuditContext) -> list[Violation]:
    violations: list[Violation] = []
    try:
        changed = git_changed_paths(ctx.baseline, ctx.repo_root)
    except RuntimeError as exc:
        raise exc

    plan_files = collect_plan_files(ctx.plan_text)
    card_surfaces = collect_card_surfaces(ctx.cards)
    expected_files: set[str] = set(plan_files)
    card_file_map: dict[str, str] = {}
    for tid, surf in card_surfaces.items():
        for f in surf["files"]:
            expected_files.add(f)
            card_file_map.setdefault(f, tid)

    for path in sorted(plan_files):
        norm = path.replace("\\", "/")
        if norm in changed or file_has_diff(norm, ctx.baseline, ctx.repo_root):
            continue
        prior_sha = _path_cleared_by_prior_commit(norm, card_surfaces, ctx.baseline, ctx.repo_root)
        if prior_sha:
            continue
        violations.append(
            Violation(
                tier="tier1",
                class_name="plan_file_zero_diff",
                path=norm,
                detail=f"Planned file has zero diff vs baseline {ctx.baseline[:12]}",
                remediates_task_id=card_file_map.get(norm, ""),
            )
        )

    for tid, surf in card_surfaces.items():
        for bullet in surf["acceptance"]:
            if not bullet.strip():
                continue
            if not _acceptance_verifiable(bullet, surf["files"], ctx.repo_root):
                violations.append(
                    Violation(
                        tier="tier1",
                        class_name="acceptance_miss",
                        path=surf["files"][0] if surf["files"] else "",
                        detail=f"Acceptance not verifiable: {bullet[:200]}",
                        source_card_key=tid,
                        remediates_task_id=tid,
                    )
                )
        for site in surf["call_sites"]:
            if not _call_site_resolvable(site, ctx.repo_root):
                violations.append(
                    Violation(
                        tier="tier1",
                        class_name="call_site_miss",
                        path=site.split(":")[0] if ":" in site else site,
                        detail=f"Call-site not resolvable: {site}",
                        source_card_key=tid,
                        remediates_task_id=tid,
                    )
                )

    for path in sorted(changed):
        norm = path.replace("\\", "/")
        if norm in expected_files:
            continue
        base = Path(norm).name
        if base in _UNPLANNED_ALLOWLIST or norm.endswith(".pyc"):
            continue
        if "__pycache__" in norm or norm.startswith(".hermes/"):
            continue
        violations.append(
            Violation(
                tier="tier1",
                class_name="unplanned_change",
                path=norm,
                detail="Changed path not in plan or card Files union",
            )
        )

    todo_drift = _check_plan_todo_drift(ctx.plan_text, ctx.cards)
    violations.extend(todo_drift)
    violations.extend(_check_verification_deploy_attestations(ctx))
    violations.extend(_check_presentation_acceptance_memory(ctx))
    return violations


def _card_key_from_audit_body(body: str, task_id: str) -> str:
    m = re.search(r"card_key:\s*(\S+)", body, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"Task\s+\S+:\s*(.+)", body)
    if m:
        slug = re.sub(r"[^a-z0-9]+", "-", m.group(1).lower()).strip("-")
        if slug:
            return slug[:64]
    return task_id


def _check_verification_deploy_attestations(ctx: AuditContext) -> list[Violation]:
    """Fail when verification-deploy cards reached terminal state without card-attestation."""
    violations: list[Violation] = []
    try:
        from card_body import is_verification_deploy, parse_card_body
        from presentation_acceptance import verification_deploy_attested
    except ImportError:
        return violations

    for card in ctx.cards:
        body = card.get("body", "")
        status = (card.get("status") or "").lower()
        if status not in {"done", "completed", "archived"}:
            continue
        parsed = parse_card_body(body)
        if not is_verification_deploy(parsed, body):
            continue
        plan_id = parsed.get("plan_id") or ctx.plan_id
        card_key = _card_key_from_audit_body(body, card.get("task_id", card.get("id", "")))
        if plan_id and verification_deploy_attested(ctx.repo_root, plan_id, card_key):
            continue
        violations.append(
            Violation(
                tier="tier1",
                class_name="verification_deploy_unattested",
                path=str(
                    ctx.repo_root
                    / ".hermes"
                    / "kanban"
                    / "card-attestations"
                    / f"{plan_id}-{card_key}.json"
                ),
                detail="verification-deploy card archived without card-attestation JSON",
                source_card_key=card_key,
                remediates_task_id=card.get("task_id", card.get("id", "")),
            )
        )
    return violations


def _check_presentation_acceptance_memory(ctx: AuditContext) -> list[Violation]:
    """Warn when plan memory acceptance_matrix is empty but plan declares presentation acceptance."""
    violations: list[Violation] = []
    mem_path = ctx.repo_root / ".hermes" / "kanban" / "memory" / f"{ctx.plan_id}.json"
    if not re.search(
        r"Acceptance \(layout\)|Acceptance \(presentation\)|Acceptance \(a11y\)",
        ctx.plan_text,
        re.I,
    ):
        return violations
    matrix: dict[str, Any] = {}
    if mem_path.is_file():
        try:
            matrix = json.loads(mem_path.read_text(encoding="utf-8")).get("acceptance_matrix") or {}
        except (json.JSONDecodeError, OSError):
            matrix = {}
    if matrix.get("presentation_cards") or matrix.get("surface_slots"):
        return violations
    violations.append(
        Violation(
            tier="tier1",
            class_name="acceptance_matrix_missing",
            path=str(mem_path),
            detail="Plan declares presentation acceptance but plan memory lacks acceptance_matrix — re-run decompose",
            severity="warn",
        )
    )
    return violations


def _acceptance_verifiable(bullet: str, files: list[str], repo_root: Path) -> bool:
    """Light heuristic: procedural bullets pass; symbols checked with word boundaries."""
    if _PROCEDURAL_ACCEPTANCE_RE.search(bullet):
        return True
    if not files:
        return True
    for f in files:
        full = repo_root / f
        if not full.is_file():
            return False
    sym = re.search(r"`([^`]+)`", bullet)
    if sym:
        token = sym.group(1).strip()
        for f in files:
            text = (repo_root / f).read_text(encoding="utf-8", errors="replace")
            if re.search(rf"\b{re.escape(token)}\b", text):
                return True
            if "." in token:
                short = token.split(".")[-1]
                if re.search(rf"\b{re.escape(short)}\b", text):
                    return True
        return False
    return True


def _call_site_resolvable(site: str, repo_root: Path) -> bool:
    if ":" not in site:
        return (repo_root / site).exists()
    path, symbol = site.split(":", 1)
    full = repo_root / path.strip()
    if not full.is_file():
        return False
    text = full.read_text(encoding="utf-8", errors="replace")
    symbol = symbol.strip()
    if re.search(rf"\b{re.escape(symbol)}\b", text):
        return True
    if "." in symbol:
        short = symbol.split(".")[-1]
        if re.search(rf"\b{re.escape(short)}\b", text):
            return True
    return False


def _check_plan_todo_drift(plan_text: str, cards: list[dict[str, Any]]) -> list[Violation]:
    if not plan_text.startswith("---"):
        return []
    end = plan_text.find("\n---", 3)
    if end == -1:
        return []
    fm = plan_text[3:end]
    if "todos:" not in fm:
        return []
    pending_impl = sum(
        1
        for c in cards
        if c.get("status", "").lower() not in {"done", "completed", "archived", "gave_up"}
        and re.search(r"```agent", c.get("body", ""))
    )
    if pending_impl > 0 and "status: completed" in fm:
        return [
            Violation(
                tier="tier1",
                class_name="plan_todo_drift",
                path="",
                detail=f"Plan todos show completed but {pending_impl} impl cards still open",
                severity="warn",
            )
        ]
    return []


def _is_doc_path(path: str) -> bool:
    norm = path.replace("\\", "/")
    if norm in {"AGENTS.md", "llms.txt", "kanban-config.example.yaml"}:
        return True
    return any(norm.startswith(p) for p in _DOC_PATH_PREFIXES)


def _required_doc_surfaces(code_path: str) -> list[str]:
    norm = code_path.replace("\\", "/")
    if "plugin/config_overlay.py" in norm:
        return [
            "wiki/configuration.md",
            "kanban-config.example.yaml",
            "schema/kanban-config.schema.json",
        ]
    if norm.startswith("scripts/") and (norm.endswith(".sh") or "/lib/" in norm):
        req = ["docs/reference/scripts.md"]
        if norm in {
            "scripts/auto_unblock.sh",
            "scripts/board_keeper.sh",
            "scripts/kanban_lifecycle_notify.sh",
            "scripts/kanban_intervention_inc.sh",
            "scripts/kanban_git_ops.sh",
            "scripts/coding_agent_invoke.sh",
            "scripts/worktree_setup.sh",
        } or norm.startswith("scripts/lib/"):
            req.append("plugin/script_materialize.py")
        return req
    if "bootstrap" in norm.lower() or "hermes_kanban_bootstrap" in norm:
        return ["wiki/bootstrap.md", "dashboard/API.md", "llms.txt"]
    if norm.startswith("plugin/skills/") and norm.endswith("SKILL.md"):
        return [norm]
    if norm.startswith("dashboard/"):
        return ["dashboard/API.md"]
    return []


def _doc_mentions_feature(doc_path: Path, code_path: str) -> bool:
    if not doc_path.is_file():
        return False
    text = doc_path.read_text(encoding="utf-8", errors="replace")
    stem = Path(code_path).stem
    name = Path(code_path).name
    norm = code_path.replace("\\", "/")
    tokens = {name, stem, norm}
    if norm.startswith("scripts/"):
        tokens.add(name)
        tokens.add(f"scripts/{name}")
    if "script_materialize.py" in text and norm.startswith("scripts/"):
        return True
    return any(token and token in text for token in tokens)


def run_tier2(ctx: AuditContext, tier1_changed: set[str]) -> list[Violation]:
    violations: list[Violation] = []
    scope = set(tier1_changed)
    for path in tier1_changed:
        if _is_doc_path(path):
            scope.add(path)

    for code_path in sorted(scope):
        if _is_doc_path(code_path) and not code_path.startswith("plugin/"):
            continue
        if code_path.endswith(".md") and "SKILL.md" not in code_path:
            continue
        for doc in _required_doc_surfaces(code_path):
            full_doc = ctx.repo_root / doc
            if not _doc_mentions_feature(full_doc, code_path):
                v = Violation(
                    tier="tier2",
                    class_name="doc_coverage_gap",
                    path=code_path,
                    detail=f"Required doc surface `{doc}` missing mention of {code_path}",
                )
                violations.append(_apply_override(v, ctx.overrides))
    return [v for v in violations if v.severity != "approved_skip" or v.class_name == "approved_skip"]


def _apply_override(v: Violation, overrides: list[dict[str, str]]) -> Violation:
    for entry in overrides:
        if entry.get("signal") == v.class_name and entry.get("path") in {v.path, ""}:
            return Violation(
                tier=v.tier,
                class_name="approved_skip",
                path=v.path,
                detail=entry.get("rationale") or v.detail,
                source_card_key=v.source_card_key,
                remediates_task_id=v.remediates_task_id,
                severity="approved_skip",
            )
    return v


def write_tier_report(
    report_dir: Path,
    plan_id: str,
    tier: str,
    violations: list[Violation],
    extra: dict[str, Any] | None = None,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "plan_id": plan_id,
        "tier": tier,
        "violation_count": sum(1 for v in violations if v.severity == "fail"),
        "violations": [v.to_dict() for v in violations if v.severity == "fail"],
        "warnings": [v.to_dict() for v in violations if v.severity == "warn"],
        "approved_skips": [v.to_dict() for v in violations if v.severity == "approved_skip"],
    }
    if extra:
        payload.update(extra)
    dest = report_dir / f"{plan_id}_audit_{tier}.json"
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest


def acceptance_template(class_name: str, path: str, detail: str) -> list[str]:
    templates = {
        "plan_file_zero_diff": [
            f"`git diff --stat` shows >0 lines for `{path}` vs audit baseline, "
            "or a done card `Commit:` matches an earlier commit touching that card's `Files:` (E001 prior-commit rule)"
        ],
        "acceptance_miss": [f"Acceptance bullet satisfied in merged tree at `{path}`"],
        "call_site_miss": [f"Call-site symbol resolvable: {detail}"],
        "unplanned_change": [f"Path `{path}` covered by plan/card Files or reverted"],
        "plan_todo_drift": ["Plan frontmatter todos align with board status"],
        "doc_coverage_gap": [f"Required doc surface updated for `{path}` per final-audit-doc-coverage.md"],
    }
    return templates.get(class_name, [detail or f"Resolve {class_name} at {path}"])


def tests_for_violation(v: Violation) -> str:
    if v.tier == "tier2" or _is_doc_path(v.path):
        return "doc: link-check"
    if v.path.endswith(".py"):
        return f"code: pytest -q -- {v.path}"
    return "doc: link-check"


def group_remediation_cards(violations: list[Violation]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, frozenset[str]], list[Violation]] = {}
    for v in violations:
        if v.severity != "fail":
            continue
        key = _remediation_group_key(v)
        groups.setdefault(key, []).append(v)
    cards: list[dict[str, Any]] = []
    for (remediates, files), group in groups.items():
        paths = sorted(p for p in files if not p.startswith("__nopath__:"))
        if not paths:
            paths = sorted({g.path for g in group if g.path})
        missed = [f"- [{g.tier}] {g.class_name}: {g.detail}" for g in group]
        acc: list[str] = []
        for g in group:
            acc.extend(acceptance_template(g.class_name, g.path, g.detail))
        tests = tests_for_violation(group[0])
        cards.append(
            {
                "remediates": remediates,
                "files": paths,
                "missed": missed,
                "acceptance": acc,
                "tests": tests,
            }
        )
    return cards


def _remediation_group_key(v: Violation) -> tuple[str, frozenset[str]]:
    if v.path:
        files_key: frozenset[str] = frozenset({v.path})
    else:
        files_key = frozenset({f"__nopath__:{v.class_name}:{v.detail[:120]}"})
    remediates = v.remediates_task_id or ""
    return (remediates, files_key)


def current_audit_round(audit_body: str) -> int:
    stamped = extract_field(audit_body, "Audit-round")
    return int(stamped) if stamped.isdigit() else 0


def violation_fingerprint(v: Violation | dict[str, Any], default_tier: str = "tier1") -> tuple[str, str, str, str]:
    if isinstance(v, Violation):
        return (v.tier, v.class_name, v.path, v.detail)
    tier = v.get("tier") or default_tier
    return (tier, v.get("class", ""), v.get("path", ""), v.get("detail", ""))


def parse_missed_bullets(body: str) -> list[str]:
    bullets: list[str] = []
    in_missed = False
    for line in body.splitlines():
        if re.match(r"(?i)^Missed:\s*$", line.strip()):
            in_missed = True
            continue
        if in_missed:
            if re.match(r"^[A-Za-z_-]+:", line) and not line.strip().startswith("-"):
                break
            if line.strip().startswith("- "):
                bullets.append(line.strip()[2:].strip())
    return bullets


def fingerprint_from_missed_line(line: str) -> tuple[str, str, str, str] | None:
    m = re.match(r"\[(tier1|tier2)\]\s*([\w_]+):\s*(.+)", line.strip(), re.I)
    if not m:
        return None
    tier, class_name, detail = m.group(1).lower(), m.group(2), m.group(3).strip()
    if class_name == "doc_coverage_gap" and "Required doc surface" in detail:
        path_m = re.search(r"for `([^`]+)`", detail)
        path = path_m.group(1) if path_m else ""
    elif " at `" in detail:
        path_m = re.search(r" at `([^`]+)`", detail)
        path = path_m.group(1) if path_m else ""
    else:
        path_m = re.search(r"`([^`]+)`", detail)
        path = path_m.group(1) if path_m else ""
    return (tier, class_name, path, detail)


def fingerprints_from_remediation_body(body: str) -> set[tuple[str, str, str, str]]:
    fps: set[tuple[str, str, str, str]] = set()
    for line in parse_missed_bullets(body):
        fp = fingerprint_from_missed_line(line)
        if fp:
            fps.add(fp)
    return fps


def load_violations_from_reports(report_dir: Path, plan_id: str) -> list[Violation]:
    violations: list[Violation] = []
    for tier in ("tier1", "tier2"):
        path = report_dir / f"{plan_id}_audit_{tier}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for v in data.get("violations", []):
            if v.get("status") == "escalated":
                continue
            violations.append(
                Violation(
                    tier=v.get("tier", tier),
                    class_name=v.get("class", ""),
                    path=v.get("path", ""),
                    detail=v.get("detail", ""),
                    source_card_key=v.get("source_card_key", ""),
                    remediates_task_id=v.get("remediates_task_id", ""),
                )
            )
    return violations


def mark_violations_escalated_in_reports(
    report_dir: Path,
    plan_id: str,
    fingerprints: set[tuple[str, str, str, str]],
) -> None:
    if not fingerprints:
        return
    for tier in ("tier1", "tier2"):
        path = report_dir / f"{plan_id}_audit_{tier}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for v in data.get("violations", []):
            fp = violation_fingerprint(v, default_tier=tier)
            if fp in fingerprints:
                v["status"] = "escalated"
                changed = True
            else:
                for target in fingerprints:
                    if target[0] == fp[0] and target[1] == fp[1] and target[3] == fp[3]:
                        v["status"] = "escalated"
                        changed = True
                        break
        if changed:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def filter_violations_by_fingerprints(
    violations: list[Violation],
    exclude: set[tuple[str, str, str, str]],
) -> list[Violation]:
    if not exclude:
        return violations
    kept: list[Violation] = []
    for v in violations:
        fp = violation_fingerprint(v)
        if fp in exclude:
            continue
        if any(fp[0] == e[0] and fp[1] == e[1] and fp[3] == e[3] for e in exclude):
            continue
        kept.append(v)
    return kept


def format_violation_summary(violations: list[Violation], limit: int = 12) -> str:
    lines = [f"[{v.tier}] {v.class_name}: {v.path or '(no path)'} — {v.detail[:120]}" for v in violations[:limit]]
    if len(violations) > limit:
        lines.append(f"... and {len(violations) - limit} more")
    return "\n".join(lines)


def run_escalation_tracker(
    scripts_dir: Path,
    task_id: str,
    block_reason: str,
    repo_root: Path,
) -> None:
    esc = scripts_dir / "kanban_escalation_tracker.sh"
    if not esc.is_file():
        return
    subprocess.run(
        [
            "bash",
            str(esc),
            "--task-id",
            task_id,
            "--block-reason",
            block_reason,
            "--repo-root",
            str(repo_root),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=60,
    )


def process_gave_up_remediation_children(
    *,
    audit_id: str,
    plan_id: str,
    report_dir: Path,
    repo_root: Path,
    scripts_dir: Path,
    gave_up_children: list[dict[str, str]],
    dry_run: bool = False,
) -> set[tuple[str, str, str, str]]:
    """Escalate gave_up remediation children; mark tier JSON; return fingerprints to exclude from spawn."""
    all_fps: set[tuple[str, str, str, str]] = set()
    for child in gave_up_children:
        body = child.get("body", "")
        task_id = child.get("task_id", "")
        fps = fingerprints_from_remediation_body(body)
        all_fps |= fps
        reason = (
            f"[escalation:orchestrator:attempt:1] final audit gave_up remediation "
            f"{task_id} plan_id={plan_id}"
        )
        if not dry_run:
            run_escalation_tracker(scripts_dir, audit_id, reason, repo_root)
        mark_violations_escalated_in_reports(report_dir, plan_id, fps)
    return all_fps


def build_remediation_body(plan_id: str, card: dict[str, Any]) -> str:
    files_line = ", ".join(card["files"]) if card["files"] else "docs/"
    acc_lines = "\n".join(f"- {a}" for a in card["acceptance"])
    missed_lines = "\n".join(card["missed"])
    return (
        f"plan_id: {plan_id}\n"
        f"Type: remediation\n"
        f"Remediation-phase: final\n"
        f"Remediates: {card['remediates'] or 'audit'}\n"
        f"Missed:\n{missed_lines}\n"
        f"Files: {files_line}\n"
        f"Acceptance:\n{acc_lines}\n"
        f"Tests: {card['tests']}\n"
    )


def verify_doc_tests(method: str, workspace: str, files: list[str]) -> tuple[bool, str | None]:
    """Verify doc: Tests: commands (evaluation chain step 3)."""
    method = method.strip()
    if method.startswith("doc:"):
        method = method[4:].strip()
    if method == "link-check":
        for f in files:
            path = Path(workspace) / f
            if not path.is_file():
                return False, f"doc file missing: {f}"
            text = path.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"\]\(([^)]+)\)", text):
                target = m.group(1).split("#")[0].strip()
                if not target or target.startswith("http"):
                    continue
                resolved = (path.parent / target).resolve()
                if not resolved.exists():
                    return False, f"broken link {target} in {f}"
        return True, None
    if method.startswith("symbol-grep "):
        symbol = method.split(" ", 1)[1].strip()
        for f in files:
            text = (Path(workspace) / f).read_text(encoding="utf-8", errors="replace")
            if symbol not in text:
                return False, f"symbol `{symbol}` not found in {f}"
        return True, None
    if method == "yaml-validate":
        import yaml

        for f in files:
            path = Path(workspace) / f
            if not path.is_file():
                return False, f"missing {f}"
            try:
                yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as exc:
                return False, f"yaml invalid in {f}: {exc}"
        return True, None
    return False, f"unknown doc test method: {method}"
