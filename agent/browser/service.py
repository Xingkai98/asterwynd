# agent/browser/service.py
"""浏览器服务 —— 管理 Playwright 浏览器实例生命周期和标签页集合。"""

from __future__ import annotations

import asyncio
import logging
import random
import string
from typing import TYPE_CHECKING

from agent.browser.policy import BrowserPolicy
from agent.browser.session import BrowserSession

if TYPE_CHECKING:
    from agent.config import BrowserConfig

logger = logging.getLogger("asterwynd.browser.service")


class BrowserNotAvailableError(Exception):
    """Playwright 不可用时的异常（未安装或导入失败）。"""

    pass


class BrowserService:
    """管理 Playwright 浏览器实例的生命周期和标签页集合。

    特性：
    - 惰性启动：首次工具调用时才启动浏览器
    - 自动标签页管理：分配短 ID、维护标签页字典
    - 生命周期关闭：停止时关闭所有会话和浏览器实例
    """

    def __init__(self, policy: BrowserPolicy, config: BrowserConfig):
        self._policy = policy
        self._config = config
        self._playwright = None
        self._browser = None
        self._context = None
        self._tabs: dict[str, BrowserSession] = {}
        self._active_tab_id: str | None = None
        self._started = False

    @property
    def is_running(self) -> bool:
        """浏览器实例是否已启动。"""
        return self._started and self._browser is not None

    # ── 生命周期 ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动 Playwright 浏览器（惰性调用，重复调用无副作用）。"""
        if self._started:
            return

        # 惰性导入 playwright
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise BrowserNotAvailableError(
                "playwright not installed. "
                "Install with: pip install playwright && playwright install chromium"
            )

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch()
        self._context = await self._browser.new_context(
            # 设置合理的 viewport 以便截图
            viewport={"width": 1280, "height": 720},
        )

        # 创建默认标签页
        page = await self._context.new_page()
        session = BrowserSession(page, self._policy)
        tab_id = self._generate_tab_id()
        self._tabs[tab_id] = session
        self._active_tab_id = tab_id
        self._started = True

        logger.info("Browser started (chromium), default tab: %s", tab_id)

    async def stop(self) -> None:
        """关闭浏览器，清理所有资源。"""
        if not self._started:
            return

        # 关闭所有标签页会话
        for session in list(self._tabs.values()):
            await session.close()
        self._tabs.clear()
        self._active_tab_id = None

        # 关闭 browser context
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None

        # 关闭 browser
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        # 停止 playwright
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        self._started = False
        logger.info("Browser stopped")

    # ── 标签页管理 ────────────────────────────────────────────────────

    async def get_session(self, tab_id: str | None = None) -> BrowserSession:
        """获取指定标签页的会话，未指定时返回当前活跃标签页。"""
        if not self.is_running:
            await self.start()

        if tab_id is None:
            tab_id = self._active_tab_id

        if tab_id is None or tab_id not in self._tabs:
            raise ValueError(f"Tab not found: {tab_id}")

        # 将目标标签页的 page 带到前台
        try:
            await self._tabs[tab_id].page.bring_to_front()
        except Exception:
            pass

        return self._tabs[tab_id]

    async def new_tab(self, url: str | None = None) -> BrowserSession:
        """创建新标签页，可选地导航到指定 URL。"""
        if not self.is_running:
            await self.start()

        page = await self._context.new_page()
        session = BrowserSession(page, self._policy)
        tab_id = self._generate_tab_id()
        self._tabs[tab_id] = session
        self._active_tab_id = tab_id

        if url is not None:
            await session.navigate(url)

        logger.info("New tab: %s -> %s", tab_id, url or "(blank)")
        return session

    async def close_tab(self, tab_id: str) -> None:
        """关闭指定标签页。"""
        if tab_id not in self._tabs:
            raise ValueError(f"Tab not found: {tab_id}")

        # 不允许关闭最后一个标签页
        if len(self._tabs) <= 1:
            raise ValueError("Cannot close the last tab")

        session = self._tabs.pop(tab_id)
        await session.close()

        # 如果关闭的是当前活跃标签页，切换到另一个
        if self._active_tab_id == tab_id:
            self._active_tab_id = next(iter(self._tabs), None)

        logger.info("Closed tab: %s", tab_id)

    async def list_tabs(self) -> list[dict]:
        """列出所有标签页的元数据。"""
        if not self.is_running:
            return []

        tabs = []
        for tid, session in self._tabs.items():
            try:
                url = session.page.url
                title = await session.page.title()
            except Exception:
                url = ""
                title = ""
            tabs.append({
                "tab_id": tid,
                "url": url,
                "title": title,
                "active": tid == self._active_tab_id,
            })
        return tabs

    async def switch_tab(self, tab_id: str) -> BrowserSession:
        """切换到指定标签页。"""
        if tab_id not in self._tabs:
            raise ValueError(f"Tab not found: {tab_id}")

        self._active_tab_id = tab_id
        session = self._tabs[tab_id]

        try:
            await session.page.bring_to_front()
        except Exception:
            pass

        return session

    # ── 内部方法 ──────────────────────────────────────────────────────

    @staticmethod
    def _generate_tab_id() -> str:
        """生成短标签页 ID（4 位小写字母+数字，类似 OpenHands）。"""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
