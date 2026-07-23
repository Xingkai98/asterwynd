from __future__ import annotations

import logging

from agent.code_intelligence.config import CodeIntelligenceConfig
from agent.config import BrowserConfig, WebSearchConfig
from agent.lsp.client import LspClientManager
from agent.run_config import ModePolicy
from agent.mcp.manager import McpManager
from agent.mcp.tools import McpTool
from agent.tools.base import Tool
from agent.tools.builtin.bash import BashTool
from agent.tools.builtin.code_intelligence import RepoMapTool, SymbolSearchTool
from agent.tools.builtin.edit import EditTool
from agent.tools.builtin.find import FindTool
from agent.tools.builtin.grep import GrepTool
from agent.tools.builtin.inspect_git_diff import InspectGitDiffTool
from agent.tools.builtin.list_files import ListFilesTool
from agent.tools.builtin.lsp import (
    LspDefinitionTool,
    LspDocumentSymbolsTool,
    LspDiagnosticsTool,
    LspHoverTool,
    LspReferencesTool,
    LspWorkspaceSymbolsTool,
)
from agent.tools.builtin.read import ReadTool
from agent.tools.builtin.web_fetch import WebFetchTool
from agent.tools.builtin.web_search import WebSearchTool
from agent.memory.persistent import PersistentMemory
from agent.tools.builtin.memory import RecallMemoryTool, SaveMemoryTool
from agent.tools.builtin.write import WriteTool
from agent.tools.builtin.browser_tools import BROWSER_TOOL_CLASSES
from agent.tools.registry import ToolRegistry
from agent.workspace_policy import WorkspacePolicy

logger = logging.getLogger("asterwynd.tools.factory")


KNOWN_BUILTIN_TOOL_NAMES = {
    "AskUserQuestion",
    "Bash",
    "Edit",
    "Find",
    "Grep",
    "InspectGitDiff",
    "ListFiles",
    "ExitPlanMode",
    "UpdatePlan",
    "RepoMap",
    "Read",
    "SymbolSearch",
    "LspDefinition",
    "LspReferences",
    "LspHover",
    "LspDocumentSymbols",
    "LspWorkspaceSymbols",
    "LspDiagnostics",
    "WebFetch",
    "WebSearch",
    "Write",
    "TaskOutput",
    "TaskStop",
    "TodoWrite",
    "SaveMemory",
    "RecallMemory",
    "ActivateSkill",
    "BrowserNavigate",
    "BrowserGetContent",
    "BrowserScreenshot",
    "BrowserScroll",
    "BrowserListTabs",
    "BrowserSwitchTab",
    "BrowserCloseTab",
}


def build_default_tool_registry(
    *,
    policy: WorkspacePolicy | None = None,
    mode_policy: ModePolicy | None = None,
    ignore_patterns: tuple[str, ...] = (),
    code_intelligence_config: CodeIntelligenceConfig | None = None,
    web_search_config: WebSearchConfig | None = None,
    browser_config: BrowserConfig | None = None,
    mcp_manager: McpManager | None = None,
    tools: list[Tool] | None = None,
    persistent_memory: PersistentMemory | None = None,
) -> ToolRegistry:
    registry = ToolRegistry(mode_policy=mode_policy)
    default_tools = tools or get_default_tools(
        policy=policy,
        ignore_patterns=ignore_patterns,
        code_intelligence_config=code_intelligence_config,
        web_search_config=web_search_config,
        browser_config=browser_config,
        persistent_memory=persistent_memory,
    )
    for tool in [*default_tools, *_build_mcp_tools(mcp_manager)]:
        registry.register(tool)
    registry.mode_policy.validate_known_tools(_known_tool_names(registry))
    return registry


def _build_mcp_tools(mcp_manager: McpManager | None) -> list[Tool]:
    if mcp_manager is None:
        return []
    return [McpTool(metadata, mcp_manager) for metadata in mcp_manager.tools]


def build_coding_tool_registry(
    *,
    policy: WorkspacePolicy | None = None,
    mode_policy: ModePolicy | None = None,
    ignore_patterns: tuple[str, ...] = (),
    code_intelligence_config: CodeIntelligenceConfig | None = None,
    browser_config: BrowserConfig | None = None,
    mcp_manager: McpManager | None = None,
    persistent_memory: PersistentMemory | None = None,
) -> ToolRegistry:
    registry = ToolRegistry(mode_policy=mode_policy)
    for tool in [
        *get_coding_tools(
        policy=policy,
        ignore_patterns=ignore_patterns,
        code_intelligence_config=code_intelligence_config,
        browser_config=browser_config,
        persistent_memory=persistent_memory,
        ),
        *_build_mcp_tools(mcp_manager),
    ]:
        registry.register(tool)
    registry.mode_policy.validate_known_tools(_known_tool_names(registry))
    return registry


def _known_tool_names(registry: ToolRegistry) -> tuple[str, ...]:
    return tuple(sorted(KNOWN_BUILTIN_TOOL_NAMES | set(registry._tools)))


def _build_lsp_manager(
    policy: WorkspacePolicy,
    code_intelligence_config: CodeIntelligenceConfig | None,
) -> LspClientManager:
    config = (code_intelligence_config or CodeIntelligenceConfig()).lsp
    return LspClientManager(config=config, workspace_root=policy.workspace_root)


