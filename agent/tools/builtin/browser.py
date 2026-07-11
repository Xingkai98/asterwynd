# agent/tools/builtin/browser.py
"""浏览器工具基类 —— 所有浏览器工具的共享基类。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.tools.base import Tool
from agent.tool_permissions import BROWSER_READ_PERMISSION

if TYPE_CHECKING:
    from agent.browser.service import BrowserService


class BrowserTool(Tool):
    """浏览器工具基类。

    所有浏览器工具共享以下特性：
    - 使用 BROWSER_READ_PERMISSION 权限
    - 不可并行执行（浏览器操作需串行化）
    - 注入 BrowserService 实例
    """

    permission = BROWSER_READ_PERMISSION
    parallelizable = False

    def __init__(self, browser_service: BrowserService | None = None):
        self.browser_service = browser_service
