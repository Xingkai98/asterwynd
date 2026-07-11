# tests/agent/browser/test_service.py
"""BrowserService 单元测试 —— 生命周期、标签页管理、错误处理。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent.config import BrowserConfig
from agent.browser.policy import BrowserPolicy
from agent.browser.service import BrowserService, BrowserNotAvailableError
from agent.workspace_policy import WorkspacePolicy


@pytest.fixture
def browser_config():
    return BrowserConfig(
        enabled=True,
        url_allowlist=("example.com",),
    )


@pytest.fixture
def browser_policy(browser_config):
    return BrowserPolicy(browser_config)


@pytest.fixture
def browser_service(browser_policy, browser_config):
    return BrowserService(browser_policy, browser_config)


class TestBrowserServiceLifecycle:
    """生命周期测试。"""

    def test_initial_state_not_running(self, browser_service):
        """初始状态 is_running 为 False。"""
        assert browser_service.is_running is False

    @pytest.mark.asyncio
    async def test_start_requires_playwright(self, browser_service):
        """未安装 playwright 时 start() 抛出 BrowserNotAvailableError。"""
        # 使用 patch 在 import 源点模拟 ImportError
        import builtins
        original_import = builtins.__import__

        def _block_playwright(name, *args, **kwargs):
            if name == "playwright" or name.startswith("playwright."):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_block_playwright):
            with pytest.raises(BrowserNotAvailableError, match="playwright not installed"):
                await browser_service.start()
        assert browser_service.is_running is False

    @pytest.mark.asyncio
    async def test_start_creates_default_tab(self, browser_service):
        """start() 创建默认标签页并设置活跃标签页。"""
        # 使用 patch 在 playwright.async_api 源模块处模拟
        mock_page = AsyncMock()
        mock_page.url = "about:blank"
        mock_page.title = AsyncMock(return_value="")
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        # async_playwright() 返回的对象有 .start() 方法
        mock_apw_instance = MagicMock()
        mock_apw_instance.start = AsyncMock(return_value=mock_pw)

        with patch("playwright.async_api.async_playwright", return_value=mock_apw_instance):
            await browser_service.start()

        assert browser_service.is_running is True
        assert len(browser_service._tabs) == 1

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self, browser_service):
        """stop() 清理所有资源。"""
        mock_page = AsyncMock()
        mock_page.close = AsyncMock()
        mock_context = AsyncMock()
        mock_context.close = AsyncMock()
        mock_browser = AsyncMock()
        mock_browser.close = AsyncMock()
        mock_playwright = AsyncMock()
        mock_playwright.stop = AsyncMock()

        browser_service._started = True
        browser_service._playwright = mock_playwright
        browser_service._browser = mock_browser
        browser_service._context = mock_context

        from agent.browser.session import BrowserSession
        session = BrowserSession(mock_page, browser_policy)
        browser_service._tabs["abcd"] = session
        browser_service._active_tab_id = "abcd"

        await browser_service.stop()

        assert browser_service.is_running is False
        assert len(browser_service._tabs) == 0
        assert browser_service._active_tab_id is None
        mock_page.close.assert_called_once()
        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()


class TestBrowserServiceTabs:
    """标签页管理测试。"""

    @pytest.mark.asyncio
    async def test_new_tab_lazy_starts(self, browser_service):
        """new_tab() 在浏览器未启动时自动启动。"""
        mock_page = AsyncMock()
        mock_page.url = "about:blank"
        mock_page.title = AsyncMock(return_value="")
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        # async_playwright() 返回的对象有 .start() 方法
        mock_apw_instance = MagicMock()
        mock_apw_instance.start = AsyncMock(return_value=mock_pw)

        with patch("playwright.async_api.async_playwright", return_value=mock_apw_instance):
            session = await browser_service.new_tab()

        assert browser_service.is_running is True
        assert session is not None

    @pytest.mark.asyncio
    async def test_list_tabs_returns_metadata(self, browser_service):
        """list_tabs() 返回标签页元数据列表。"""
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="Example Page")
        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        # 初始化 service
        browser_service._playwright = mock_playwright
        browser_service._browser = mock_browser
        browser_service._context = mock_context
        browser_service._started = True

        from agent.browser.session import BrowserSession
        session = BrowserSession(mock_page, browser_policy)
        browser_service._tabs["abcd"] = session
        browser_service._active_tab_id = "abcd"

        tabs = await browser_service.list_tabs()

        assert len(tabs) == 1
        assert tabs[0]["tab_id"] == "abcd"
        assert tabs[0]["url"] == "https://example.com"
        assert tabs[0]["active"] is True

    @pytest.mark.asyncio
    async def test_list_tabs_not_running_returns_empty(self, browser_service):
        """浏览器未启动时 list_tabs() 返回空列表。"""
        tabs = await browser_service.list_tabs()
        assert tabs == []

    @pytest.mark.asyncio
    async def test_close_tab_prevents_last_tab(self, browser_service):
        """close_tab() 不允许关闭最后一个标签页。"""
        mock_page = AsyncMock()
        browser_service._started = True

        from agent.browser.session import BrowserSession
        session = BrowserSession(mock_page, browser_policy)
        browser_service._tabs["abcd"] = session
        browser_service._active_tab_id = "abcd"

        with pytest.raises(ValueError, match="Cannot close the last tab"):
            await browser_service.close_tab("abcd")

    @pytest.mark.asyncio
    async def test_close_tab_success(self, browser_service):
        """close_tab() 成功关闭非最后一个标签页。"""
        mock_page1 = AsyncMock()
        mock_page1.close = AsyncMock()
        mock_page2 = AsyncMock()
        mock_page2.close = AsyncMock()

        browser_service._started = True

        from agent.browser.session import BrowserSession
        session1 = BrowserSession(mock_page1, browser_policy)
        session2 = BrowserSession(mock_page2, browser_policy)
        browser_service._tabs["tab1"] = session1
        browser_service._tabs["tab2"] = session2
        browser_service._active_tab_id = "tab1"

        await browser_service.close_tab("tab1")

        assert "tab1" not in browser_service._tabs
        assert "tab2" in browser_service._tabs
        assert browser_service._active_tab_id == "tab2"

    @pytest.mark.asyncio
    async def test_switch_tab(self, browser_service):
        """switch_tab() 切换到指定标签页。"""
        mock_page1 = AsyncMock()
        mock_page1.bring_to_front = AsyncMock()
        mock_page1.url = "https://example.com/page1"
        mock_page1.title = AsyncMock(return_value="Page 1")

        mock_page2 = AsyncMock()
        mock_page2.url = "https://example.com/page2"
        mock_page2.title = AsyncMock(return_value="Page 2")

        browser_service._started = True

        from agent.browser.session import BrowserSession
        session1 = BrowserSession(mock_page1, browser_policy)
        session2 = BrowserSession(mock_page2, browser_policy)
        browser_service._tabs["tab1"] = session1
        browser_service._tabs["tab2"] = session2
        browser_service._active_tab_id = "tab1"

        session = await browser_service.switch_tab("tab2")

        assert browser_service._active_tab_id == "tab2"
        assert session is session2

    @pytest.mark.asyncio
    async def test_switch_tab_not_found(self, browser_service):
        """switch_tab() 对不存在的标签页抛出 ValueError。"""
        browser_service._started = True

        with pytest.raises(ValueError, match="Tab not found"):
            await browser_service.switch_tab("nonexistent")

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, browser_service):
        """get_session() 对不存在的标签页抛出 ValueError。"""
        browser_service._started = True

        with pytest.raises(ValueError, match="Tab not found"):
            await browser_service.get_session("nonexistent")


class TestBrowserServiceTabIdGeneration:
    """标签页 ID 生成测试。"""

    def test_generate_tab_id_is_4_chars(self):
        """生成的标签页 ID 为 4 位字符。"""
        tab_id = BrowserService._generate_tab_id()
        assert len(tab_id) == 4
        assert tab_id.isalnum()
        assert tab_id.islower()
