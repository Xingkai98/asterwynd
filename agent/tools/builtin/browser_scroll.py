# agent/tools/builtin/browser_scroll.py
"""BrowserScroll 工具 —— 滚动当前页面。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.tools.base import tool_parameters
from agent.tools.builtin.browser import BrowserTool
from agent.browser.service import BrowserNotAvailableError

if TYPE_CHECKING:
    from agent.browser.service import BrowserService


@tool_parameters(
    name="BrowserScroll",
    description="向上或向下滚动当前浏览器页面。",
    parameters={
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "description": "滚动方向：up（向上）或 down（向下）",
                "enum": ["up", "down"],
            },
            "amount": {
                "type": "integer",
                "description": "滚动的像素数，默认 300",
                "default": 300,
            },
            "tab_id": {
                "type": "string",
                "description": "标签页 ID（可选，不指定则使用当前活跃标签页）",
            },
        },
        "required": ["direction"],
    },
)
class BrowserScrollTool(BrowserTool):
    """滚动当前页面的浏览器工具。"""

    async def execute(
        self,
        direction: str,
        amount: int = 300,
        tab_id: str | None = None,
        **kwargs,
    ) -> str:
        if self.browser_service is None:
            return "[Browser not available: browser service not configured]"

        if not self.browser_service.is_running:
            return "[Browser not available: browser not started]"

        if direction not in ("up", "down"):
            return f"[Browser Error: invalid direction '{direction}', must be 'up' or 'down']"

        try:
            session = await self.browser_service.get_session(tab_id)
        except ValueError as e:
            return f"[Browser Error: {e}]"

        try:
            await session.scroll(direction, max(1, int(amount)))
        except Exception as e:
            return f"[Browser Error: {e}]"

        direction_text = "down" if direction == "down" else "up"
        return f"Scrolled {direction_text} by {amount}px"
