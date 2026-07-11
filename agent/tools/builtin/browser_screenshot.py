# agent/tools/builtin/browser_screenshot.py
"""BrowserScreenshot 工具 —— 截取当前页面截图。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from agent.tools.base import tool_parameters
from agent.tools.builtin.browser import BrowserTool
from agent.browser.service import BrowserNotAvailableError

if TYPE_CHECKING:
    from agent.message import ContentBlock, ImageBlock


def _make_image_block(png_bytes: bytes, file_path: str) -> "ImageBlock":
    """构造包含 base64 PNG 图片的 ImageBlock。"""
    import base64
    from agent.message import ImageBlock, ImageUrl

    b64 = base64.b64encode(png_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"
    return ImageBlock(image_url=ImageUrl(url=data_url), file_path=file_path)


@tool_parameters(
    name="BrowserScreenshot",
    description="截取当前浏览器页面的截图。截图保存到浏览器产物目录。",
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
class BrowserScreenshotTool(BrowserTool):
    """截取当前页面截图的浏览器工具。

    截图保存到 <workspace_root>/.asterwynd/browser-artifacts/ 目录，
    同时返回包含 base64 图片数据的 ContentBlock 列表供模型查看。
    """

    async def execute(self, tab_id: str | None = None, **kwargs) -> str | list["ContentBlock"]:
        if self.browser_service is None:
            return "[Browser not available: browser service not configured]"

        if not self.browser_service.is_running:
            return "[Browser not available: browser not started]"

        try:
            session = await self.browser_service.get_session(tab_id)
        except ValueError as e:
            return f"[Browser Error: {e}]"

        try:
            png_bytes = await session.screenshot()
        except Exception as e:
            error_name = type(e).__name__
            if "Timeout" in error_name:
                return (
                    f"[Browser Error: screenshot timeout after "
                    f"{session._policy.config.screenshot_timeout}s]"
                )
            return f"[Browser Error: {e}]"

        # 保存到产物目录
        artifact_dir = session._policy.get_artifact_dir()
        artifact_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time() * 1000)
        tid = tab_id or "current"
        filename = f"screenshot-{timestamp}-{tid}.png"
        filepath = artifact_dir / filename

        try:
            session._policy.assert_artifact_write_allowed(filepath)
            filepath.write_bytes(png_bytes)
        except PermissionError as e:
            return f"[Browser Error: artifact write denied: {e}]"

        # 返回图片 content block 和文件路径
        image_block = _make_image_block(png_bytes, str(filepath))
        return [
            image_block,
        ]
