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
from agent.tools.builtin.list_files import ListFilesTool
from agent.tools.builtin.find import FindTool
from agent.workspace_policy import WorkspacePolicy

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
    "ListFilesTool",
    "FindTool",
    "BashTool",
    "WebSearchTool",
    "WebFetchTool",
    "GrepTool",
]
