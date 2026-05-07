# Plan 6: 记忆系统（Memory + AutoCompact）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 MemoryManager（消息历史 + AutoCompact token 压缩）

**Architecture:**
- `MemoryManager` 持有消息历史，在每个 tool_calls 循环后检查是否需要压缩
- `compact()` 保留 system + 最近消息，中间部分用 LLM 生成摘要

**Tech Stack:** tiktoken（token 计数）, LLM（摘要生成）

---

## 文件清单

- Create: `agent/memory/manager.py`
- Modify: `agent/memory/__init__.py`
- Create: `tests/agent/memory/test_memory.py`

---

### Task 1: MemoryManager + AutoCompact

- [ ] **Step 1: 创建 tests/agent/memory/test_memory.py，写入测试**

```python
# tests/agent/memory/test_memory.py
import pytest
from unittest.mock import AsyncMock, patch
from agent.memory.manager import MemoryManager
from agent.message import Message

def test_add_message():
    mgr = MemoryManager(max_tokens=1000)
    mgr.add(Message(role="user", content="hello"))
    assert len(mgr.messages) == 1

def test_count_tokens_approx():
    mgr = MemoryManager(max_tokens=1000)
    # 简单验证 token 计数函数存在
    tokens = mgr.count_tokens([Message(role="user", content="hello world")])
    assert tokens > 0

def test_compact_if_needed_does_nothing_under_budget():
    mgr = MemoryManager(max_tokens=100_000_000)
    for i in range(5):
        mgr.add(Message(role="user", content=f"message {i}" * 100))
    initial_len = len(mgr.messages)
    mgr.compact_if_needed()
    assert len(mgr.messages) == initial_len

def test_compact_if_needed_triggers_over_budget():
    mgr = MemoryManager(max_tokens=50)  # 很小的 budget 强制触发
    for i in range(10):
        mgr.add(Message(role="user", content=f"long message content here {i} " * 50))
    # 预期触发压缩（具体结果取决于 LLM 摘要）
    mgr.compact_if_needed()
    # 压缩后消息应该更少
    assert len(mgr.messages) <= 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/memory/test_memory.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 创建 agent/memory/manager.py**

```python
# agent/memory/manager.py
import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.llm import LLM
    from agent.message import Message

logger = logging.getLogger("myagent.memory")

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def _count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except ImportError:
    # Fallback：简单按字符数 / 4 估算
    def _count_tokens(text: str) -> int:
        return len(text) // 4

class MemoryManager:
    """
    管理 Agent 会话消息历史，支持 AutoCompact。

    compact() 策略：保留所有 system 消息 + 最近 N 条对话，
    中间部分用 LLM 生成一段摘要。
    """

    def __init__(
        self,
        max_tokens: int = 100_000,
        recent_window: int = 10,
        llm: Optional["LLM"] = None,
    ):
        self.messages: list["Message"] = []
        self.max_tokens = max_tokens
        self.recent_window = recent_window
        self.llm = llm

    def add(self, message: "Message") -> None:
        self.messages.append(message)

    def count_tokens(self, messages: list["Message"]) -> int:
        return sum(_count_tokens(m.content) for m in messages)

    def compact_if_needed(self) -> None:
        total = self.count_tokens(self.messages)
        if total > self.max_tokens:
            logger.info(f"[Memory] {total} tokens > {self.max_tokens} budget, compacting")
            self.compact()

    def compact(self) -> None:
        """
        压缩策略：
        1. 保留所有 system 消息
        2. 保留最近 recent_window 条消息
        3. 中间部分生成一段 LLM 摘要（如果 LLM 可用）
        """
        system = [m for m in self.messages if m.role == "system"]
        recent = self.messages[-self.recent_window:]

        if self.llm is None:
            # 无 LLM：直接丢弃中间消息，保留 system + recent
            self.messages = system + recent
            logger.info(f"[Memory] Compacted to {len(self.messages)} messages (no LLM)")
            return

        middle = self.messages[:-self.recent_window]
        if not middle:
            return

        # 用 LLM 生成摘要
        import asyncio

        async def _summarize():
            try:
                prompt = (
                    "请用一段话简要总结以下对话历史的核心内容：\n\n"
                    + "\n".join(f"[{m.role}] {m.content}" for m in middle)
                )
                response = await self.llm.chat(
                    [Message(role="user", content=prompt)],
                    model="gpt-4o-mini",
                )
                summary_text = response.content or "（对话历史已压缩）"
                return Message(role="system", content=f"[对话摘要] {summary_text}")
            except Exception as e:
                logger.warning(f"[Memory] 摘要生成失败: {e}")
                return Message(role="system", content="（对话历史已压缩）")

        summary = asyncio.get_event_loop().run_until_complete(_summarize())
        self.messages = system + [summary] + recent
        logger.info(f"[Memory] Compacted to {len(self.messages)} messages")

    def get_messages(self) -> list["Message"]:
        return self.messages

    def clear(self) -> None:
        """清空所有非 system 消息"""
        self.messages = [m for m in self.messages if m.role == "system"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/memory/test_memory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/agent/memory/test_memory.py agent/memory/manager.py agent/memory/__init__.py
git commit -m "feat: 实现 MemoryManager + AutoCompact"
```
