# agent/__init__.py
"""
MyAgent — 轻量级通用 AI Agent 框架
"""

from agent.loop import AgentLoop
from agent.message import Message, tool_result_message, system_message
from agent.result import RunResult, StopReason, ToolCallMade
from agent.llm import LLM, LLMResponse, LLMStreamEvent, ToolCallDelta
from agent.openai_llm import OpenAILLM
from agent.anthropic_llm import AnthropicLLM
from agent.tools import ToolRegistry, get_default_tools, Tool, ToolCall, tool_parameters
from agent.hooks.manager import HookManager, Hook
from agent.memory.manager import MemoryManager
from agent.skills.loader import SkillLoader, Skill
from agent.subagent.manager import SubAgentManager

__all__ = [
    "AgentLoop",
    "Message",
    "tool_result_message",
    "system_message",
    "RunResult",
    "StopReason",
    "ToolCallMade",
    "LLM",
    "LLMResponse",
    "LLMStreamEvent",
    "ToolCallDelta",
    "OpenAILLM",
    "AnthropicLLM",
    "ToolRegistry",
    "get_default_tools",
    "Tool",
    "ToolCall",
    "tool_parameters",
    "HookManager",
    "Hook",
    "MemoryManager",
    "SkillLoader",
    "Skill",
    "SubAgentManager",
]
