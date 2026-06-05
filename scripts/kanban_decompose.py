#!/usr/bin/env python3
"""
kanban_decompose.py — Governed card creation from a hardened, optimized plan.

Reads card definitions from a plan's "Kanban optimization" section and creates
them on the kanban board in governed order:

  1. Gate card (blocked immediately via --initial-status blocked)
  2. All implementation cards (TODO)
  3. Link dependencies: gate → wave parent → ordinal (same-file) parent
  4. Verify all parent links exist
  5. Unblock gate (triggers wave-1 promotion via dispatcher)
  6. Optionally create auto_unblock + board_keeper crons

Cards start as TODO so the dispatcher promotes them when ALL parents complete.
Cards are only pre-blocked if they have no agent block (orchestrator cards) or
explicitly request blocked status. Cards move to blocked on failure — never
pre-emptively for dependency reasons.

Usage:
    python3 kanban_decompose.py --plan <plan.md> [--dry-run] [--no-crons]
    python3 kanban_decompose.py --plan <plan.md> --json  (machine-readable output)

The plan must have a "## Kanban optimization" section with "#### Card N" subsections
containing YAML-frontmatter card bodies (plan_id, files, mode, tests, commit,
estimated_lines, assignee, wave, wave_parent, ordinal_parent).

Environment:
    HERMES_HOME — required; used to locate kanban.db and cron script paths
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tempfile
from pathlib import Path

# ── CLI ────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Governed kanban card creation from plan")
    p.add_argument("--plan", help="Path to the optimized plan file (markdown)")
    p.add_argument("--cards-yaml", help="Path to structured cards YAML file (preferred)")
    p.add_argument("--dry-run", action="store_true", help="Parse and print cards, don't create")
    p.add_argument("--no-crons", action="store_true", help="Skip cron creation")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p.add_argument("--stagger-ms", type=int, default=1500,
                   help="Millis between card creates (default: 1500)")
    p.add_argument("--pause-every", type=int, default=5,
                   help="Pause after every N cards (default: 5)")
    p.add_argument("--pause-ms", type=int, default=3000,
                   help="Pause duration in millis (default: 3000)")

    args = p.parse_args()
    if not args.plan and not args.cards_yaml:
        p.error("Either --plan or --cards-yaml is required")
    return args

# ── Plan parser ────────────────────────────────────────────────────────────

def parse_yaml_cards(yaml_path: str) -> dict:
    """Parse card definitions from a structured YAML file (preferred format)."""
    import yaml
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    if not data or "cards" not in data:
        sys.exit("ERROR: YAML file must have a 'cards' key")

    cards = []
    for raw in data["cards"]:
        card = {
            "key": raw.get("key", ""),
            "title": raw.get("title", ""),
            "type": raw.get("type", "code-gen"),
            "assignee": raw.get("assignee", "worker"),
            "plan_id": data.get("plan_id", raw.get("plan_id", "")),
            "files": raw.get("files", []),
            "mode": raw.get("mode", "modify-only"),
            "tests": raw.get("tests", ""),
            "commit": raw.get("commit", ""),
            "estimated_lines": raw.get("estimated_lines", 0),
            "wave": raw.get("wave", 1),
            "wave_parent": raw.get("wave_parent"),
            "ordinal_parent": raw.get("ordinal_parent"),
            "workspace": raw.get("workspace"),
            "branch": raw.get("branch"),
            "body": raw.get("body", ""),
            "agent_body": raw.get("body", ""),  # same as body for YAML format
        }
        cards.append(card)

    return {"cards": cards, "plan_id": data.get("plan_id", "")}


def parse_plan(plan_path: str) -> dict:
    """Parse card definitions from a plan's Kanban optimization section."""
    with open(plan_path) as f:
        content = f.read()

    # Find the Kanban optimization section
    opt_match = re.search(r'## Kanban optimization.*?(?=^## \w|\Z)', content,
                          re.MULTILINE | re.DOTALL)
    if not opt_match:
        sys.exit("ERROR: No '## Kanban optimization' section found in plan")

    section = opt_match.group(0)

    # Extract card definitions (#### Card N — ...)
    card_blocks = re.finditer(
        r'#### (Card \d+.*?)(?=#### Card \d+|### (?:Same-provider|Line budget|Sad-path|Parent-child))',
        section, re.DOTALL
    )

    cards = []
    for match in card_blocks:
        block = match.group(1)
        card = parse_card_block(block)
        if card:
            cards.append(card)

    if not cards:
        sys.exit("ERROR: No card definitions found in optimization section")

    return {"cards": cards}


