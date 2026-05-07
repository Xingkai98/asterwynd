# Plan 3: LLM 接口抽象

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 定义 LLM 接口抽象（Protocol），实现 OpenAI Chat Completions 调用

**Architecture:** LLM 是纯接口，不感知 AgentLoop 的存在。所有模型通过实现 Protocol 使用

**Tech Stack:** Protocol (typing), aiohttp

---

## 文件清单

- Create: `agent/llm.py`
- Modify: `agent/__init__.py`

---

### Task 1: 定义 LLM Protocol 接口

- [ ] **Step 1: 创建 tests/agent/test_llm.py，写入测试**

```python
# tests/agent/test_llm.py
import pytest
from agent.llm import LLMResponse, ToolCallDelta
from agent.message import Message

def test_llm_response():
    response = LLMResponse(
        content="Hello!",
        tool_calls=[],
    )
    assert response.content == "Hello!"

def test_llm_response_with_tool_calls():
    response = LLMResponse(
        content="",
        tool_calls=[
            ToolCallDelta(id="call_1", name="Bash", arguments='{"cmd": "ls"}')
        ],
    )
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "Bash"

def test_llm_response_no_content():
    response = LLMResponse(content=None, tool_calls=[])
    assert response.content is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_llm.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 创建 agent/llm.py**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/agent/test_llm.py agent/llm.py agent/__init__.py
git commit -m "feat: 添加 LLM Protocol 接口和 LLMResponse 类型"
```

---

### Task 2: 实现 OpenAI LLM

- [ ] **Step 1: 创建 tests/agent/test_openai_llm.py，写入测试**

```python
# tests/agent/test_openai_llm.py
import pytest
from unittest.mock import AsyncMock, patch
from agent.openai_llm import OpenAILLM
from agent.message import Message

@pytest.mark.asyncio
async def test_openai_chat_success():
    llm = OpenAILLM(api_key="test-key", base_url="https://api.openai.com/v1")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 10},
        }
        messages = [Message(role="user", content="Hi")]
        response = await llm.chat(messages, model="gpt-4")
        assert response.content == "Hello!"

@pytest.mark.asyncio
async def test_openai_tool_call():
    llm = OpenAILLM(api_key="test-key")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.json.return_value = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [
                        {"id": "call_1", "function": {"name": "Bash", "arguments": '{"cmd": "ls"}'}
                    ]
                },
                "finish_reason": "tool_calls"
            }],
            "usage": {"total_tokens": 50},
        }
        messages = [Message(role="user", content="Run ls")]
        response = await llm.chat(messages, model="gpt-4")
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "Bash"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_openai_llm.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 创建 agent/openai_llm.py**

```python
# agent/openai_llm.py
import json
from typing import Optional
import httpx

from agent.llm import LLM, LLMResponse, ToolCallDelta
from agent.message import Message

class OpenAILLM:
    """OpenAI Chat Completions API 实现"""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
            )
        return self._client

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        model: str = "gpt-4",
    ) -> LLMResponse:
        client = await self._get_client()

        payload: dict = {
            "model": model,
            "messages": [self._message_to_dict(m) for m in messages],
        }
        if tools:
            payload["tools"] = tools

        response = await client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        message = choice["message"]

        if "tool_calls" in message and message["tool_calls"]:
            tool_calls = [
                ToolCallDelta(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                )
                for tc in message["tool_calls"]
            ]
            return LLMResponse(content=None, tool_calls=tool_calls, stop_reason="tool_calls")

        return LLMResponse(
            content=message.get("content"),
            tool_calls=[],
            stop_reason=choice.get("finish_reason"),
        )

    def _message_to_dict(self, msg: Message) -> dict:
        d: dict = {"role": msg.role, "content": msg.content}
        if msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        return d

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_openai_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/agent/test_openai_llm.py agent/openai_llm.py agent/__init__.py
git commit -m "feat: 实现 OpenAI LLM provider"
```
