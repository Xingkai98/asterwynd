# tests/agent/browser/test_policy.py
"""BrowserPolicy 单元测试 —— URL 白名单验证、产物路径。"""

import pytest
from pathlib import Path

from agent.config import BrowserConfig
from agent.browser.policy import BrowserPolicy, BrowserPolicyError
from agent.workspace_policy import WorkspacePolicy


class TestBrowserPolicyUrlAllowlist:
    """URL 白名单验证测试。"""

    def test_empty_allowlist_denies_all(self):
        """空白名单拒绝所有 URL。"""
        config = BrowserConfig(url_allowlist=())
        policy = BrowserPolicy(config)

        assert policy.is_url_allowed("https://example.com") is False
        assert policy.is_url_allowed("https://docs.python.org") is False
        assert policy.is_url_allowed("http://example.com") is False

    def test_exact_domain_match(self):
        """精确域名匹配：白名单中的域名精确匹配 URL hostname。"""
        config = BrowserConfig(url_allowlist=("docs.python.org",))
        policy = BrowserPolicy(config)

        assert policy.is_url_allowed("https://docs.python.org/3/library/") is True
        assert policy.is_url_allowed("https://docs.python.org") is True
        # 子域名不匹配精确条目
        assert policy.is_url_allowed("https://sub.docs.python.org") is False
        # 不同域名不匹配
        assert policy.is_url_allowed("https://python.org") is False

    def test_wildcard_subdomain_match(self):
        """通配符子域名匹配："*.example.com" 匹配 "sub.example.com"。"""
        config = BrowserConfig(url_allowlist=("*.example.com",))
        policy = BrowserPolicy(config)

        assert policy.is_url_allowed("https://sub.example.com/page") is True
        assert policy.is_url_allowed("https://deep.sub.example.com/page") is True
        # 通配符不匹配裸域名
        assert policy.is_url_allowed("https://example.com") is False
        # 不匹配其他域名
        assert policy.is_url_allowed("https://other.org") is False

    def test_http_denied_by_default(self):
        """http:// 默认被拒绝，除非白名单中显式包含 http 条目。"""
        # https 条目不放行 http
        config = BrowserConfig(url_allowlist=("example.com",))
        policy = BrowserPolicy(config)

        assert policy.is_url_allowed("https://example.com/page") is True
        assert policy.is_url_allowed("http://example.com/page") is False

    def test_http_explicitly_allowed(self):
        """白名单中显式包含 http:// 条目时放行 http。"""
        config = BrowserConfig(url_allowlist=("http://local.dev",))
        policy = BrowserPolicy(config)

        assert policy.is_url_allowed("http://local.dev/page") is True
        # http 条目不适用于 https
        assert policy.is_url_allowed("https://local.dev/page") is False

    def test_unknown_scheme_denied(self):
        """非 http/https scheme 一律拒绝。"""
        config = BrowserConfig(url_allowlist=("example.com",))
        policy = BrowserPolicy(config)

        assert policy.is_url_allowed("ftp://example.com/file") is False
        assert policy.is_url_allowed("file:///etc/passwd") is False
        assert policy.is_url_allowed("javascript:alert(1)") is False

    def test_multiple_allowlist_entries(self):
        """多个白名单条目都可匹配。"""
        config = BrowserConfig(url_allowlist=(
            "docs.python.org",
            "*.github.com",
            "http://local.dev",
        ))
        policy = BrowserPolicy(config)

        assert policy.is_url_allowed("https://docs.python.org/3/") is True
        assert policy.is_url_allowed("https://api.github.com/repos") is True
        assert policy.is_url_allowed("http://local.dev/page") is True
        assert policy.is_url_allowed("https://github.com/user") is False
        assert policy.is_url_allowed("https://example.com") is False


class TestBrowserPolicyError:
    """BrowserPolicyError 异常测试。"""

    def test_assert_url_allowed_raises_on_deny(self):
        """assert_url_allowed 在 URL 被拒绝时抛出 BrowserPolicyError。"""
        config = BrowserConfig(url_allowlist=())
        policy = BrowserPolicy(config)

        with pytest.raises(BrowserPolicyError, match="URL not in allowlist"):
            policy.assert_url_allowed("https://example.com")

    def test_assert_url_allowed_passes_on_allow(self):
        """assert_url_allowed 在 URL 被允许时不抛异常。"""
        config = BrowserConfig(url_allowlist=("example.com",))
        policy = BrowserPolicy(config)

        # 不应抛出异常
        policy.assert_url_allowed("https://example.com/page")


class TestBrowserPolicyArtifactPath:
    """产物路径测试。"""

    def test_get_artifact_dir(self):
        """产物目录为 <workspace_root>/.asterwynd/browser-artifacts/。"""
        config = BrowserConfig()
        ws_policy = WorkspacePolicy(workspace_root="/tmp/test-ws")
        policy = BrowserPolicy(config, workspace_policy=ws_policy)

        artifact_dir = policy.get_artifact_dir()
        assert artifact_dir == Path("/tmp/test-ws/.asterwynd/browser-artifacts")

    def test_assert_artifact_write_allowed_delegates(self):
        """assert_artifact_write_allowed 委托给 WorkspacePolicy。"""
        config = BrowserConfig()
        ws_policy = WorkspacePolicy(workspace_root="/tmp/test-ws")
        policy = BrowserPolicy(config, workspace_policy=ws_policy)

        # 工作区内的路径应该允许
        allowed_path = Path("/tmp/test-ws/.asterwynd/browser-artifacts/screenshot.png")
        # 不抛异常即为通过
        policy.assert_artifact_write_allowed(allowed_path)

    def test_assert_artifact_write_allowed_denies_outside(self):
        """工作区外的路径应该被拒绝。"""
        config = BrowserConfig()
        ws_policy = WorkspacePolicy(workspace_root="/tmp/test-ws")
        policy = BrowserPolicy(config, workspace_policy=ws_policy)

        with pytest.raises(PermissionError, match="outside workspace"):
            policy.assert_artifact_write_allowed(Path("/etc/passwd"))


class TestBrowserPolicyConfigPassthrough:
    """超时配置透传测试。"""

    def test_timeout_configs_passed_through(self):
        """BrowserPolicy 透传 BrowserConfig 中的超时配置。"""
        config = BrowserConfig(
            navigation_timeout=45,
            read_timeout=20,
            screenshot_timeout=15,
        )
        policy = BrowserPolicy(config)

        assert policy.config.navigation_timeout == 45
        assert policy.config.read_timeout == 20
        assert policy.config.screenshot_timeout == 15
