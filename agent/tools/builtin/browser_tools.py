# agent/tools/builtin/browser_tools.py
"""浏览器工具聚合模块 —— 统一导出所有浏览器工具类。"""

from agent.tools.builtin.browser_navigate import BrowserNavigateTool
from agent.tools.builtin.browser_get_content import BrowserGetContentTool
from agent.tools.builtin.browser_screenshot import BrowserScreenshotTool
from agent.tools.builtin.browser_scroll import BrowserScrollTool
from agent.tools.builtin.browser_tabs import (
    BrowserListTabsTool,
    BrowserSwitchTabTool,
    BrowserCloseTabTool,
)

BROWSER_TOOL_CLASSES = (
    BrowserNavigateTool,
    BrowserGetContentTool,
    BrowserScreenshotTool,
    BrowserScrollTool,
    BrowserListTabsTool,
    BrowserSwitchTabTool,
    BrowserCloseTabTool,
)

__all__ = [
    "BrowserNavigateTool",
    "BrowserGetContentTool",
    "BrowserScreenshotTool",
    "BrowserScrollTool",
    "BrowserListTabsTool",
    "BrowserSwitchTabTool",
    "BrowserCloseTabTool",
    "BROWSER_TOOL_CLASSES",
]
