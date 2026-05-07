# Plan 8: 子 Agent 系统

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 SubAgentManager（后台任务委托）+ 父子通信协议 + mid-turn injection

**Architecture:**
- `SubAgentManager`：管理所有子 agent 的生命周期
- `ParentChannelHook`：Hook 实现，把子 agent 结果注入父 agent 当前轮次
- 父子通过 `asyncio.Queue` 通信

**Tech Stack:** asyncio

---

## 文件清单

- Create: `agent/subagent/protocol.py`
- Create: `agent/subagent/manager.py`
- Modify: `agent/subagent/__init__.py`
- Create: `tests/agent/subagent/test_subagent.py`

---

### Task 1: 父子通信协议（asyncio.Queue）

- [ ] **Step 1: 创建 tests/agent/subagent/test_protocol.py，写入测试**

```python
# tests/agent/subagent/test_protocol.py
import pytest
import asyncio
from agent.subagent.protocol import ParentChannel, parent_channel

def test_parent_channel_put_get():
    channel = ParentChannel(parent_id="p1", subagent_id="s1")
    channel.put_result("task done", "c1")
    result = channel.get_result(timeout=1.0)
    assert result.task == "task done"
    assert result.subagent_id == "s1"

def test_parent_channel_timeout():
    channel = ParentChannel(parent_id="p1", subagent_id="s1")
    with pytest.raises(asyncio.TimeoutError):
        channel.get_result(timeout=0.1)

def test_parent_channel_context_manager():
    with parent_channel("p1", "s1") as ch:
        ch.put_result("done", "call_1")
    # get_result after close should raise
    with pytest.raises(asyncio.TimeoutError):
        ch.get_result(timeout=0.1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/subagent/test_protocol.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 创建 agent/subagent/protocol.py**

```python
# agent/subagent/protocol.py
import asyncio
import uuid
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.message import Message

@dataclass
class SubAgentResult:
    subagent_id: str
    task: str
    result: str
    tool_call_id: str

class ParentChannel:
    """父子 agent 之间的通信通道"""

    def __init__(self, parent_id: str, subagent_id: str):
        self.parent_id = parent_id
        self.subagent_id = subagent_id
        self._queue: asyncio.Queue[SubAgentResult] = asyncio.Queue()

    def put_result(self, result: str, tool_call_id: str, task: str = "") -> None:
        self._queue.put_nowait(
            SubAgentResult(
                subagent_id=self.subagent_id,
                task=task,
                result=result,
                tool_call_id=tool_call_id,
            )
        )

    async def get_result(self, timeout: Optional[float] = None) -> SubAgentResult:
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)

    async def __aenter__(self) -> "ParentChannel":
        return self

    async def __aexit__(self, *args):
        # Drain queue on exit
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

@contextlib.contextmanager
def parent_channel(parent_id: str, subagent_id: str):
    ch = ParentChannel(parent_id, subagent_id)
    try:
        yield ch
    finally:
        pass  # cleanup happens via __aexit__ if used as async context manager

import contextlib
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/subagent/test_protocol.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/agent/subagent/test_protocol.py agent/subagent/protocol.py agent/subagent/__init__.py
git commit -m "feat: 实现父子通信协议 ParentChannel"
```

---

### Task 2: SubAgentManager + ParentChannelHook

- [ ] **Step 1: 创建 tests/agent/subagent/test_manager.py，写入测试**

```python
# tests/agent/subagent/test_manager.py
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from agent.subagent.manager import SubAgentManager
from agent.subagent.protocol import ParentChannel

@pytest.mark.asyncio
async def test_delegate_returns_subagent_id():
    manager = SubAgentManager()
    task_id = await manager.delegate(
        task="do something",
        tools=[],
        model="gpt-4o-mini",
        llm=None,
    )
    assert task_id is not None
    assert len(task_id) == 8  # hex ID

@pytest.mark.asyncio
async def test_list_subagents():
    manager = SubAgentManager()
    task_id = await manager.delegate(task="task1", tools=[], model="gpt-4o-mini", llm=None)
    assert task_id in manager.list_subagents()

@pytest.mark.asyncio
async def test_cancel_subagent():
    manager = SubAgentManager()
    task_id = await manager.delegate(task="long task", tools=[], model="gpt-4o-mini", llm=None)
    cancelled = await manager.cancel(task_id)
    assert cancelled is True
    assert task_id not in manager.list_subagents()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/subagent/test_manager.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 创建 agent/subagent/manager.py**

