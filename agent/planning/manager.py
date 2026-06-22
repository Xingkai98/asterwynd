from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PlanStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
PLAN_STATUSES: tuple[PlanStatus, ...] = (
    "pending",
    "in_progress",
    "completed",
    "failed",
    "skipped",
)


@dataclass
class PlanItem:
    id: str
    content: str
    status: PlanStatus = "pending"
    note: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status,
            "note": self.note,
        }


class PlanningManager:
    def __init__(self) -> None:
        self._items: list[PlanItem] = []
        self._next_id = 1

    def set_plan(self, contents: list[str]) -> dict:
        items: list[PlanItem] = []
        for content in contents:
            normalized = content.strip()
            if not normalized:
                raise ValueError("plan item content must not be empty")
            items.append(PlanItem(id=self._new_item_id(), content=normalized))

        self._items = items
        return self.snapshot()

    def update_item(
        self,
        item_id: str,
        status: PlanStatus,
        note: str | None = None,
    ) -> dict:
        if status not in PLAN_STATUSES:
            raise ValueError(f"invalid plan status: {status}")

        item = self._find_item(item_id)
        if status == "in_progress":
            in_progress = [
                existing for existing in self._items
                if existing.status == "in_progress" and existing.id != item_id
            ]
            if in_progress:
                raise ValueError("only one in_progress plan item is allowed")

        item.status = status
        item.note = note
        return self.snapshot()

    def snapshot(self) -> dict:
        items = [item.to_dict() for item in self._items]
        return {
            "items": items,
            "summary": self.summary(items),
        }

    def summary(self, items: list[dict] | None = None) -> dict:
        serialized_items = items if items is not None else [
            item.to_dict() for item in self._items
        ]
        counts = {status: 0 for status in PLAN_STATUSES}
        current_item = None

        for item in serialized_items:
            counts[item["status"]] += 1
            if item["status"] == "in_progress":
                current_item = item

        return {
            "total": len(serialized_items),
            **counts,
            "current_item": current_item,
        }

    def render_context(self) -> str:
        if not self._items:
            return ""

        lines = ["Current structured planning state:"]
        for item in self._items:
            line = f"- [{item.status}] {item.content}"
            if item.note:
                line = f"{line} ({item.note})"
            lines.append(line)
        return "\n".join(lines)

    def _new_item_id(self) -> str:
        item_id = f"item-{self._next_id}"
        self._next_id += 1
        return item_id

    def _find_item(self, item_id: str) -> PlanItem:
        for item in self._items:
            if item.id == item_id:
                return item
        raise ValueError(f"unknown plan item: {item_id}")
