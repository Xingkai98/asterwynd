# agent/browser/policy.py
"""浏览器安全策略 —— URL 白名单验证、超时配置、产物路径管理。"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from agent.config import BrowserConfig
from agent.workspace_policy import WorkspacePolicy


class BrowserPolicyError(Exception):
    """浏览器策略拒绝时的异常。"""

    pass


class BrowserPolicy:
    """浏览器安全策略。

    职责：
    - URL 白名单验证（精确域名匹配 + 通配符子域名）
    - 超时配置透传
    - 浏览器产物目录管理
    """

    def __init__(
        self,
        config: BrowserConfig,
        workspace_policy: WorkspacePolicy | None = None,
    ):
        self.config = config
        self.workspace_policy = workspace_policy or WorkspacePolicy()

    # ── URL 白名单 ─────────────────────────────────────────────────────

    def is_url_allowed(self, url: str) -> bool:
        """检查 URL 是否在白名单中。

        规则：
        - 空白名单时拒绝所有 URL。
        - 默认只允许 https://，http:// 除非白名单中显式包含 http 条目否则拒绝。
        - 支持精确域名匹配和通配符子域名匹配。
        """
        if not self.config.url_allowlist:
            return False

        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        scheme = parsed.scheme

        if scheme not in ("http", "https"):
            return False

        # http:// 只能通过白名单中显式的 http 条目放行
        if scheme == "http":
            return self._match_specific_scheme(hostname, "http")

        # https:// 检查白名单中的非 http 条目
        return self._match_https_host(hostname)

    def assert_url_allowed(self, url: str) -> None:
        """检查 URL 是否允许，不允许时抛出 BrowserPolicyError。"""
        if not self.is_url_allowed(url):
            raise BrowserPolicyError(f"URL not in allowlist: {url}")

    def _match_specific_scheme(self, hostname: str, scheme: str) -> bool:
        """检查 hostname 是否匹配白名单中指定 scheme 的条目。"""
        for pattern in self.config.url_allowlist:
            if "://" in pattern:
                parsed_pattern = urlparse(pattern)
                if parsed_pattern.scheme == scheme:
                    pattern_host = parsed_pattern.hostname or ""
                    if self._host_matches(hostname, pattern_host):
                        return True
            # 无 scheme 的 bare domain 不算 http 条目
        return False

    def _match_https_host(self, hostname: str) -> bool:
        """检查 hostname 是否匹配白名单中允许 https 的条目。"""
        for pattern in self.config.url_allowlist:
            if "://" in pattern:
                parsed_pattern = urlparse(pattern)
                # http 条目不适用于 https URL
                if parsed_pattern.scheme == "http":
                    continue
                pattern_host = parsed_pattern.hostname or ""
            else:
                # bare domain 默认视为允许 https
                pattern_host = pattern

            if self._host_matches(hostname, pattern_host):
                return True

        return False

    @staticmethod
    def _host_matches(hostname: str, pattern: str) -> bool:
        """检查 hostname 是否匹配白名单模式。

        支持两种模式：
        - 精确匹配："docs.python.org" 精确匹配 "docs.python.org"
        - 通配符子域名："*.example.com" 匹配 "sub.example.com" 但不匹配 "example.com"
        """
        if pattern.startswith("*."):
            suffix = pattern[2:]  # "example.com"
            # "sub.example.com".endswith(".example.com") → True
            # "example.com".endswith(".example.com") → False（缺少前导点）
            return hostname.endswith("." + suffix)
        return hostname == pattern

    # ── 产物路径 ──────────────────────────────────────────────────────

    def get_artifact_dir(self) -> Path:
        """返回浏览器产物目录路径：<workspace_root>/.asterwynd/browser-artifacts/"""
        return self.workspace_policy.workspace_root / ".asterwynd" / "browser-artifacts"

    def assert_artifact_write_allowed(self, path: Path) -> None:
        """检查产物路径是否允许写入，委托给 WorkspacePolicy。"""
        self.workspace_policy.assert_write_allowed(path)
