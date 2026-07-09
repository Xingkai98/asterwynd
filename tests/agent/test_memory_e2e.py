# tests/agent/test_memory_e2e.py
"""End-to-end tests for persistent cross-session memory.

Simulates multi-turn conversations where the agent saves and recalls
memories through SaveMemory / RecallMemory tools, verifying the full
integration of PersistentMemory + AgentLoop + tool execution.
"""
import json
import pytest
from pathlib import Path

from agent.loop import AgentLoop
from agent.memory.persistent import PersistentMemory
from agent.message import Message
from agent.llm import LLMResponse, ToolCallDelta
from agent.tools.builtin.memory import SaveMemoryTool, RecallMemoryTool
from agent.tools.registry import ToolRegistry
from agent.hooks.manager import HookManager


@pytest.fixture
def persistent_memory(tmp_path, monkeypatch):
    """A PersistentMemory backed by a temp directory."""
    fake_base = tmp_path / "fake-claude" / "projects"
    monkeypatch.setattr(
        "agent.memory.persistent._MEMORY_DIR_BASE",
        fake_base,
    )
    return PersistentMemory(tmp_path)


@pytest.fixture
def registry_with_memory_tools(persistent_memory):
    """ToolRegistry with SaveMemory and RecallMemory registered."""
    registry = ToolRegistry()
    registry.register(SaveMemoryTool(memory=persistent_memory))
    registry.register(RecallMemoryTool(memory=persistent_memory))
    return registry


def _save_tool_call(name: str, mem_type: str, description: str, body: str) -> ToolCallDelta:
    arguments = json.dumps({
        "type": mem_type,
        "name": name,
        "description": description,
        "body": body,
    })
    return ToolCallDelta(id=f"save-{name}", name="SaveMemory", arguments=arguments)


def _recall_tool_call(call_id: str = "recall-1") -> ToolCallDelta:
    return ToolCallDelta(id=call_id, name="RecallMemory", arguments="{}")


def _recall_filtered_tool_call(mem_type: str) -> ToolCallDelta:
    return ToolCallDelta(
        id="recall-filtered",
        name="RecallMemory",
        arguments=json.dumps({"type": mem_type}),
    )


class MultiStepLLM:
    """LLM that returns responses from a predefined list, one per chat() call."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = responses
        self._idx = 0
        self.all_messages = []  # accumulate all messages seen

    async def chat(self, messages, tools=None, model="gpt-4") -> LLMResponse:
        self.all_messages.append(list(messages))
        if self._idx >= len(self._responses):
            return LLMResponse(content="done", stop_reason="end_turn")
        resp = self._responses[self._idx]
        self._idx += 1
        return resp


# ---------------------------------------------------------------------------
# Save-then-recall across two AgentLoop runs (simulating cross-session)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_memory_persists_across_agent_runs(
    persistent_memory, registry_with_memory_tools
):
    """Agent saves a memory in one run, then recalls it in a new run."""
    # ---- Run 1: Save a user memory ----
    save_llm = MultiStepLLM([
        LLMResponse(
            content=None,
            tool_calls=[
                _save_tool_call("user-role", "user", "role", "Backend engineer, prefers Go."),
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Memory saved.", stop_reason="end_turn"),
    ])

    loop1 = AgentLoop(
        llm=save_llm,
        tool_registry=registry_with_memory_tools,
        hooks=HookManager(),
        persistent_memory=persistent_memory,
    )

    result1 = await loop1.run([Message(role="user", content="Remember that I prefer Go.")])

    assert result1.stop_reason.value == "end_turn"
    assert len(result1.tool_calls_made) == 1
    assert result1.tool_calls_made[0].name == "SaveMemory"
    assert "saved" in (result1.tool_calls_made[0].result or "")

    # Verify file was written
    mem_file = persistent_memory.memory_dir / "user-role.md"
    assert mem_file.exists()
    content = mem_file.read_text()
    assert "Backend engineer, prefers Go." in content
    assert "type: user" in content

    # ---- Run 2: Recall all memories ----
    recall_llm = MultiStepLLM([
        LLMResponse(
            content=None,
            tool_calls=[_recall_tool_call()],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Here are your memories.", stop_reason="end_turn"),
    ])

    registry2 = ToolRegistry()
    registry2.register(SaveMemoryTool(memory=persistent_memory))
    registry2.register(RecallMemoryTool(memory=persistent_memory))

    loop2 = AgentLoop(
        llm=recall_llm,
        tool_registry=registry2,
        hooks=HookManager(),
        persistent_memory=persistent_memory,
    )

    result2 = await loop2.run([Message(role="user", content="What do you remember about me?")])

    assert result2.stop_reason.value == "end_turn"
    assert len(result2.tool_calls_made) == 1
    assert result2.tool_calls_made[0].name == "RecallMemory"

    recall_result = result2.tool_calls_made[0].result or ""
    assert "user-role" in recall_result
    assert "Backend engineer, prefers Go." in recall_result


# ---------------------------------------------------------------------------
# MEMORY.md index is injected into system messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_index_injected_in_system_messages(
    persistent_memory, registry_with_memory_tools
):
    """After saving a memory, the MEMORY.md index should appear in context."""
    # Pre-populate a memory
    persistent_memory.save("user", "my-role", "role desc", "I write Go and Python.")

    capture_llm = MultiStepLLM([
        LLMResponse(content="I see the memories.", stop_reason="end_turn"),
    ])

    loop = AgentLoop(
        llm=capture_llm,
        tool_registry=registry_with_memory_tools,
        hooks=HookManager(),
        persistent_memory=persistent_memory,
    )

    await loop.run([Message(role="user", content="What do you know?")])

    # The LLM should have received messages containing the memory index
    all_text = ""
    for batch in capture_llm.all_messages:
        for msg in batch:
            if msg.content:
                all_text += str(msg.content) + "\n"

    assert "## Project Memory" in all_text
    assert "my-role.md" in all_text
    # Full body text must NOT be injected — only the index is
    assert "I write Go and Python." not in all_text


# ---------------------------------------------------------------------------
# No injection when no memories exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_memory_index_when_no_memories(
    persistent_memory, registry_with_memory_tools
):
    """When no memories exist, no ## Project Memory block should be injected."""
    capture_llm = MultiStepLLM([
        LLMResponse(content="I don't know anything.", stop_reason="end_turn"),
    ])

    loop = AgentLoop(
        llm=capture_llm,
        tool_registry=registry_with_memory_tools,
        hooks=HookManager(),
        persistent_memory=persistent_memory,
    )

    await loop.run([Message(role="user", content="What do you know?")])

    all_text = ""
    for batch in capture_llm.all_messages:
        for msg in batch:
            if msg.content:
                all_text += str(msg.content) + "\n"

    assert "## Project Memory" not in all_text


