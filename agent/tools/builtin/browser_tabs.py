# agent/tools/builtin/browser_tabs.py
"""标签页管理浏览器工具 —— BrowserListTabs、BrowserSwitchTab、BrowserCloseTab。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.tools.base import tool_parameters
from agent.tools.builtin.browser import BrowserTool
from agent.browser.service import BrowserNotAvailableError

if TYPE_CHECKING:
    from agent.browser.service import BrowserService


@tool_parameters(
    name="BrowserListTabs",
    description="列出所有浏览器标签页。",
    parameters={
        "type": "object",
        "properties": {},
    },
)
class BrowserListTabsTool(BrowserTool):
    """列出所有浏览器标签页的工具。"""

    async def execute(self, **kwargs) -> str:
        if self.browser_service is None:
            return "[Browser not available: browser service not configured]"

        if not self.browser_service.is_running:
            return "No browser tabs (browser not started)"

        try:
            tabs = await self.browser_service.list_tabs()
        except Exception as e:
            return f"[Browser Error: {e}]"

        if not tabs:
            return "No browser tabs"

        lines = []
        for tab in tabs:
            marker = " *" if tab.get("active") else "  "
            tid = tab["tab_id"]
            title = tab.get("title", "")[:80]
            url = tab.get("url", "")
            line = f"{marker} [{tid}] {title}"
            if url:
                line += f"\n       {url}"
            lines.append(line)

        return "\n".join(lines)


@tool_parameters(
    name="BrowserSwitchTab",
    description="切换到指定的浏览器标签页。",
    parameters={
        "type": "object",
        "properties": {
            "tab_id": {
                "type": "string",
                "description": "要切换到的标签页 ID",
            },
        },
        "required": ["tab_id"],
    },
)
class BrowserSwitchTabTool(BrowserTool):
    """切换浏览器标签页的工具。"""

    async def execute(self, tab_id: str, **kwargs) -> str:
        if self.browser_service is None:
            return "[Browser not available: browser service not configured]"

        if not self.browser_service.is_running:
            return "[Browser not available: browser not started]"

        try:
            session = await self.browser_service.switch_tab(tab_id)
        except ValueError as e:
            return f"[Browser Error: {e}]"

        try:
            url = session.page.url
            title = await session.page.title()
        except Exception:
            url = ""
            title = ""

        return f"Switched to tab [{tab_id}]: {title}\n{url}"


@tool_parameters(
    name="BrowserCloseTab",
    description="关闭指定的浏览器标签页。不允许关闭最后一个标签页。",
    parameters={
        "type": "object",
        "properties": {
            "tab_id": {
                "type": "string",
                "description": "要关闭的标签页 ID",
            },
        },
        "required": ["tab_id"],
    },
)
class BrowserCloseTabTool(BrowserTool):
    """关闭浏览器标签页的工具。"""

    async def execute(self, tab_id: str, **kwargs) -> str:
        if self.browser_service is None:
            return "[Browser not available: browser service not configured]"

        if not self.browser_service.is_running:
            return "[Browser not available: browser not started]"

        try:
            await self.browser_service.close_tab(tab_id)
        except ValueError as e:
            return f"[Browser Error: {e}]"

        return f"Closed tab [{tab_id}]"
