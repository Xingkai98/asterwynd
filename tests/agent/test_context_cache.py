# tests/agent/test_context_cache.py
"""Sub-change ② tests: prefix-cache injection order, cache_control breakpoints,
stable-prefix layering, and deterministic tool ordering.

Coverage map:
- TextBlock.cache round-trips serialization (task 2.1)
- ContextBuilder.build_blocks returns per-P TextBlocks; build() stays str (2.1)
- Cacheable sources are frozen outside the budget pass (2.5)
- Anthropic _build_payload cache_control placement (2.3)
- Per-mode CachePlan strategy, selector OFF vs ON (2.3)
- cache_control 400 retry fallback (2.3)
- OpenAI payload never carries cache_control (2.4)
- Loop wires set_stable_tools with the core tool set (2.2)
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from agent.anthropic_llm import AnthropicLLM
from agent.llm import CachePlan, ToolCallDelta
from agent.message import Message, TextBlock, content_block_from_dict, content_block_to_dict
from agent.context.builder import ContextBuilder
from agent.context.protocol import BuildContext
from agent.run_config import AgentMode
from agent.tools.governance.selector import ToolSelector
from agent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# TextBlock.cache serialization (task 2.1)
# ---------------------------------------------------------------------------


class TestTextBlockCacheRoundTrip:
    def test_cache_flag_preserved(self):
        block = TextBlock(text="stable", cache=True)
        d = content_block_to_dict(block)
        assert d["cache"] is True
        restored = content_block_from_dict(d)
        assert restored.cache is True
        assert restored.text == "stable"

    def test_cache_flag_default_false_and_omitted(self):
        block = TextBlock(text="plain")
        d = content_block_to_dict(block)
        assert "cache" not in d
        restored = content_block_from_dict(d)
        assert restored.cache is False

    def test_message_roundtrip_preserves_cache_flag(self):
        msg = Message(role="system", content=[
            TextBlock(text="P0", cache=True),
            TextBlock(text="P4", cache=False),
        ])
        restored = Message.from_dict(msg.to_dict())
        assert restored.content[0].cache is True
        assert restored.content[1].cache is False


# ---------------------------------------------------------------------------
# ContextBuilder build_blocks + stable-prefix freeze (tasks 2.1, 2.5)
# ---------------------------------------------------------------------------


class _StableSource:
    name = "Stable"
    priority = 0
    budget = 1000
    critical = True
    cacheable = True

    async def render(self, context: BuildContext) -> str:
        return "STABLE"


class _VariableSource:
    name = "Variable"
    priority = 5
    budget = 1000
    critical = False

    async def render(self, context: BuildContext) -> str:
        return "VAR " * 200


def _ctx():
    return BuildContext(
        cwd="/tmp/x", mode=AgentMode.BUILD,
        context_window=100_000, total_budget=100,
    )


class TestBuildBlocks:
    async def test_build_still_returns_str(self):
        builder = ContextBuilder(total_budget=10_000)
        builder.register(_StableSource())
        builder.register(_VariableSource())
        result = await builder.build(_ctx())
        assert isinstance(result, str)
        assert "STABLE" in result

    async def test_build_blocks_returns_textblocks_with_cache_flags(self):
        builder = ContextBuilder(total_budget=10_000)
        builder.register(_StableSource())
        builder.register(_VariableSource())
        blocks = await builder.build_blocks(_ctx())
        assert all(isinstance(b, TextBlock) for b in blocks)
        stable = [b for b in blocks if b.text == "STABLE"]
        variable = [b for b in blocks if b.text.startswith("VAR")]
        assert stable and stable[0].cache is True
        assert variable and variable[0].cache is False

    async def test_cacheable_source_survives_budget_pressure(self):
        """P0/P1/P2 (cacheable) are frozen outside the budget pass (task 2.5)."""
        builder = ContextBuilder(total_budget=50)  # very tight
        builder.register(_StableSource())
        builder.register(_VariableSource())
        blocks = await builder.build_blocks(_ctx())
        texts = [b.text for b in blocks]
        assert any(t == "STABLE" for t in texts)  # cacheable layer not trimmed


# ---------------------------------------------------------------------------
# Anthropic _build_payload cache_control placement (task 2.3)
# ---------------------------------------------------------------------------


def _llm() -> AnthropicLLM:
    return AnthropicLLM(api_key="test", base_url="https://api.anthropic.com")


def _system_blocks(*cache_flags):
    return Message(
        role="system",
        content=[TextBlock(text=f"layer-{i}", cache=flag) for i, flag in enumerate(cache_flags)],
    )


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "description": name, "parameters": {}}}


class TestAnthropicCacheControl:
    def test_breakpoint_on_last_stable_system_block(self):
        llm = _llm()
        llm.cache_plan = CachePlan(stable_system_block_count=3, stable_tool_count=0)
        messages = [
            _system_blocks(True, True, True, False, False),  # P0 P1 P2 stable; P4 P5 variable
            Message(role="user", content="hi"),
        ]
        payload = llm._build_payload(messages, tools=None, model="claude-sonnet-4-20250514")
        system = payload["system"]
        assert "cache_control" not in system[0]
        assert "cache_control" not in system[1]
        assert system[2]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in system[3]
        assert "cache_control" not in system[4]

    def test_breakpoint_on_last_core_tool(self):
        llm = _llm()
        llm.cache_plan = CachePlan(stable_system_block_count=0, stable_tool_count=2)
        tools = [_tool("Read"), _tool("Edit"), _tool("WebSearch")]
        payload = llm._build_payload(
            [Message(role="user", content="hi")],
            tools=tools,
            model="claude-sonnet-4-20250514",
        )
        converted = payload["tools"]
        assert "cache_control" not in converted[0]
        assert converted[1]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in converted[2]

    def test_no_cache_control_without_plan(self):
        llm = _llm()
        messages = [_system_blocks(True, True), Message(role="user", content="hi")]
        payload = llm._build_payload(messages, tools=[_tool("Read")], model="m")
        assert "cache_control" not in str(payload.get("system", []))
        assert "cache_control" not in str(payload.get("tools", []))

    def test_plan_consumed_once(self):
        llm = _llm()
        llm.cache_plan = CachePlan(stable_system_block_count=1, stable_tool_count=0)
        messages = [_system_blocks(True), Message(role="user", content="hi")]
        llm._build_payload(messages, tools=None, model="m")
        # Second build sees no plan (consumed).
        payload = llm._build_payload(messages, tools=None, model="m")
        assert "cache_control" not in str(payload.get("system", []))

    def test_strip_cache_control(self):
        payload = {
            "system": [{"type": "text", "text": "a", "cache_control": {"type": "ephemeral"}}],
            "tools": [{"name": "Read", "cache_control": {"type": "ephemeral"}}],
        }
        assert AnthropicLLM._payload_has_cache_control(payload)
        stripped = AnthropicLLM._strip_cache_control(payload)
        assert not AnthropicLLM._payload_has_cache_control(stripped)
        assert stripped["system"][0]["text"] == "a"

    @pytest.mark.asyncio
    async def test_cache_control_400_retry(self):
        import httpx
        llm = _llm()
        llm.cache_plan = CachePlan(stable_system_block_count=1, stable_tool_count=0)
        messages = [_system_blocks(True), Message(role="user", content="hi")]

        calls = []

        class _Response:
            status_code = 400
            text = "cache_control not supported"
            request = MagicMock()

            def raise_for_status(self):
                raise httpx.HTTPStatusError(
                    "400", request=self.request, response=self
                )

        async def failing_post(url, json=None, **kwargs):
            calls.append(json)
            if len(calls) == 1:
                return _Response()
            # Second attempt (without cache_control) succeeds.
            resp = MagicMock()
            resp.status_code = 200
            resp.json = AsyncMock(return_value={
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
            })
            return resp

        client = MagicMock()
        client.post = failing_post
        llm._get_client = AsyncMock(return_value=client)
        resp = await llm.chat(messages, tools=None, model="m")
        assert resp.content == "ok"
        assert len(calls) == 2
        assert "cache_control" not in str(calls[1])

    @pytest.mark.asyncio
    async def test_stream_cache_control_400_retry(self):
        """Streaming path also retries once without cache_control (finding M1)."""
        import httpx

        llm = _llm()
        llm.cache_plan = CachePlan(stable_system_block_count=1, stable_tool_count=0)
        messages = [_system_blocks(True), Message(role="user", content="hi")]

        attempts = {"n": 0}

        class _StreamCtx:
            def __init__(self, failing: bool):
                self._failing = failing

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def aiter_lines(self):
                if self._failing:
                    import types
                    resp = types.SimpleNamespace(status_code=400, request=MagicMock())
                    raise httpx.HTTPStatusError(
                        "400 cache_control unsupported", request=MagicMock(), response=resp
                    )
                yield "event: message_start"
                yield 'data: {"type":"message_start","message":{"id":"m","role":"assistant","content":[]}}'
                yield "event: content_block_start"
                yield 'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}'
                yield "event: content_block_delta"
                yield 'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ok"}}'
                yield "event: content_block_stop"
                yield 'data: {"type":"content_block_stop","index":0}'
                yield "event: message_delta"
                yield 'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":1}}'
                yield "event: message_stop"
                yield 'data: {"type":"message_stop"}'

        def fake_stream(method, url, **kwargs):
            attempts["n"] += 1
            return _StreamCtx(failing=(attempts["n"] == 1))

        client = MagicMock()
        client.stream = fake_stream
        llm._get_client = AsyncMock(return_value=client)

        events = [e async for e in llm.stream_chat(messages, tools=None, model="m")]
        assert any(e.type == "complete" for e in events)
        assert attempts["n"] == 2  # first failed, retried without cache_control


# ---------------------------------------------------------------------------
# OpenAI negative path (task 2.4)
# ---------------------------------------------------------------------------


class TestOpenAICacheControlAbsent:
    def test_openai_payload_never_has_cache_control(self):
        from agent.openai_llm import OpenAILLM

        llm = OpenAILLM(api_key="test")
        messages = [
            Message(role="system", content=[TextBlock(text="P0", cache=True)]),
            Message(role="user", content="hi"),
        ]
        # OpenAILLM has no supports_cache_control -> loop never sets a plan.
        assert not getattr(llm, "supports_cache_control", False)
        payload = llm._build_openai_messages(messages, model="gpt-4")
        assert "cache_control" not in str(payload)


# ---------------------------------------------------------------------------
# Loop seam: CachePlan computation + set_stable_tools wiring (tasks 2.2, 2.3)
# ---------------------------------------------------------------------------


class TestLoopCacheSeam:
    async def test_compute_cache_plan_selector_off(self):
        from agent.loop import AgentLoop

        loop = AgentLoop(llm=_llm(), tool_registry=ToolRegistry())
        messages = [_system_blocks(True, True, True), Message(role="user", content="hi")]
        plan = loop._compute_cache_plan(messages, tools=[_tool("Read")])
        assert plan.stable_system_block_count == 3
        assert plan.stable_tool_count == 0

    async def test_compute_cache_plan_with_preceding_system_block(self):
        """A non-cache system message before the injected blocks must not shift
        the breakpoint (grill finding L5)."""
        from agent.loop import AgentLoop

        loop = AgentLoop(llm=_llm(), tool_registry=ToolRegistry())
        messages = [
            Message(role="system", content="pre-existing base system"),
            _system_blocks(True, True, True),  # injected context at system index 1..3
            Message(role="user", content="hi"),
        ]
        plan = loop._compute_cache_plan(messages, tools=[_tool("Read")])
        # Last cache block is at absolute system index 3 -> breakpoint at 4.
        assert plan.stable_system_block_count == 4

    async def test_compute_cache_plan_selector_on(self):
        from agent.loop import AgentLoop

        registry = ToolRegistry()
        selector = ToolSelector(embedder=MagicMock(), top_k=5)
        selector.index_tool("Read", "read files")
        selector.index_tool("Edit", "edit files")
        selector.index_tool("WebSearch", "search web")
        selector.set_stable_tools(["Read", "Edit"])
        registry.set_selector(selector)
        loop = AgentLoop(llm=_llm(), tool_registry=registry)
        messages = [_system_blocks(True, True), Message(role="user", content="hi")]
        tools = [_tool("Read"), _tool("Edit"), _tool("WebSearch")]
        plan = loop._compute_cache_plan(messages, tools=tools)
        assert plan.stable_system_block_count == 0  # system breakpoint omitted
        assert plan.stable_tool_count == 2  # Read + Edit stable prefix

    async def test_set_stable_tools_wired_when_selector_present(self):
        from agent.loop import AgentLoop

        registry = ToolRegistry()
        selector = ToolSelector(embedder=MagicMock(), top_k=5)
        selector.index_tool("Read", "read files")
        registry.set_selector(selector)
        loop = AgentLoop(llm=_llm(), tool_registry=registry)
        loop._select_tool_schemas([Message(role="user", content="hi")])
        assert selector.is_stable("Read")
        assert selector.is_stable("Bash")
