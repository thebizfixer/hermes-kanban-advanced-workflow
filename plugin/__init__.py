"""kanban-advanced plugin — register all tools, hooks, CLI commands, and bundled skills."""

import logging
from pathlib import Path
from . import schemas, tools, hooks, cli

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire all plugin components into the Hermes Agent runtime."""

    # ── 1. Register all 11 bundled skills ──────────────────────────
    skills_dir = Path(__file__).parent / "skills"
    registered = 0
    failed = []

    for child in sorted(skills_dir.iterdir()):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.exists():
            try:
                ctx.register_skill(child.name, skill_md)
                registered += 1
                logger.info("plugin: registered skill %s", child.name)
            except Exception as exc:
                failed.append(child.name)
                logger.error("plugin: failed to register skill %s: %s", child.name, exc)

    if failed:
        logger.warning("plugin: %d/%d skills registered; failed: %s",
                       registered, registered + len(failed), ", ".join(failed))

    # ── 2. Register LLM-callable tools ─────────────────────────────
    _register_tool = ctx.register_tool
    _register_tool(name="kanban_create",   toolset="kanban",
                   description="Create a new kanban card from a plan section",
                   schema=schemas.KANBAN_CREATE, handler=tools.kanban_create)
    _register_tool(name="kanban_list",     toolset="kanban",
                   description="List all cards on the kanban board with status",
                   schema=schemas.KANBAN_LIST, handler=tools.kanban_list)
    _register_tool(name="kanban_show",     toolset="kanban",
                   description="Show details for a specific kanban card by ID",
                   schema=schemas.KANBAN_SHOW, handler=tools.kanban_show)
    _register_tool(name="kanban_complete", toolset="kanban",
                   description="Mark a kanban card as completed with summary",
                   schema=schemas.KANBAN_COMPLETE, handler=tools.kanban_complete)
    _register_tool(name="kanban_block",    toolset="kanban",
                   description="Block a kanban card with a reason for the block",
                   schema=schemas.KANBAN_BLOCK, handler=tools.kanban_block)
    _register_tool(name="kanban_unblock",  toolset="kanban",
                   description="Unblock a previously blocked kanban card",
                   schema=schemas.KANBAN_UNBLOCK, handler=tools.kanban_unblock)
    _register_tool(name="kanban_link",     toolset="kanban",
                   description="Link two kanban cards as parent-child dependency",
                   schema=schemas.KANBAN_LINK, handler=tools.kanban_link)

    # ── 3. Register lifecycle hooks ────────────────────────────────
    # on_session_start: fires once when a brand-new session is created
    ctx.register_hook("on_session_start", hooks.on_session_start)
    # post_tool_call: fires after every tool call; callback(tool_name, params, result)
    ctx.register_hook("post_tool_call", hooks.post_tool_call)

    # ── 4. Register CLI subcommands ────────────────────────────────
    ctx.register_cli_command(
        name="kanban-advanced",
        help="Advanced kanban workflow management — decompose plans, validate boards, preflight gates",
        setup_fn=cli.setup_argparse,
        handler_fn=cli.handle_kanban,
    )

    logger.info("plugin: kanban-advanced v1.0.0 registered (%d skills, 7 tools, 2 hooks, 1 CLI)",
                registered)
