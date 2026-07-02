"""Tool schemas — what the LLM sees to decide when to call kanban tools."""

KANBAN_CREATE = {
    "name": "kanban_create",
    "description": (
        "Create a new kanban card from a plan section. "
        "Use this during plan decomposition to create one card per workstream. "
        "The card will be dispatched to a worker profile for execution."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Task title — short, descriptive, matches the plan section heading",
            },
            "body": {
                "type": "string",
                "description": "Full card body including agent -p block, Files:, Mode:, Tests:, and Commit: lines",
            },
            "assignee": {
                "type": "string",
                "description": "Profile name to assign the task to (e.g. 'worker')",
            },
            "workspace": {
                "type": "string",
                "description": "Workspace type: 'worktree', 'scratch', or 'dir:<path>'",
            },
            "branch": {
                "type": "string",
                "description": "Branch name for worktree tasks (e.g. 'wt/card-42-fix-auth')",
            },
            "parents": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Parent task IDs this card depends on (repeatable)",
            },
            "priority": {
                "type": "integer",
                "description": "Priority tiebreaker (lower = higher priority)",
            },
            "skill": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Skills to force-load into the worker (appended to kanban-advanced:kanban-worker). Example: ['kanban-advanced:kanban-planning']",
            },
            "goal": {
                "type": "boolean",
                "description": "Run worker in goal loop with judge evaluation. Best for open-ended cards.",
                "default": False,
            },
            "goal_max_turns": {
                "type": "integer",
                "description": "Turn budget for goal workers (default 20). Ignored unless goal=True.",
            },
        },
        "required": ["title"],
    },
}

KANBAN_LIST = {
    "name": "kanban_list",
    "description": (
        "List all cards on the kanban board with status, assignee, and priority. "
        "Use this to monitor board state, check which cards are blocked/ready/running, "
        "and decide which cards to dispatch or triage next."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["todo", "ready", "running", "blocked", "done", "archived", "review", "scheduled", "triage"],
                "description": "Filter by status. Omit to show all non-archived cards.",
            },
            "assignee": {
                "type": "string",
                "description": "Filter by assigned profile name",
            },
            "json_output": {
                "type": "boolean",
                "description": "Return JSON for programmatic consumption",
                "default": True,
            },
        },
        "required": [],
    },
}

KANBAN_SHOW = {
    "name": "kanban_show",
    "description": (
        "Show full details for a specific kanban card by ID — body, comments, run history, "
        "dependency graph, and events. Use this to diagnose failures, inspect card state, "
        "or review what a completed card produced."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The kanban card ID to inspect",
            },
            "json_output": {
                "type": "boolean",
                "description": "Return JSON for programmatic consumption",
                "default": True,
            },
        },
        "required": ["task_id"],
    },
}

KANBAN_COMPLETE = {
    "name": "kanban_complete",
    "description": (
        "Mark one or more kanban cards as completed with a summary. "
        "Use this when a card's work is done — the summary becomes the handoff "
        "for downstream dependent cards."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "One or more task IDs to mark as completed",
            },
            "summary": {
                "type": "string",
                "description": "Structured handoff summary for downstream tasks. Include what changed, what was tested, and any caveats.",
            },
            "result": {
                "type": "string",
                "description": "Short result summary (falls back to summary if omitted)",
            },
        },
        "required": ["task_ids", "summary"],
    },
}

KANBAN_BLOCK = {
    "name": "kanban_block",
    "description": (
        "Block a kanban card with a reason. Use this when a card has failed, "
        "needs human intervention, or is blocked by an external dependency. "
        "Blocked cards will not be dispatched until unblocked."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID to block",
            },
            "reason": {
                "type": "string",
                "description": "Reason for blocking — appended as a comment on the card",
            },
            "kind": {
                "type": "string",
                "enum": ["dependency", "needs_input", "capability", "transient"],
                "description": (
                    "Block kind: 'dependency' parks in todo (auto-resumed when parent "
                    "completes); others block immediately. Omit for legacy behavior."
                ),
            },
        },
        "required": ["task_id", "reason"],
    },
}

KANBAN_UNBLOCK = {
    "name": "kanban_unblock",
    "description": (
        "Unblock one or more previously blocked kanban cards. "
        "Use this when the blocking issue has been resolved and the card is ready to run."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "One or more task IDs to unblock",
            },
            "reason": {
                "type": "string",
                "description": "Optional note explaining why the card is being unblocked",
            },
        },
        "required": ["task_ids"],
    },
}

KANBAN_LINK = {
    "name": "kanban_link",
    "description": (
        "Link two kanban cards as a parent-child dependency. "
        "The child card will not be dispatched until the parent is completed. "
        "Use this to wire the dependency graph during plan decomposition."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "parent_id": {
                "type": "string",
                "description": "The parent task ID (must be completed before child can run)",
            },
            "child_id": {
                "type": "string",
                "description": "The child task ID (waits on parent completion)",
            },
        },
        "required": ["parent_id", "child_id"],
    },
}