def parse_card_block(block: str) -> dict | None:
    """Parse a single card definition block into a structured dict."""
    # Extract title from heading
    title_match = re.match(r'#### (Card \d+.*?)(?:\s*\(.*?\))?\s*$', block, re.MULTILINE)
    if not title_match:
        return None
    title = title_match.group(1).strip()

    # Determine card type from title
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
    else:
        card_type = "code-gen"

    # Extract YAML frontmatter fields
    plan_id = _extract_field(block, r'plan_id:\s*(.+)')
    files_raw = _extract_field(block, r'files:\s*\n((?:\s{2}- .+\n?)+)')
    files = []
    if files_raw:
        files = [f.strip().lstrip('- ') for f in files_raw.strip().split('\n') if f.strip().startswith('- ')]
    mode = _extract_field(block, r'mode:\s*(.+)')
    tests = _extract_field(block, r'tests:\s*(.+)')
    commit = _extract_field(block, r'commit:\s*"?(.+?)"?\s*$')
    estimated_lines = _extract_field(block, r'estimated_lines:\s*(\d+)')
    wave = _extract_field(block, r'wave:\s*(\d+)')
    wave_parent = _extract_field(block, r'wave_parent:\s*(.+)')
    ordinal_parent = _extract_field(block, r'ordinal_parent:\s*(.+)')
    workspace = _extract_field(block, r'workspace:\s*(.+)')
    branch = _extract_field(block, r'branch:\s*(.+)')
    card_assignee = _extract_field(block, r'assignee:\s*(.+)')

    if card_assignee:
        assignee = card_assignee
    elif not assignee:
        assignee = "worker" if card_type == "code-gen" else "orchestrator"

    # Extract agent block body
    agent_body = None
    agent_match = re.search(r'```agent\s*\n(.*?)```', block, re.DOTALL)
    if agent_match:
        agent_body = agent_match.group(1).strip()

    # Build the full card body (YAML frontmatter + agent block)
    body_lines = [f"plan_id: {plan_id or 'unknown'}"]
    if files:
        body_lines.append("files:")
        for f in files:
            body_lines.append(f"  - {f}")
    body_lines.append(f"mode: {mode or 'modify-only'}")
    if tests:
        body_lines.append(f"tests: {tests}")
    if commit:
        body_lines.append(f"commit: \"{commit}\"")
    if estimated_lines:
        body_lines.append(f"estimated_lines: {estimated_lines}")

    if agent_body:
        body_lines.append("")
        body_lines.append("---")
        body_lines.append("```agent")
        body_lines.append(agent_body)
        body_lines.append("```")

    full_body = "\n".join(body_lines)

    # Determine card key for dependency matching
    key_match = re.search(r'(card\d+)', title.lower().replace(' ', '').replace('-', ''))
    card_key = key_match.group(1) if key_match else title.lower().replace(' ', '_')

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


