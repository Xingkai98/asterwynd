# agent/message.py
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from typing import Literal, Optional, Any

logger = logging.getLogger("asterwynd.message")


def _has_lone_surrogate(text: str) -> bool:
    """文本是否含 lone surrogate（U+D800–U+DFFF）。

    这类字符不是合法 Unicode 文本，`json.dump(ensure_ascii=False)` 无法编码；
    真实端点的 reasoning 签名不会出现它们（issue #256 审阅 S-3）。
    """
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


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
    cache: bool = False  # 稳定前缀标记（Anthropic cache_control 断点用）


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
        d = {"type": block.type, "text": block.text}
        if block.cache:
            d["cache"] = True
        return d
    d: dict = {"type": block.type, "image_url": asdict(block.image_url)}
    if block.file_path:
        d["file_path"] = block.file_path
    return d


def content_block_from_dict(data: dict) -> ContentBlock:
    """从 dict 反序列化 ContentBlock"""
    block_type = data.get("type", "text")
    if block_type == "text":
        return TextBlock(text=data.get("text", ""), cache=bool(data.get("cache", False)))
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


# ── ReasoningBlock ────────────────────────────────────────────────────

@dataclass
class ReasoningBlock:
    """思维链的一段（issue #256）。

    一段 = **可展示文本** + **可选的 opaque 回传载荷**。二者职责严格分离：

    - ``text``：供展示与日志使用。
    - ``opaque``：provider 的不透明回传载荷（如 Anthropic 的 ``signature``）。
      它 **只回传、永不展示、永不解析**，且在「采集 → 持久化 → 回放」全链路
      必须 **逐字节不变** —— 绝不可经 ``_strip_surrogates`` 之类的清洗函数，
      否则签名会被改写导致回传校验失败。
    """
    text: str = ""
    opaque: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"text": self.text}
        if self.opaque is not None:
            # 不变量边界：opaque 必须是**合法 Unicode 文本**（不含 lone surrogate）。
            # 真实端点的签名都是 ASCII（Anthropic 为 base64、DeepSeek 为 UUID），
            # 不会有 surrogate；但 lone surrogate 本身不是合法 Unicode 文本，
            # `json.dump(ensure_ascii=False)` 会抛 UnicodeEncodeError 让整个
            # session 保存崩掉（issue #256 审阅 S-3）。这里按「丢弃该 opaque、
            # 保留 text」降级——比崩掉保存更安全，且不变量在合法输入上仍成立。
            if _has_lone_surrogate(self.opaque):
                logger.warning(
                    "Dropping reasoning opaque payload containing lone surrogates "
                    "(not valid Unicode text; cannot be persisted)"
                )
            else:
                d["opaque"] = self.opaque
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ReasoningBlock":
        if isinstance(data, ReasoningBlock):
            return data
        return cls(text=data.get("text", ""), opaque=data.get("opaque"))


# ── Message ───────────────────────────────────────────────────────────

@dataclass
class Message:
    """代表一条对话消息"""
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentBlock]
    tool_call_id: Optional[str] = None
    reasoning: list[ReasoningBlock] = field(default_factory=list)
    tool_calls: list = field(default_factory=list)
    # 非序列化 token 计数缓存（增量计数用；to_dict/from_dict 不包含）
    _tokens: Optional[int] = field(default=None, repr=False, compare=False)

    @property
    def reasoning_text(self) -> str:
        """所有段的可展示文本按序拼接（供展示层消费；忽略 opaque）。"""
        return "".join(block.text for block in self.reasoning)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role}
        if isinstance(self.content, str):
            d["content"] = self.content
        else:
            d["content"] = [content_block_to_dict(b) for b in self.content]
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.reasoning:
            d["reasoning"] = [block.to_dict() for block in self.reasoning]
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
        reasoning = [ReasoningBlock.from_dict(b) for b in data.get("reasoning", [])]
        if not reasoning and data.get("reasoning_content"):
            # 旧会话兼容（Q1：旧字段只读，读入即包成单段；新写入只写 reasoning）
            reasoning = [ReasoningBlock(text=data["reasoning_content"])]
        return cls(
            role=data["role"],
            content=content,
            tool_call_id=data.get("tool_call_id"),
            reasoning=reasoning,
            tool_calls=tool_calls,
        )