# ---------------------------------------------------------------------------
# RecallMemory with type filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_memory_filters_by_type(
    persistent_memory, registry_with_memory_tools
):
    """Agent saves multiple memory types, then recalls only one type."""
    # ---- Run 1: Save user + project memories ----
    save_llm = MultiStepLLM([
        LLMResponse(
            content=None,
            tool_calls=[
                _save_tool_call("my-role", "user", "role", "Go engineer."),
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(
            content=None,
            tool_calls=[
                _save_tool_call("deadline", "project", "deadline", "Ship Friday."),
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Both saved.", stop_reason="end_turn"),
    ])

    loop1 = AgentLoop(
        llm=save_llm,
        tool_registry=registry_with_memory_tools,
        hooks=HookManager(),
        persistent_memory=persistent_memory,
    )

    await loop1.run([Message(role="user", content="Save two memories.")])

    # ---- Run 2: Recall only user type ----
    recall_llm = MultiStepLLM([
        LLMResponse(
            content=None,
            tool_calls=[_recall_filtered_tool_call("user")],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Here are user memories.", stop_reason="end_turn"),
    ])

    registry2 = ToolRegistry()
    registry2.register(SaveMemoryTool(memory=persistent_memory))
    registry2.register(RecallMemoryTool(memory=persistent_memory))

    loop2 = AgentLoop(
        llm=recall_llm,
        tool_registry=registry2,
        hooks=HookManager(),
        persistent_memory=persistent_memory,
    )

    result2 = await loop2.run([Message(role="user", content="Recall user memories.")])

    recall_result = result2.tool_calls_made[0].result or ""
    assert "Go engineer." in recall_result
    assert "Ship Friday." not in recall_result


# ---------------------------------------------------------------------------
# SaveMemory update (same name, new content)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_memory_update_persists_across_runs(
    persistent_memory, registry_with_memory_tools
):
    """Updating an existing memory by name should be reflected on next recall."""
    # ---- Run 1: Initial save ----
    save1_llm = MultiStepLLM([
        LLMResponse(
            content=None,
            tool_calls=[
                _save_tool_call("my-pref", "user", "prefs v1", "Likes dark mode."),
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Saved.", stop_reason="end_turn"),
    ])

    loop1 = AgentLoop(
        llm=save1_llm,
        tool_registry=registry_with_memory_tools,
        hooks=HookManager(),
        persistent_memory=persistent_memory,
    )
    await loop1.run([Message(role="user", content="Save preference.")])

    # ---- Run 2: Update same name ----
    save2_llm = MultiStepLLM([
        LLMResponse(
            content=None,
            tool_calls=[
                _save_tool_call("my-pref", "user", "prefs v2", "Likes light mode."),
            ],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Updated.", stop_reason="end_turn"),
    ])

    loop2 = AgentLoop(
        llm=save2_llm,
        tool_registry=registry_with_memory_tools,
        hooks=HookManager(),
        persistent_memory=persistent_memory,
    )
    await loop2.run([Message(role="user", content="Update preference.")])

    # ---- Run 3: Recall to verify update ----
    recall_llm = MultiStepLLM([
        LLMResponse(
            content=None,
            tool_calls=[_recall_tool_call()],
            stop_reason="tool_calls",
        ),
        LLMResponse(content="Here it is.", stop_reason="end_turn"),
    ])

    registry3 = ToolRegistry()
    registry3.register(SaveMemoryTool(memory=persistent_memory))
    registry3.register(RecallMemoryTool(memory=persistent_memory))

    loop3 = AgentLoop(
        llm=recall_llm,
        tool_registry=registry3,
        hooks=HookManager(),
        persistent_memory=persistent_memory,
    )
    result3 = await loop3.run([Message(role="user", content="Recall.")])

    recall_result = result3.tool_calls_made[0].result or ""
    assert "Likes light mode." in recall_result
    assert "Likes dark mode." not in recall_result
