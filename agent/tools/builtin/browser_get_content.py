# agent/tools/builtin/browser_get_content.py
"""BrowserGetContent 工具 —— 获取当前页面文本内容。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.tools.base import tool_parameters
from agent.tools.builtin.browser import BrowserTool
from agent.browser.service import BrowserNotAvailableError

if TYPE_CHECKING:
    from agent.browser.service import BrowserService


@tool_parameters(
    name="BrowserGetContent",
    description="获取当前浏览器页面的文本内容。",
    parameters={
        "type": "object",
        "properties": {
            "tab_id": {
                "type": "string",
                "description": "标签页 ID（可选，不指定则使用当前活跃标签页）",
            },
        },
    },
)
class BrowserGetContentTool(BrowserTool):
    """获取当前页面文本内容的浏览器工具。"""

    async def execute(self, tab_id: str | None = None, **kwargs) -> str:
        if self.browser_service is None:
            return "[Browser not available: browser service not configured]"

        if not self.browser_service.is_running:
            return "[Browser not available: browser not started]"

        try:
            session = await self.browser_service.get_session(tab_id)
        except ValueError as e:
            return f"[Browser Error: {e}]"

        content = await session.get_content()
        return content
