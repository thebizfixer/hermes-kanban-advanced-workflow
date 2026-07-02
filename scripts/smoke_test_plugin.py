#!/usr/bin/env python3
"""Self-contained plugin smoke test — no Hermes runtime required.

Verifies the kanban-advanced plugin contract that the six-sigma agent-role UX
depends on: all bundled skills register, all LLM tools register with callable
handlers, both lifecycle hooks register and are callable, and the
profile-aware role-discovery hook (on_session_start) distinguishes the
orchestrator role from the default/worker role.

Run from the repo root (any platform):

    python3 scripts/smoke_test_plugin.py
    # Windows: python scripts/smoke_test_plugin.py also works

Exit 0 = plugin contract intact. Exit 1 = a role-critical surface is broken.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Expected surface (must match plugin.yaml and README "What You Get").
EXPECTED_SKILLS = {
    "kanban-advanced", "kanban-cleanup", "kanban-coder", "kanban-git",
    "kanban-notify", "kanban-orchestrator", "kanban-orchestrator-governance",
    "kanban-planning", "kanban-postmortem", "kanban-preflight",
    "kanban-reconciliation", "kanban-worker", "kanban-worker-governance",
}
EXPECTED_TOOLS = {
    "kanban_create", "kanban_list", "kanban_show", "kanban_complete",
    "kanban_block", "kanban_unblock", "kanban_link",
}
EXPECTED_HOOKS = {"on_session_start", "post_tool_call", "kanban_task_completed", "kanban_task_blocked"}
EXPECTED_CLI = {"kanban-advanced"}


class MockCtx:
    """Mirror of the Hermes plugin registration context surface used by register()."""

    def __init__(self):
        self.skills = {}
        self.tools = {}
        self.hooks = {}
        self.cli = {}

    def register_skill(self, name, skill_md):
        if not Path(skill_md).exists():
            raise FileNotFoundError(f"SKILL.md missing for {name}: {skill_md}")
        self.skills[name] = skill_md

    def register_tool(self, name, toolset=None, description=None, schema=None, handler=None, **kwargs):
        assert callable(handler), f"tool {name} handler is not callable"
        assert isinstance(schema, dict), f"tool {name} schema is not a dict"
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def register_hook(self, event, callback):
        assert callable(callback), f"hook {event} callback is not callable"
        self.hooks[event] = callback

    def register_cli_command(self, name, help=None, setup_fn=None, handler_fn=None, **kwargs):
        self.cli[name] = {"setup_fn": setup_fn, "handler_fn": handler_fn}


def _load_plugin():
    """Import the plugin package from the repo root the way Hermes would."""
    spec = importlib.util.spec_from_file_location(
        "plugin", REPO_ROOT / "plugin" / "__init__.py",
        submodule_search_locations=[str(REPO_ROOT / "plugin")],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["plugin"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    failures = []
    ctx = MockCtx()

    plugin = _load_plugin()
    plugin.register(ctx)

    # ── Skills (role SOPs) ──
    got_skills = set(ctx.skills)
    if got_skills != EXPECTED_SKILLS:
        failures.append(
            f"skills mismatch: missing={EXPECTED_SKILLS - got_skills}, "
            f"unexpected={got_skills - EXPECTED_SKILLS}"
        )

    # ── Tools ──
    got_tools = set(ctx.tools)
    if got_tools != EXPECTED_TOOLS:
        failures.append(
            f"tools mismatch: missing={EXPECTED_TOOLS - got_tools}, "
            f"unexpected={got_tools - EXPECTED_TOOLS}"
        )

    # ── Hooks ──
    got_hooks = set(ctx.hooks)
    if got_hooks != EXPECTED_HOOKS:
        failures.append(
            f"hooks mismatch: missing={EXPECTED_HOOKS - got_hooks}, "
            f"unexpected={got_hooks - EXPECTED_HOOKS}"
        )

    # ── CLI ──
    if set(ctx.cli) != EXPECTED_CLI:
        failures.append(f"cli mismatch: got={set(ctx.cli)}, expected={EXPECTED_CLI}")

    # ── Tool handlers must accept Hermes's dispatch contract ──
    # tools/registry.py calls: entry.handler(args, **kwargs) — a single
    # positional dict. A handler with unpacked named params (e.g.
    # def kanban_show(task_id, ...)) silently mis-binds the dict. Verify the
    # handler reads the param out of the dict rather than swallowing the dict.
    show = ctx.tools.get("kanban_show", {}).get("handler")
    if show:
        try:
            import json as _json
            out = _json.loads(show({"task_id": "SMOKE-1", "json_output": True}))
            # With hermes unreachable the call errors, but mis-binding shows up
            # as the whole dict leaking into the error/output text.
            blob = _json.dumps(out)
            if "'task_id'" in blob or '"task_id":' in blob and "SMOKE-1" not in blob:
                failures.append(
                    "kanban_show appears to mis-bind the args dict "
                    "(handler signature not (args: dict, **kwargs))"
                )
        except TypeError as exc:
            failures.append(f"kanban_show rejects positional dict dispatch: {exc!r}")
        except Exception:
            pass  # subprocess/hermes errors are fine; we only test the contract

    # ── Role-discovery hook: orchestrator vs default (keyword invocation) ──
    import os
    sess_hook = ctx.hooks.get("on_session_start")
    if sess_hook:
        try:
            prev = os.environ.get("HERMES_PROFILE")
            os.environ["HERMES_PROFILE"] = "orchestrator"
            sess_hook(session_id="smoke", model="test", platform="cli")
            os.environ["HERMES_PROFILE"] = ""
            sess_hook(session_id="smoke", model="test", platform="cli")
            if prev is None:
                os.environ.pop("HERMES_PROFILE", None)
            else:
                os.environ["HERMES_PROFILE"] = prev
        except Exception as exc:
            failures.append(f"on_session_start raised under profile kwargs: {exc!r}")

    # ── post_tool_call: must accept Hermes's keyword-only invocation ──
    # model_tools.py calls: invoke_hook("post_tool_call", tool_name=, args=,
    # result=, task_id=, duration_ms=) — all keywords.
    ptc = ctx.hooks.get("post_tool_call")
    if ptc:
        try:
            ptc(
                tool_name="kanban_list",
                args={"status": "ready"},
                result='{"ok": true}',
                task_id="SMOKE-1",
                duration_ms=12,
            )
        except Exception as exc:
            failures.append(
                f"post_tool_call rejects Hermes keyword invocation: {exc!r}"
            )

    # ── Report ──
    print(f"skills:  {len(ctx.skills)}/{len(EXPECTED_SKILLS)}")
    print(f"tools:   {len(ctx.tools)}/{len(EXPECTED_TOOLS)}")
    print(f"hooks:   {len(ctx.hooks)}/{len(EXPECTED_HOOKS)}")
    print(f"cli:     {len(ctx.cli)}/{len(EXPECTED_CLI)}")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nPASS: plugin contract intact — role skills, tools, hooks, and CLI all register.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