def tool_result_message(tool_call_id: str, content: str | list[ContentBlock]) -> Message:
    """快捷构造工具结果消息"""
    return Message(role="tool", content=content, tool_call_id=tool_call_id)


# ── Tool-call pairing repair (issue #304) ─────────────────────────────

#: 合成 tool_result 的固定前缀。序列化层据此写 provider 级错误信号
#: （Anthropic ``is_error: true``；OpenAI 用 ``Error:`` 文本前缀）。
SYNTHETIC_TOOL_RESULT_PREFIX = "[asterwynd:synthetic-tool-result] Error:"

#: 合成文案里 name/id 的展示上限（原 id 仍完整保存在 tool_call_id）。
_SYNTHETIC_LABEL_LIMIT = 128


@dataclass(frozen=True)
class RepairedCall:
    tool_call_id: str
    tool_name: str


@dataclass(frozen=True)
class RepairReport:
    """一次配对修复的结果；``messages`` 是修复后的列表（纯函数，不改入参）。"""

    messages: list[Message]
    repaired: list[RepairedCall]

    @property
    def changed(self) -> bool:
        return bool(self.repaired)


def _bounded_label(value: object, limit: int = _SYNTHETIC_LABEL_LIMIT) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _synthetic_tool_result(tool_call) -> Message:
    tool_name = _bounded_label(getattr(tool_call, "name", ""))
    tool_id = _bounded_label(getattr(tool_call, "id", ""))
    content = (
        f"{SYNTHETIC_TOOL_RESULT_PREFIX} Tool call '{tool_name}' ({tool_id}) "
        "did not complete because the run was interrupted before a result was "
        "recorded. The tool may have partially executed; inspect state before "
        "retrying."
    )
    return Message(role="tool", content=content, tool_call_id=tool_call.id)


def repair_tool_call_pairing(messages: list[Message]) -> RepairReport:
    """为中断遗留的悬空 assistant ``tool_calls`` 补合成 ``tool_result``。

    规则（design Decision 3/4）：

    - 按 assistant 分组，只把紧随其后的连续 ``role="tool"`` 消息视为结果块；
    - 只在该 id 于整条历史中都没有任何 ``role="tool"`` 消息时合成；
      结果存在但位置不合法（orphan-before / misplaced-after）只记录、不合成，
      避免同一 ``tool_use_id`` 出现两条结果；
    - 同一 assistant 的多个缺失按原 ``tool_calls`` 顺序插入；
    - 空 id 不合成；正常链返回原列表对象，零改动。
    """
    tool_ids_in_history = {
        m.tool_call_id
        for m in messages
        if m.role == "tool" and m.tool_call_id
    }
    repaired: list[RepairedCall] = []
    out: list[Message] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        out.append(message)
        if message.role != "assistant" or not message.tool_calls:
            index += 1
            continue

        block_end = index + 1
        while block_end < len(messages) and messages[block_end].role == "tool":
            out.append(messages[block_end])
            block_end += 1

        resolved_in_block = {
            m.tool_call_id
            for m in messages[index + 1:block_end]
            if m.tool_call_id
        }
        seen_ids: set[str] = set()
        synthetic: list[Message] = []
        for tool_call in message.tool_calls:
            tool_call_id = getattr(tool_call, "id", "") or ""
            if not tool_call_id:
                logger.warning(
                    "Skipping tool-call pairing repair for empty tool_call_id "
                    "(assistant message index %d)", index,
                )
                continue
            if tool_call_id in resolved_in_block or tool_call_id in seen_ids:
                continue
            seen_ids.add(tool_call_id)
            if tool_call_id in tool_ids_in_history:
                logger.warning(
                    "Not synthesizing tool result for %r: a result exists in a "
                    "non-adjacent position (orphan/misplaced); leaving the "
                    "malformed chain unchanged", _bounded_label(tool_call_id),
                )
                continue
            synthetic.append(_synthetic_tool_result(tool_call))
            repaired.append(RepairedCall(
                tool_call_id=tool_call_id,
                tool_name=str(getattr(tool_call, "name", "") or ""),
            ))

        if synthetic:
            out.extend(synthetic)
        index = block_end

    if not repaired:
        return RepairReport(messages=messages, repaired=[])
    return RepairReport(messages=out, repaired=repaired)


def system_message(content: str) -> Message:
    """快捷构造系统消息"""
    return Message(role="system", content=content)
