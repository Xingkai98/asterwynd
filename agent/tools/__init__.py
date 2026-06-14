# agent/tools/__init__.py
from agent.tools.base import Tool, ToolCall, tool_parameters
from agent.tools.registry import ToolRegistry
from agent.tools.sandbox import SandboxExecutor

# 内置工具
from agent.tools.builtin.read import ReadTool
from agent.tools.builtin.write import WriteTool
from agent.tools.builtin.bash import BashTool
from agent.tools.builtin.web_search import WebSearchTool
from agent.tools.builtin.web_fetch import WebFetchTool
from agent.tools.builtin.grep import GrepTool
from agent.tools.builtin.edit import EditTool
from agent.tools.builtin.inspect_git_diff import InspectGitDiffTool
from agent.workspace_policy import WorkspacePolicy

def get_default_tools(policy: WorkspacePolicy | None = None) -> list[Tool]:
    policy = policy or WorkspacePolicy()
    return [
        ReadTool(),
        WriteTool(policy=policy),
        EditTool(policy=policy),
        BashTool(),
        WebSearchTool(),
        WebFetchTool(),
        GrepTool(),
        InspectGitDiffTool(policy=policy),
    ]

def get_coding_tools(policy: WorkspacePolicy | None = None) -> list[Tool]:
    policy = policy or WorkspacePolicy()
    return [
        ReadTool(),
        WriteTool(policy=policy),
        EditTool(policy=policy),
        InspectGitDiffTool(policy=policy),
        GrepTool(),
        BashTool(),
    ]

__all__ = [
    "Tool",
    "ToolCall",
    "tool_parameters",
    "ToolRegistry",
    "SandboxExecutor",
    "get_default_tools",
    "get_coding_tools",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "InspectGitDiffTool",
    "BashTool",
    "WebSearchTool",
    "WebFetchTool",
    "GrepTool",
]