```python
# agent/subagent/manager.py
import asyncio
import uuid
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.llm import LLM
    from agent.message import Message
    from agent.subagent.protocol import ParentChannel

class SubAgentManager:
    """
    管理子 agent 的生命周期。
    delegate() 创建后台 asyncio task，不阻塞调用者。
    """

    def __init__(self):
        self._subagents: dict[str, asyncio.Task] = {}
        self._channels: dict[str, "ParentChannel"] = {}

    async def delegate(
        self,
        task: str,
        tools: list,
        model: str,
        llm: Optional["LLM"],
    ) -> str:
        """
        Spawn a background agent for `task`.
        Returns subagent_id for tracking.
        """
        subagent_id = uuid.uuid4().hex[:8]
        channel = ParentChannel(parent_id="main", subagent_id=subagent_id)
        self._channels[subagent_id] = channel

        # 创建后台 task
        t = asyncio.create_task(
            self._run_subagent(subagent_id, task, tools, model, llm, channel)
        )
        self._subagents[subagent_id] = t
        return subagent_id

    async def _run_subagent(
        self,
        subagent_id: str,
        task: str,
        tools: list,
        model: str,
        llm: Optional["LLM"],
        channel: "ParentChannel",
    ):
        """后台运行子 agent，完成后通过 channel 发送结果"""
        try:
            if llm is None:
                result = f"[SubAgent {subagent_id}] LLM not configured"
            else:
                from agent.message import Message
                messages = [
                    Message(role="system", content=f"你是一个子 agent，任务：{task}"),
                    Message(role="user", content=task),
                ]
                response = await llm.chat(messages, model=model)
                result = response.content or "[无内容返回]"

            channel.put_result(result, tool_call_id=f"subagent_{subagent_id}", task=task)
        except Exception as e:
            channel.put_result(f"[Error] {e}", tool_call_id=f"subagent_{subagent_id}", task=task)
        finally:
            self._subagents.pop(subagent_id, None)

    def get_channel(self, subagent_id: str) -> Optional["ParentChannel"]:
        return self._channels.get(subagent_id)

    def list_subagents(self) -> list[str]:
        return list(self._subagents.keys())

    async def cancel(self, subagent_id: str) -> bool:
        task = self._subagents.pop(subagent_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return True
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/subagent/test_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/agent/subagent/test_manager.py agent/subagent/manager.py agent/subagent/__init__.py
git commit -m "feat: 实现 SubAgentManager"
```

---

### Task 3: ParentChannelHook（mid-turn injection）

- [ ] **Step 1: 创建 agent/subagent/parent_channel_hook.py**

```python
# agent/subagent/parent_channel_hook.py
"""
ParentChannelHook：把子 agent 结果注入父 agent 当前轮次。
用于实现 mid-turn injection。
"""
from typing import TYPE_CHECKING, Optional
from agent.hooks.manager import Hook
from agent.subagent.protocol import ParentChannel, SubAgentResult

if TYPE_CHECKING:
    from agent.message import Message
    from agent.result import RunResult
    from agent.llm import LLMResponse
    from agent.tools.base import ToolCall

class ParentChannelHook(Hook):
    """
    Hook that listens for subagent results on a ParentChannel
    and injects them into the parent agent's messages mid-turn.
    """

    def __init__(
        self,
        subagent_id: str,
        channel: ParentChannel,
        parent_messages: list["Message"],
    ):
        self.subagent_id = subagent_id
        self.channel = channel
        self.parent_messages = parent_messages

    async def after_tool_execute(self, tool_call: "ToolCall", result: str) -> None:
        # 检查结果中是否有 subagent_result 标记
        if tool_call.name.startswith("delegate") and "subagent_id:" in result:
            # 从 result 中提取 subagent_id，尝试获取 channel
            # 简化实现：直接 poll channel
            try:
                sub_result: SubAgentResult = await self.channel.get_result(timeout=0.01)
                from agent.message import Message
                self.parent_messages.append(
                    Message(
                        role="tool",
                        content=sub_result.result,
                        tool_call_id=sub_result.tool_call_id,
                    )
                )
            except asyncio.TimeoutError:
                pass

    async def before_iteration(self, iteration: int, messages: list["Message"]) -> None: pass
    async def after_llm_call(self, response: "LLMResponse") -> None: pass
    async def before_tool_execute(self, tool_call: "ToolCall") -> None: pass
    async def on_error(self, error: Exception) -> None: pass
    async def on_completion(self, result: "RunResult") -> None: pass

import asyncio
```

- [ ] **Step 2: Commit**

```bash
git add agent/subagent/parent_channel_hook.py
git commit -m "feat: 实现 ParentChannelHook（mid-turn injection）"
```