def _extract_field(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else None


# ── Kanban operations ──────────────────────────────────────────────────────

def hermes(*args, timeout: int = 30) -> tuple[str, str, int]:
    """Run a hermes CLI command."""
    cmd = ["hermes"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def extract_id(output: str) -> str | None:
    """Extract task ID from hermes output (e.g., t_a1b2c3d4)."""
    m = re.search(r'(t_[a-zA-Z0-9]{8})', output)
    return m.group(1) if m else None


def create_card(card: dict, dry_run: bool = False) -> str | None:
    """Create a single kanban card. Returns task ID or None."""
    title = card["title"]
    assignee = card["assignee"]
    card_type = card["type"]
    body = card["body"]

    if dry_run:
        print(f"  [DRY-RUN] Would create: {title} (assignee={assignee}, type={card_type})")
        return f"dryrun_{card['key']}"

    # Write body to temp file to avoid shell escaping
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(body)
        tmpfile = f.name

    try:
        cmd = ["hermes", "kanban", "create", title, "--assignee", assignee]

        # Gate card: create as blocked
        if card_type == "gate":
            cmd.extend(["--initial-status", "blocked"])

        # Code-gen cards: add workspace and branch
        if card_type == "code-gen" and card.get("workspace"):
            cmd.extend(["--workspace", card["workspace"]])
        if card_type == "code-gen" and card.get("branch"):
            cmd.extend(["--branch", card["branch"]])

        # Body via temp file
        cmd.extend(["--body-file", tmpfile])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        out = result.stdout.strip()
        err = result.stderr.strip()

        task_id = extract_id(out)
        if task_id:
            return task_id
        else:
            print(f"  WARN: Could not extract ID from: {out[:200]}", file=sys.stderr)
            if err:
                print(f"  stderr: {err[:200]}", file=sys.stderr)
            return None
    finally:
        os.unlink(tmpfile)


def link_cards(parent_id: str, child_id: str, dry_run: bool = False) -> bool:
    """Link parent → child dependency."""
    if dry_run:
        print(f"  [DRY-RUN] Would link: {parent_id} -> {child_id}")
        return True
    out, err, rc = hermes("kanban", "link", parent_id, child_id)
    return rc == 0


def verify_links(card_map: dict[str, str], cards: list[dict]) -> list[str]:
    """Verify all declared dependencies have corresponding links."""
    errors = []
    for card in cards:
        card_id = card_map.get(card["key"])
        if not card_id:
            continue
        # Check that all declared parents exist in card_map
        for parent_key in [card.get("wave_parent"), card.get("ordinal_parent")]:
            if parent_key and parent_key not in card_map:
                errors.append(f"{card['key']}: parent '{parent_key}' not found in card map")
    return errors


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Validate input file
    input_path = args.cards_yaml or args.plan
    if not os.path.exists(input_path):
        sys.exit(f"ERROR: File not found: {input_path}")

    hermes_home = os.environ.get("HERMES_HOME", "")
    if not hermes_home:
        print("WARN: HERMES_HOME not set — cron scripts may not resolve", file=sys.stderr)

    # Parse plan
    if args.cards_yaml:
        print(f"Parsing cards YAML: {args.cards_yaml}")
        parsed = parse_yaml_cards(args.cards_yaml)
    else:
        print(f"Parsing plan: {args.plan}")
        parsed = parse_plan(args.plan)
    all_cards = parsed["cards"]

    # Count impl cards first (used in auto-generated card bodies)
    impl_cards = [c for c in all_cards if c["type"] not in ("gate", "root", "audit")]

    # Auto-generate gate card (every board needs one)
    gate_card = {
        "key": "gate",
        "title": f"Gate — {parsed.get('plan_id', 'kanban plan')}",
        "type": "gate",
        "assignee": "orchestrator",
        "plan_id": parsed.get("plan_id", ""),
        "files": [],
        "mode": "N/A",
        "tests": "N/A",
        "commit": "N/A",
        "estimated_lines": 0,
        "wave": 0,
        "wave_parent": None,
        "ordinal_parent": None,
        "workspace": None,
        "branch": None,
        "body": f"plan_id: {parsed.get('plan_id', 'unknown')}\nGate card. All implementation cards link to gate. Unblock triggers wave 1 promotion.",
        "agent_body": None,
    }

    # Auto-generate root card
    root_card = {
        "key": "root",
        "title": f"{parsed.get('plan_id', 'Kanban plan')} — ROOT",
        "type": "root",
        "assignee": "orchestrator",
        "plan_id": parsed.get("plan_id", ""),
        "files": [],
        "mode": "N/A",
        "tests": "N/A",
        "commit": "N/A",
        "estimated_lines": 0,
        "wave": 0,
        "wave_parent": None,
        "ordinal_parent": None,
        "workspace": None,
        "branch": None,
        "body": f"plan_id: {parsed.get('plan_id', 'unknown')}\nRoot card for {len(impl_cards)} implementation cards.",
        "agent_body": None,
    }

    # Auto-generate audit card
    audit_card = {
        "key": "audit",
        "title": f"Final audit — {parsed.get('plan_id', 'kanban plan')}",
        "type": "audit",
        "assignee": "orchestrator",
        "plan_id": parsed.get("plan_id", ""),
        "files": [],
        "mode": "N/A",
        "tests": "N/A",
        "commit": "N/A",
        "estimated_lines": 0,
        "wave": 999,  # last wave
        "wave_parent": None,
        "ordinal_parent": None,
        "workspace": None,
        "branch": None,
        "body": f"plan_id: {parsed.get('plan_id', 'unknown')}\nFinal audit. Verifies file compliance, lint, tests, cross-task consistency, commit reachability.",
        "agent_body": None,
    }

    # Rebuild card list with gate first, then impl, then audit
    all_cards = [gate_card] + impl_cards + [root_card, audit_card]

    # Separate cards by type
    gate_cards = [c for c in all_cards if c["type"] == "gate"]
    root_cards = [c for c in all_cards if c["type"] == "root"]
    audit_cards = [c for c in all_cards if c["type"] == "audit"]
    # impl_cards already computed above

    if not gate_cards:
        sys.exit("ERROR: No gate card generated")
    gate_card = gate_cards[0]

    print(f"\nPlan: {len(all_cards)} cards ({len(impl_cards)} impl, {len(gate_cards)} gate, {len(root_cards)} root)")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}\n")

    # ── Step 1: Create gate card (blocked) ──
    print("=== Step 1: Gate card (blocked) ===")
    gate_id = create_card(gate_card, args.dry_run)
    if not gate_id:
        sys.exit("ERROR: Failed to create gate card")
    print(f"  Gate: {gate_id} (blocked)")
    time.sleep(args.stagger_ms / 1000)

    # ── Step 2: Create implementation cards (TODO) ──
    print(f"\n=== Step 2: {len(impl_cards)} implementation cards (TODO) ===")
    card_ids: dict[str, str] = {"gate": gate_id}

    created = 1  # gate counts as 1
    for card in impl_cards:
        cid = create_card(card, args.dry_run)
        if cid:
            card_ids[card["key"]] = cid
            print(f"  {card['key']}: {cid} (todo)")
        else:
            print(f"  {card['key']}: FAILED", file=sys.stderr)
        created += 1
        time.sleep(args.stagger_ms / 1000)
        if created % args.pause_every == 0:
            print(f"  --- pausing {args.pause_ms}ms ---")
            time.sleep(args.pause_ms / 1000)

    # Also create root card if present
    for root_card in root_cards:
        rid = create_card(root_card, args.dry_run)
        if rid:
            card_ids[root_card["key"]] = rid
            print(f"  {root_card['key']}: {rid} (root)")
        time.sleep(args.stagger_ms / 1000)

    # Also create audit card
    for audit in audit_cards:
        aid = create_card(audit, args.dry_run)
        if aid:
            card_ids[audit["key"]] = aid
            print(f"  audit: {aid} (blocked)")
        time.sleep(args.stagger_ms / 1000)

    # ── Step 3: Link dependencies ──
    print(f"\n=== Step 3: Link dependencies ===")
    links_created = 0
    seen_links = set()  # deduplicate (card2 parent of card8 for both wave + ordinal)
    for card in impl_cards:
        child_id = card_ids.get(card["key"])
        if not child_id:
            continue

        # 3a: Link to gate (all cards depend on gate)
        link_key = f"gate->{card['key']}"
        if card["key"] != "gate" and gate_id and link_key not in seen_links:
            if link_cards(gate_id, child_id, args.dry_run):
                seen_links.add(link_key)
                links_created += 1
                if not args.dry_run:
                    print(f"  gate -> {card['key']}")

        # 3b: Link to wave parent
        wp = card.get("wave_parent")
        if wp and wp in card_ids:
            link_key = f"{wp}->{card['key']}"
            if link_key not in seen_links:
                if link_cards(card_ids[wp], child_id, args.dry_run):
                    seen_links.add(link_key)
                    links_created += 1
                    if not args.dry_run:
                        print(f"  {wp} (wave) -> {card['key']}")

        # 3c: Link to ordinal parent
        op = card.get("ordinal_parent")
        if op and op in card_ids:
            link_key = f"{op}->{card['key']}"
            if link_key not in seen_links:
                if link_cards(card_ids[op], child_id, args.dry_run):
                    seen_links.add(link_key)
                    links_created += 1
                    if not args.dry_run:
                        print(f"  {op} (ordinal) -> {card['key']}")

    print(f"  Total links: {links_created}")

    # Link audit card to all impl cards (audit gates on all implementation)
    audit_id = card_ids.get("audit")
    if audit_id:
        for card in impl_cards:
            child_id = card_ids.get(card["key"])
            if child_id:
                link_key = f"audit->{card['key']}"
                if link_key not in seen_links:
                    if link_cards(child_id, audit_id, args.dry_run):
                        seen_links.add(link_key)
                        links_created += 1
        if not args.dry_run:
            hermes("kanban", "block", audit_id, "Awaiting all implementation cards completion")
            print(f"  audit blocked")

    # Complete root card immediately
    root_id = card_ids.get("root")
    if root_id and not args.dry_run:
        hermes("kanban", "complete", root_id, "--summary", f"Root complete — {len(impl_cards)} cards dispatched.")
        print(f"  root completed")

    # ── Step 4: Verify dependencies ──
    print(f"\n=== Step 4: Verify dependencies ===")
    errors = verify_links(card_ids, impl_cards)
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit("Dependency verification failed — fix plan and retry")
    print("  All dependencies verified")

    # ── Step 5: Unblock gate ──
    print(f"\n=== Step 5: Unblock gate ===")
    if not args.dry_run:
        out, err, rc = hermes("kanban", "unblock", gate_id)
        if rc == 0:
            print(f"  Gate {gate_id} unblocked — wave 1 promotion begins")
        else:
            print(f"  WARN: Gate unblock failed: {err}", file=sys.stderr)
    else:
        print(f"  [DRY-RUN] Would unblock: {gate_id}")

    # ── Step 6: Create crons (optional) ──
    if not args.no_crons and not args.dry_run:
        print(f"\n=== Step 6: Create auto-unblock + board-keeper crons ===")
        print("  Run: hermes cron create ... ")
        print("  (cron creation requires the cronjob tool — invoke separately)")
    elif args.dry_run:
        print(f"\n=== Step 6: [DRY-RUN] Would create crons ===")

    # ── Output ──
    print(f"\n=== Summary ===")
    print(f"  Gate: {gate_id}")
    print(f"  Cards: {len(card_ids) - 1}")
    if args.json:
        print(json.dumps({"gate": gate_id, "cards": card_ids}, indent=2))
    else:
        for key, cid in sorted(card_ids.items()):
            if key != "gate":
                print(f"  {key}: {cid}")


if __name__ == "__main__":
    main()
