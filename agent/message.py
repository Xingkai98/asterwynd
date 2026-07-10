# agent/message.py
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Literal, Optional, Any


# ── Content Block types ──────────────────────────────────────────────

@dataclass
class ImageUrl:
    """图片 URL，支持 base64 data URL 或 HTTP URL"""
    url: str
    detail: str | None = None  # "auto" | "low" | "high" (OpenAI)


@dataclass
class TextBlock:
    """文本内容块 — 构造时应显式传入 text= 关键字参数"""
    text: str = ""
    type: Literal["text"] = field(default="text", init=False)


@dataclass
class ImageBlock:
    """图片内容块"""
    image_url: ImageUrl = field(default_factory=lambda: ImageUrl(url=""))
    file_path: str | None = None  # 本地文件路径，用于 compact/trace 引用
    type: Literal["image_url"] = field(default="image_url", init=False)


ContentBlock = TextBlock | ImageBlock


# ── Helpers ───────────────────────────────────────────────────────────

def content_block_to_dict(block: ContentBlock) -> dict:
    """将单个 ContentBlock 序列化为 dict"""
    if isinstance(block, TextBlock):
        return {"type": block.type, "text": block.text}
    d: dict = {"type": block.type, "image_url": asdict(block.image_url)}
    if block.file_path:
        d["file_path"] = block.file_path
    return d


def content_block_from_dict(data: dict) -> ContentBlock:
    """从 dict 反序列化 ContentBlock"""
    block_type = data.get("type", "text")
    if block_type == "text":
        return TextBlock(text=data.get("text", ""))
    if block_type == "image_url":
        image_url_data = data.get("image_url", {})
        return ImageBlock(
            image_url=ImageUrl(
                url=image_url_data.get("url", ""),
                detail=image_url_data.get("detail"),
            ),
            file_path=data.get("file_path"),
        )
    return TextBlock(text=data.get("text", ""))


def extract_text(content: str | list[ContentBlock]) -> str:
    """从 content 中提取纯文本"""
    if isinstance(content, str):
        return content
    return "\n".join(
        b.text for b in content if isinstance(b, TextBlock)
    )


def count_tokens_for_content(content: str | list[ContentBlock], counter) -> int:
    """对 content 进行 token 计数。ImageBlock 按固定 1000 token/张估算。"""
    if isinstance(content, str):
        return counter(content)
    total = 0
    for block in content:
        if isinstance(block, TextBlock):
            total += counter(block.text)
        elif isinstance(block, ImageBlock):
            total += 1000
    return total


# ── Message ───────────────────────────────────────────────────────────

@dataclass
class Message:
    """代表一条对话消息"""
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentBlock]
    tool_call_id: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role}
        if isinstance(self.content, str):
            d["content"] = self.content
        else:
            d["content"] = [content_block_to_dict(b) for b in self.content]
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.reasoning_content is not None:
            d["reasoning_content"] = self.reasoning_content
        if self.tool_calls:
            d["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in self.tool_calls
            ]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        from agent.llm import ToolCallDelta

        content = data.get("content", "")
        if isinstance(content, list):
            content = [content_block_from_dict(b) for b in content]
        tool_calls = [
            call if isinstance(call, ToolCallDelta)
            else ToolCallDelta(
                id=call.get("id", ""),
                name=call.get("name", ""),
                arguments=call.get("arguments", ""),
            )
            for call in data.get("tool_calls", [])
        ]
        return cls(
            role=data["role"],
            content=content,
            tool_call_id=data.get("tool_call_id"),
            reasoning_content=data.get("reasoning_content"),
            tool_calls=tool_calls,
        )


def tool_result_message(tool_call_id: str, content: str | list[ContentBlock]) -> Message:
    """快捷构造工具结果消息"""
    return Message(role="tool", content=content, tool_call_id=tool_call_id)


def system_message(content: str) -> Message:
    """快捷构造系统消息"""
    return Message(role="system", content=content)
