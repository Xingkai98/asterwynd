from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent.planning import PlanItem, PLAN_STATUSES
from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import AGENT_STATE_PERMISSION

TODO_VALID_STATUSES = ("pending", "in_progress", "completed")

CreateCallback = Callable[[str], PlanItem]
UpdateCallback = Callable[[str, str, str | None], PlanItem]
ListCallback = Callable[[str | None], list[PlanItem]]


@tool_parameters(
    name="TodoWrite",
    description=(
        "Create and manage a structured task list for your current coding session. "
        "Use this to track progress, organize complex tasks, and demonstrate "
        "thoroughness. Only use it if it's relevant to the current work."
    ),
    parameters={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["create", "update", "list"],
                "description": "The operation to perform on the todo list.",
            },
            "content": {
                "type": "string",
                "description": "Task description. Required for 'create'.",
            },
            "id": {
                "type": "string",
                "description": "The todo item id. Required for 'update'.",
            },
            "status": {
                "type": "string",
                "enum": list(TODO_VALID_STATUSES),
                "description": "New status for the item. Required for 'update'.",
            },
            "note": {
                "type": "string",
                "description": "Optional note to attach to the item.",
            },
        },
        "required": ["operation"],
        "additionalProperties": False,
    },
)
class TodoWriteTool(Tool):
    name = "TodoWrite"
    read_only = False
    dangerous = False
    permission = AGENT_STATE_PERMISSION

    def __init__(
        self,
        create_cb: CreateCallback,
        update_cb: UpdateCallback,
        list_cb: ListCallback,
    ):
        self._create_cb = create_cb
        self._update_cb = update_cb
        self._list_cb = list_cb

    async def execute(self, **kwargs) -> str:
        operation = kwargs.get("operation")

        if operation == "create":
            return self._handle_create(kwargs)
        elif operation == "update":
            return self._handle_update(kwargs)
        elif operation == "list":
            return self._handle_list(kwargs)
        else:
            return f"[Error: unknown operation {operation!r}]"

    def _handle_create(self, kwargs: dict[str, Any]) -> str:
        content = kwargs.get("content")
        if not isinstance(content, str) or not content.strip():
            return "[Error: content must be a non-empty string]"

        item = self._create_cb(content.strip())
        return (
            f"[Todo item created: {item.id}] "
            f"status={item.status} content={item.content}"
        )

    def _handle_update(self, kwargs: dict[str, Any]) -> str:
        item_id = kwargs.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            return "[Error: id must be a non-empty string]"

        status = kwargs.get("status")
        if not isinstance(status, str) or status not in TODO_VALID_STATUSES:
            return (
                f"[Error: invalid status {status!r}; "
                f"must be one of {list(TODO_VALID_STATUSES)}]"
            )

        note = kwargs.get("note")
        if note is not None and not isinstance(note, str):
            return "[Error: note must be a string or null]"

        try:
            item = self._update_cb(item_id.strip(), status, note.strip() if isinstance(note, str) else None)
        except ValueError as e:
            return f"[Error: {e}]"

        return (
            f"[Todo item updated: {item.id}] "
            f"status={item.status} content={item.content}"
        )

    def _handle_list(self, kwargs: dict[str, Any]) -> str:
        status_filter = kwargs.get("status")
        if status_filter is not None:
            if not isinstance(status_filter, str) or status_filter not in TODO_VALID_STATUSES:
                return (
                    f"[Error: invalid status filter {status_filter!r}; "
                    f"must be one of {list(TODO_VALID_STATUSES)}]"
                )

        items = self._list_cb(status_filter if isinstance(status_filter, str) else None)

        if not items:
            return "[Todo list is empty]"

        lines = [f"{len(items)} todo item(s):"]
        for item in items:
            status_marker = {
                "pending": " ",
                "in_progress": "▶",
                "completed": "✓",
            }.get(item.status, " ")
            line = f"  [{status_marker}] {item.content}"
            if item.note:
                line = f"{line} ({item.note})"
            lines.append(line)

        return "\n".join(lines)
