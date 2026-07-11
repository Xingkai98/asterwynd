# tests/agent/tools/test_browser_tools.py
"""浏览器工具单元测试 —— schema 验证、权限元数据、错误路径。"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agent.tool_permissions import (
    BROWSER_READ_PERMISSION,
    ToolCapability,
    ToolOrigin,
    ToolRiskLevel,
)
from agent.tools.builtin.browser import BrowserTool
from agent.tools.builtin.browser_tools import BROWSER_TOOL_CLASSES
from agent.tools.builtin.browser_navigate import BrowserNavigateTool
from agent.tools.builtin.browser_get_content import BrowserGetContentTool
from agent.tools.builtin.browser_screenshot import BrowserScreenshotTool
from agent.tools.builtin.browser_scroll import BrowserScrollTool
from agent.tools.builtin.browser_tabs import (
    BrowserListTabsTool,
    BrowserSwitchTabTool,
    BrowserCloseTabTool,
)


# ── Schema 验证 ──────────────────────────────────────────────────────

EXPECTED_TOOL_NAMES = {
    "BrowserNavigate",
    "BrowserGetContent",
    "BrowserScreenshot",
    "BrowserScroll",
    "BrowserListTabs",
    "BrowserSwitchTab",
    "BrowserCloseTab",
}


def test_seven_browser_tools_registered():
    """BROWSER_TOOL_CLASSES 包含 7 个工具。"""
    names = {cls.name for cls in BROWSER_TOOL_CLASSES}
    assert names == EXPECTED_TOOL_NAMES
    assert len(BROWSER_TOOL_CLASSES) == 7


@pytest.mark.parametrize("tool_cls", BROWSER_TOOL_CLASSES)
def test_tool_has_valid_schema(tool_cls):
    """每个浏览器工具都有合法的 JSON Schema。"""
    tool = tool_cls()
    schema = tool.get_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == tool_cls.name
    assert schema["function"]["description"]
    assert "parameters" in schema["function"]
    assert schema["function"]["parameters"]["type"] == "object"


@pytest.mark.parametrize("tool_cls", BROWSER_TOOL_CLASSES)
def test_tool_has_permission(tool_cls):
    """每个浏览器工具都设置了 BROWSER_READ_PERMISSION 权限。"""
    tool = tool_cls()
    permission = tool.get_permission()

    assert permission.risk_level == ToolRiskLevel.MEDIUM
    assert permission.origin == ToolOrigin.BROWSER
    assert ToolCapability.BROWSER_CONTROL in permission.capabilities


@pytest.mark.parametrize("tool_cls", BROWSER_TOOL_CLASSES)
def test_tool_not_parallelizable(tool_cls):
    """浏览器工具不可并行执行。"""
    assert tool_cls.parallelizable is False


# ── 权限元数据 ───────────────────────────────────────────────────────

def test_browser_read_permission_definition():
    """BROWSER_READ_PERMISSION 定义正确。"""
    assert BROWSER_READ_PERMISSION.capabilities == frozenset({ToolCapability.BROWSER_CONTROL})
    assert BROWSER_READ_PERMISSION.risk_level == ToolRiskLevel.MEDIUM
    assert BROWSER_READ_PERMISSION.origin == ToolOrigin.BROWSER


# ── 错误路径：无 browser_service ──────────────────────────────────────


@pytest.mark.asyncio
async def test_navigate_without_service():
    """BrowserNavigateTool 在没有 browser_service 时返回错误字符串。"""
    tool = BrowserNavigateTool(browser_service=None)
    result = await tool.execute(url="https://example.com")
    assert result.startswith("[Browser not available")


@pytest.mark.asyncio
async def test_get_content_without_service():
    """BrowserGetContentTool 在没有 browser_service 时返回错误字符串。"""
    tool = BrowserGetContentTool(browser_service=None)
    result = await tool.execute()
    assert result.startswith("[Browser not available")


@pytest.mark.asyncio
async def test_screenshot_without_service():
    """BrowserScreenshotTool 在没有 browser_service 时返回错误字符串。"""
    tool = BrowserScreenshotTool(browser_service=None)
    result = await tool.execute()
    assert result.startswith("[Browser not available")


@pytest.mark.asyncio
async def test_scroll_without_service():
    """BrowserScrollTool 在没有 browser_service 时返回错误字符串。"""
    tool = BrowserScrollTool(browser_service=None)
    result = await tool.execute(direction="down")
    assert result.startswith("[Browser not available")


@pytest.mark.asyncio
async def test_list_tabs_without_service():
    """BrowserListTabsTool 在没有 browser_service 时返回错误字符串。"""
    tool = BrowserListTabsTool(browser_service=None)
    result = await tool.execute()
    assert result.startswith("[Browser not available")


@pytest.mark.asyncio
async def test_switch_tab_without_service():
    """BrowserSwitchTabTool 在没有 browser_service 时返回错误字符串。"""
    tool = BrowserSwitchTabTool(browser_service=None)
    result = await tool.execute(tab_id="abcd")
    assert result.startswith("[Browser not available")


@pytest.mark.asyncio
async def test_close_tab_without_service():
    """BrowserCloseTabTool 在没有 browser_service 时返回错误字符串。"""
    tool = BrowserCloseTabTool(browser_service=None)
    result = await tool.execute(tab_id="abcd")
    assert result.startswith("[Browser not available")


# ── 错误路径：browser 未启动 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_content_when_not_running():
    """BrowserGetContentTool 在 browser 未启动时返回错误。"""
    mock_service = MagicMock()
    mock_service.is_running = False
    tool = BrowserGetContentTool(browser_service=mock_service)
    result = await tool.execute()
    assert "not started" in result


@pytest.mark.asyncio
async def test_screenshot_when_not_running():
    """BrowserScreenshotTool 在 browser 未启动时返回错误。"""
    mock_service = MagicMock()
    mock_service.is_running = False
    tool = BrowserScreenshotTool(browser_service=mock_service)
    result = await tool.execute()
    assert "not started" in result


@pytest.mark.asyncio
async def test_scroll_when_not_running():
    """BrowserScrollTool 在 browser 未启动时返回错误。"""
    mock_service = MagicMock()
    mock_service.is_running = False
    tool = BrowserScrollTool(browser_service=mock_service)
    result = await tool.execute(direction="down")
    assert "not started" in result


# ── Mock 成功路径 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_navigate_success():
    """BrowserNavigateTool 成功导航并返回标题。"""
    mock_service = MagicMock()
    mock_service.is_running = True
    mock_session = MagicMock()
    mock_session.navigate = AsyncMock(return_value={
        "url": "https://example.com",
        "title": "Example Page",
    })
    mock_service.get_session = AsyncMock(return_value=mock_session)

    tool = BrowserNavigateTool(browser_service=mock_service)
    result = await tool.execute(url="https://example.com")

    assert "Navigated to: https://example.com" in result
    assert "Example Page" in result


@pytest.mark.asyncio
async def test_get_content_success():
    """BrowserGetContentTool 成功返回页面文本。"""
    mock_service = MagicMock()
    mock_service.is_running = True
    mock_session = MagicMock()
    mock_session.get_content = AsyncMock(return_value="Hello World")
    mock_service.get_session = AsyncMock(return_value=mock_session)

    tool = BrowserGetContentTool(browser_service=mock_service)
    result = await tool.execute()

    assert result == "Hello World"


@pytest.mark.asyncio
async def test_scroll_success():
    """BrowserScrollTool 成功滚动。"""
    mock_service = MagicMock()
    mock_service.is_running = True
    mock_session = MagicMock()
    mock_session.scroll = AsyncMock()
    mock_service.get_session = AsyncMock(return_value=mock_session)

    tool = BrowserScrollTool(browser_service=mock_service)
    result = await tool.execute(direction="up", amount=500)

    assert "Scrolled up by 500px" in result


@pytest.mark.asyncio
async def test_scroll_invalid_direction():
    """BrowserScrollTool 拒绝无效方向。"""
    mock_service = MagicMock()
    mock_service.is_running = True
    tool = BrowserScrollTool(browser_service=mock_service)
    result = await tool.execute(direction="left")
    assert "invalid direction" in result


# ── 标签页管理 Mock 测试 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tabs_success():
    """BrowserListTabsTool 成功列出标签页。"""
    mock_service = MagicMock()
    mock_service.is_running = True
    mock_service.list_tabs = AsyncMock(return_value=[
        {"tab_id": "abcd", "url": "https://example.com", "title": "Example", "active": True},
        {"tab_id": "efgh", "url": "https://other.com", "title": "Other", "active": False},
    ])

    tool = BrowserListTabsTool(browser_service=mock_service)
    result = await tool.execute()

    assert "abcd" in result
    assert "efgh" in result


@pytest.mark.asyncio
async def test_switch_tab_success():
    """BrowserSwitchTabTool 成功切换标签页。"""
    mock_service = MagicMock()
    mock_service.is_running = True
    mock_session = MagicMock()
    mock_session.page.url = "https://example.com"
    mock_session.page.title = AsyncMock(return_value="Example Page")
    mock_service.switch_tab = AsyncMock(return_value=mock_session)

    tool = BrowserSwitchTabTool(browser_service=mock_service)
    result = await tool.execute(tab_id="abcd")

    assert "Switched to tab [abcd]" in result
    assert "Example Page" in result


@pytest.mark.asyncio
async def test_close_tab_success():
    """BrowserCloseTabTool 成功关闭标签页。"""
    mock_service = MagicMock()
    mock_service.is_running = True
    mock_service.close_tab = AsyncMock()

    tool = BrowserCloseTabTool(browser_service=mock_service)
    result = await tool.execute(tab_id="abcd")

    assert "Closed tab [abcd]" in result
