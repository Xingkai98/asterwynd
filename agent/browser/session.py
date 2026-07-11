# agent/browser/session.py
"""浏览器会话 —— 封装单个 Playwright Page 的操作。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.browser.policy import BrowserPolicy


class BrowserSession:
    """封装单个 Playwright Page，提供受策略约束的页面操作。

    所有方法在超时时返回错误字符串/字典，不抛出异常。
    """

    def __init__(self, page, policy: BrowserPolicy):
        self._page = page
        self._policy = policy

    @property
    def page(self):
        """返回底层 Playwright Page 对象（供 service 层访问元数据）。"""
        return self._page

    async def navigate(self, url: str) -> dict:
        """导航到指定 URL，返回 {url, title}。

        超时时返回包含 error 字段的字典。
        """
        self._policy.assert_url_allowed(url)
        timeout_ms = self._policy.config.navigation_timeout * 1000

        try:
            await self._page.goto(url, timeout=timeout_ms)
            title = await self._page.title()
            return {"url": self._page.url, "title": title}
        except Exception as e:
            error_name = type(e).__name__
            if "Timeout" in error_name:
                return {
                    "url": url,
                    "title": "",
                    "error": f"[Browser Error: navigation timeout after {self._policy.config.navigation_timeout}s]",
                }
            return {
                "url": url,
                "title": "",
                "error": f"[Browser Error: {e}]",
            }

    async def get_content(self) -> str:
        """获取当前页面的文本内容。

        超时时返回错误字符串。
        """
        timeout_ms = self._policy.config.read_timeout * 1000

        try:
            content = await self._page.evaluate(
                "() => document.body ? document.body.innerText : ''",
            )
            # 设置较短超时在 evaluate 上
            return content or ""
        except Exception as e:
            error_name = type(e).__name__
            if "Timeout" in error_name:
                return f"[Browser Error: read timeout after {self._policy.config.read_timeout}s]"
            return f"[Browser Error: {e}]"

    async def screenshot(self) -> bytes:
        """截取当前页面的 PNG 截图。

        超时时抛出异常，由调用方（工具层）处理。
        """
        timeout_ms = self._policy.config.screenshot_timeout * 1000
        return await self._page.screenshot(type="png", timeout=timeout_ms)

    async def scroll(self, direction: str, amount: int = 300) -> None:
        """滚动页面。

        Args:
            direction: "up" 或 "down"
            amount: 滚动的像素数，默认 300
        """
        delta = amount if direction == "down" else -amount
        await self._page.evaluate(f"window.scrollBy(0, {delta})")

    async def close(self) -> None:
        """关闭当前页面。"""
        try:
            await self._page.close()
        except Exception:
            pass
