# agent/llm.py
from dataclasses import dataclass, field
from typing import Protocol, Optional, runtime_checkable

@dataclass
class ToolCallDelta:
    id: str
    name: str
    arguments: str  # JSON string

@runtime_checkable
class LLM(Protocol):
    """LLM provider 接口"""
    async def chat(
        self,
        messages: list["Message"],
        tools: Optional[list[dict]] = None,
        model: str = "gpt-4",
    ) -> "LLMResponse":
        ...

@dataclass
class LLMResponse:
    content: Optional[str]
    tool_calls: list[ToolCallDelta] = field(default_factory=list)
    stop_reason: Optional[str] = None