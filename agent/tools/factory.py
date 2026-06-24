from __future__ import annotations

from agent.code_intelligence.config import CodeIntelligenceConfig
from agent.config import WebSearchConfig
from agent.run_config import ModePolicy
from agent.tools.base import Tool
from agent.tools.builtin.bash import BashTool
from agent.tools.builtin.code_intelligence import RepoMapTool, SymbolSearchTool
from agent.tools.builtin.edit import EditTool
from agent.tools.builtin.find import FindTool
from agent.tools.builtin.grep import GrepTool
from agent.tools.builtin.inspect_git_diff import InspectGitDiffTool
from agent.tools.builtin.list_files import ListFilesTool
from agent.tools.builtin.read import ReadTool
from agent.tools.builtin.web_fetch import WebFetchTool
from agent.tools.builtin.web_search import WebSearchTool
from agent.tools.builtin.write import WriteTool
from agent.tools.registry import ToolRegistry
from agent.workspace_policy import WorkspacePolicy


KNOWN_BUILTIN_TOOL_NAMES = {
    "Bash",
    "Edit",
    "Find",
    "Grep",
    "InspectGitDiff",
    "ListFiles",
    "RepoMap",
    "Read",
    "SymbolSearch",
    "WebFetch",
    "WebSearch",
    "Write",
}


def build_default_tool_registry(
    *,
    policy: WorkspacePolicy | None = None,
    mode_policy: ModePolicy | None = None,
    ignore_patterns: tuple[str, ...] = (),
    code_intelligence_config: CodeIntelligenceConfig | None = None,
    web_search_config: WebSearchConfig | None = None,
    tools: list[Tool] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry(mode_policy=mode_policy)
    for tool in tools or get_default_tools(
        policy=policy,
        ignore_patterns=ignore_patterns,
        code_intelligence_config=code_intelligence_config,
        web_search_config=web_search_config,
    ):
        registry.register(tool)
    registry.mode_policy.validate_known_tools(_known_tool_names(registry))
    return registry


def build_coding_tool_registry(
    *,
    policy: WorkspacePolicy | None = None,
    mode_policy: ModePolicy | None = None,
    ignore_patterns: tuple[str, ...] = (),
    code_intelligence_config: CodeIntelligenceConfig | None = None,
) -> ToolRegistry:
    registry = ToolRegistry(mode_policy=mode_policy)
    for tool in get_coding_tools(
        policy=policy,
        ignore_patterns=ignore_patterns,
        code_intelligence_config=code_intelligence_config,
    ):
        registry.register(tool)
    registry.mode_policy.validate_known_tools(_known_tool_names(registry))
    return registry


def _known_tool_names(registry: ToolRegistry) -> tuple[str, ...]:
    return tuple(sorted(KNOWN_BUILTIN_TOOL_NAMES | set(registry._tools)))


def get_default_tools(
    policy: WorkspacePolicy | None = None,
    *,
    ignore_patterns: tuple[str, ...] = (),
    code_intelligence_config: CodeIntelligenceConfig | None = None,
    web_search_config: WebSearchConfig | None = None,
) -> list[Tool]:
    policy = policy or WorkspacePolicy()
    return [
        ReadTool(policy=policy),
        WriteTool(policy=policy),
        EditTool(policy=policy),
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
    ]


def get_coding_tools(
    policy: WorkspacePolicy | None = None,
    *,
    ignore_patterns: tuple[str, ...] = (),
    code_intelligence_config: CodeIntelligenceConfig | None = None,
) -> list[Tool]:
    policy = policy or WorkspacePolicy()
    return [
        ReadTool(policy=policy),
        WriteTool(policy=policy),
        EditTool(policy=policy),
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
    ]
