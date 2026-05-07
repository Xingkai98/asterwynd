# agent/message.py
from dataclasses import dataclass, asdict, field
from typing import Literal, Optional, Any

@dataclass
class Message:
    """代表一条对话消息"""
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: Optional[str] = None
    # tool_calls: list of ToolCallDelta, for assistant messages carrying tool_use blocks to be sent back to LLM
    tool_calls: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.tool_call_id is None:
            d.pop("tool_call_id", None)
        if not self.tool_calls:
            d.pop("tool_calls", None)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(**data)

def tool_result_message(tool_call_id: str, content: str) -> "Message":
    """快捷构造工具结果消息"""
    return Message(role="tool", content=content, tool_call_id=tool_call_id)

def system_message(content: str) -> "Message":
    """快捷构造系统消息"""
    return Message(role="system", content=content)