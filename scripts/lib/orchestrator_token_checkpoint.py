"""Best-effort orchestrator token logging at plugin script milestones."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

_LIB = Path(__file__).resolve().parent
_SCRIPTS = _LIB.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def maybe_log_orchestrator_checkpoint(
    plan_id: str,
    checkpoint: str,
    *,
    turns: int = 0,
    note: str = "",
    log: Callable[[str], None] | None = None,
) -> bool:
    """Log orchestrator tokens when plan_id is set and token_tracker is importable."""
    plan_id = (plan_id or os.environ.get("HERMES_KANBAN_PLAN_ID", "")).strip()
    if not plan_id:
        return False
    try:
        from token_tracker import log_orchestrator_tokens  # noqa: WPS433
    except Exception:
        return False
    try:
        log_orchestrator_tokens(
            plan_id=plan_id,
            checkpoint=checkpoint,
            turns=turns,
            note=note,
        )
        if log:
            log(f"[token] orchestrator checkpoint={checkpoint} plan_id={plan_id}")
        return True
    except Exception as exc:
        if log:
            log(f"[token] orchestrator checkpoint skipped: {exc}")
        return False


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Log orchestrator token checkpoint")
    p.add_argument("--plan-id", required=True)
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--turns", type=int, default=0)
    p.add_argument("--note", default="")
    args = p.parse_args(argv)
    maybe_log_orchestrator_checkpoint(
        args.plan_id,
        args.checkpoint,
        turns=args.turns,
        note=args.note,
        log=print,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