def _build_lsp_tools(
    policy: WorkspacePolicy,
    lsp_manager: LspClientManager,
) -> list[Tool]:
    return [
        LspDefinitionTool(policy=policy, lsp_manager=lsp_manager),
        LspReferencesTool(policy=policy, lsp_manager=lsp_manager),
        LspHoverTool(policy=policy, lsp_manager=lsp_manager),
        LspDocumentSymbolsTool(policy=policy, lsp_manager=lsp_manager),
        LspWorkspaceSymbolsTool(policy=policy, lsp_manager=lsp_manager),
        LspDiagnosticsTool(policy=policy, lsp_manager=lsp_manager),
    ]


def get_default_tools(
    policy: WorkspacePolicy | None = None,
    *,
    ignore_patterns: tuple[str, ...] = (),
    code_intelligence_config: CodeIntelligenceConfig | None = None,
    web_search_config: WebSearchConfig | None = None,
    browser_config: BrowserConfig | None = None,
    persistent_memory: PersistentMemory | None = None,
) -> list[Tool]:
    policy = policy or WorkspacePolicy()
    pmem = persistent_memory or PersistentMemory(policy.workspace_root)
    lsp_manager = _build_lsp_manager(policy, code_intelligence_config)
    tools: list[Tool] = [
        ReadTool(policy=policy),
        WriteTool(policy=policy, lsp_manager=lsp_manager),
        EditTool(policy=policy, lsp_manager=lsp_manager),
        BashTool(policy=policy),
        WebSearchTool(provider_configs=(web_search_config or WebSearchConfig()).providers),
        WebFetchTool(),
        GrepTool(policy=policy),
        InspectGitDiffTool(policy=policy),
        RepoMapTool(
            policy=policy,
            ignore_patterns=ignore_patterns,
            code_intelligence_config=code_intelligence_config,
        ),
        SymbolSearchTool(
            policy=policy,
            ignore_patterns=ignore_patterns,
            code_intelligence_config=code_intelligence_config,
        ),
        *_build_lsp_tools(policy, lsp_manager),
        SaveMemoryTool(memory=pmem),
        RecallMemoryTool(memory=pmem),
    ]

    # 浏览器工具：仅在 BrowserConfig 启用时注册
    if browser_config is not None and browser_config.enabled:
        try:
            browser_tools = _build_browser_tools(browser_config, policy)
            tools.extend(browser_tools)
        except Exception as exc:
            logger.warning("Failed to initialize browser tools: %s", exc)

    return tools


def _build_browser_tools(
    browser_config: BrowserConfig,
    policy: WorkspacePolicy,
) -> list[Tool]:
    """构建浏览器工具列表。

    如果 playwright 未安装，记录警告并返回空列表。
    """
    from agent.browser.policy import BrowserPolicy
    from agent.browser.service import BrowserService, BrowserNotAvailableError

    browser_policy = BrowserPolicy(browser_config, workspace_policy=policy)
    browser_service = BrowserService(browser_policy, browser_config)

    # 预检查 playwright 可用性（通过惰性导入检测）
    try:
        import importlib
        importlib.import_module("playwright")
    except ImportError:
        logger.warning(
            "Browser tools enabled but playwright is not installed. "
            "Install with: pip install playwright && playwright install chromium"
        )
        return []

    return [
        tool_cls(browser_service=browser_service)
        for tool_cls in BROWSER_TOOL_CLASSES
    ]


def get_coding_tools(
    policy: WorkspacePolicy | None = None,
    *,
    ignore_patterns: tuple[str, ...] = (),
    code_intelligence_config: CodeIntelligenceConfig | None = None,
    browser_config: BrowserConfig | None = None,
    persistent_memory: PersistentMemory | None = None,
) -> list[Tool]:
    policy = policy or WorkspacePolicy()
    pmem = persistent_memory or PersistentMemory(policy.workspace_root)
    lsp_manager = _build_lsp_manager(policy, code_intelligence_config)
    tools: list[Tool] = [
        ReadTool(policy=policy),
        WriteTool(policy=policy, lsp_manager=lsp_manager),
        EditTool(policy=policy, lsp_manager=lsp_manager),
        InspectGitDiffTool(policy=policy),
        ListFilesTool(policy=policy, ignore_patterns=ignore_patterns),
        FindTool(policy=policy, ignore_patterns=ignore_patterns),
        RepoMapTool(
            policy=policy,
            ignore_patterns=ignore_patterns,
            code_intelligence_config=code_intelligence_config,
        ),
        SymbolSearchTool(
            policy=policy,
            ignore_patterns=ignore_patterns,
            code_intelligence_config=code_intelligence_config,
        ),
        GrepTool(policy=policy),
        BashTool(policy=policy),
        *_build_lsp_tools(policy, lsp_manager),
        SaveMemoryTool(memory=pmem),
        RecallMemoryTool(memory=pmem),
    ]

    # 浏览器工具：仅在 BrowserConfig 启用时注册
    if browser_config is not None and browser_config.enabled:
        try:
            browser_tools = _build_browser_tools(browser_config, policy)
            tools.extend(browser_tools)
        except Exception as exc:
            logger.warning("Failed to initialize browser tools: %s", exc)

    return tools
