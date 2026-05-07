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

def get_default_tools() -> list[Tool]:
    return [
        ReadTool(),
        WriteTool(),
        BashTool(),
        WebSearchTool(),
        WebFetchTool(),
        GrepTool(),
    ]

__all__ = [
    "Tool",
    "ToolCall",
    "tool_parameters",
    "ToolRegistry",
    "SandboxExecutor",
    "get_default_tools",
    "ReadTool",
    "WriteTool",
    "BashTool",
    "WebSearchTool",
    "WebFetchTool",
    "GrepTool",
]