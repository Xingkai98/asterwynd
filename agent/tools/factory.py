from __future__ import annotations

from agent.run_config import ModePolicy
from agent.tools.base import Tool
from agent.tools.builtin.bash import BashTool
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


def build_default_tool_registry(
    *,
    policy: WorkspacePolicy | None = None,
    mode_policy: ModePolicy | None = None,
    tools: list[Tool] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry(mode_policy=mode_policy)
    for tool in tools or get_default_tools(policy=policy):
        registry.register(tool)
    return registry


def build_coding_tool_registry(
    *,
    policy: WorkspacePolicy | None = None,
    mode_policy: ModePolicy | None = None,
) -> ToolRegistry:
    registry = ToolRegistry(mode_policy=mode_policy)
    for tool in get_coding_tools(policy=policy):
        registry.register(tool)
    return registry


def get_default_tools(policy: WorkspacePolicy | None = None) -> list[Tool]:
    policy = policy or WorkspacePolicy()
    return [
        ReadTool(policy=policy),
        WriteTool(policy=policy),
        EditTool(policy=policy),
        BashTool(policy=policy),
        WebSearchTool(),
        WebFetchTool(),
        GrepTool(policy=policy),
        InspectGitDiffTool(policy=policy),
    ]


def get_coding_tools(policy: WorkspacePolicy | None = None) -> list[Tool]:
    policy = policy or WorkspacePolicy()
    return [
        ReadTool(policy=policy),
        WriteTool(policy=policy),
        EditTool(policy=policy),
        InspectGitDiffTool(policy=policy),
        ListFilesTool(policy=policy),
        FindTool(policy=policy),
        GrepTool(policy=policy),
        BashTool(policy=policy),
    ]
