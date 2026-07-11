# agent/tools/builtin/browser_navigate.py
"""BrowserNavigate 工具 —— 导航到指定 URL。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.tools.base import tool_parameters
from agent.tools.builtin.browser import BrowserTool
from agent.browser.policy import BrowserPolicyError
from agent.browser.service import BrowserNotAvailableError

if TYPE_CHECKING:
    from agent.browser.service import BrowserService


@tool_parameters(
    name="BrowserNavigate",
    description="导航到指定 URL。仅允许访问浏览器白名单中的域名。",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要导航到的 URL（必须以 https:// 开头）",
            },
        },
        "required": ["url"],
    },
)
class BrowserNavigateTool(BrowserTool):
    """导航到指定 URL 的浏览器工具。"""

    async def execute(self, url: str, **kwargs) -> str:
        if self.browser_service is None:
            return "[Browser not available: browser service not configured]"

        if not self.browser_service.is_running:
            try:
                await self.browser_service.start()
            except BrowserNotAvailableError as e:
                return f"[Browser not available: {e}]"

        try:
            # 尝试获取当前活跃会话并导航
            session = await self.browser_service.get_session()
        except ValueError:
            # 没有活跃会话时创建新标签页
            session = await self.browser_service.new_tab()

        try:
            result = await session.navigate(url)
        except BrowserPolicyError as e:
            return f"[URL denied: {e}]"

        if "error" in result:
            return result["error"]

        title = result.get("title", "")
        final_url = result.get("url", url)
        return f"Navigated to: {final_url}\nTitle: {title}"
