# tests/agent/tools/test_memory_tools.py
import pytest
from pathlib import Path

from agent.memory.persistent import PersistentMemory
from agent.tool_permissions import ToolCapability, ToolRiskLevel
from agent.tools.builtin.memory import SaveMemoryTool, RecallMemoryTool


class TestSaveMemoryTool:
    @pytest.fixture
    def mem(self, tmp_path, monkeypatch):
        fake_base = tmp_path / "fake-claude" / "projects"
        monkeypatch.setattr(
            "agent.memory.persistent._MEMORY_DIR_BASE",
            fake_base,
        )
        return PersistentMemory(tmp_path)

    def test_permission_is_agent_state_medium(self):
        tool = SaveMemoryTool()
        perm = tool.get_permission()
        assert ToolCapability.AGENT_STATE in perm.capabilities
        assert perm.risk_level == ToolRiskLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_creates_user_memory(self, mem):
        tool = SaveMemoryTool(memory=mem)
        result = await tool.execute(
            type="user", name="my-role", description="role desc", body="I write Go."
        )
        assert "saved" in result
        assert (mem.memory_dir / "my-role.md").exists()

    @pytest.mark.asyncio
    async def test_creates_feedback_memory(self, mem):
        tool = SaveMemoryTool(memory=mem)
        await tool.execute(
            type="feedback", name="testing-rules", description="rules", body="Use real DB."
        )
        assert (mem.memory_dir / "testing-rules.md").exists()

    @pytest.mark.asyncio
    async def test_creates_project_memory(self, mem):
        tool = SaveMemoryTool(memory=mem)
        await tool.execute(
            type="project", name="deadline", description="deadline", body="Ship Friday."
        )
        assert (mem.memory_dir / "deadline.md").exists()

    @pytest.mark.asyncio
    async def test_creates_reference_memory(self, mem):
        tool = SaveMemoryTool(memory=mem)
        await tool.execute(
            type="reference", name="grafana", description="dash", body="URL: grafana.internal"
        )
        assert (mem.memory_dir / "grafana.md").exists()

    @pytest.mark.asyncio
    async def test_updates_existing_memory(self, mem):
        tool = SaveMemoryTool(memory=mem)
        await tool.execute(
            type="user", name="my-role", description="v1", body="Old."
        )
        result = await tool.execute(
            type="user", name="my-role", description="v2", body="New."
        )
        assert "updated" in result
        content = (mem.memory_dir / "my-role.md").read_text()
        assert "New." in content

    @pytest.mark.asyncio
    async def test_rejects_invalid_name(self, mem):
        tool = SaveMemoryTool(memory=mem)
        result = await tool.execute(
            type="user", name="Bad Name", description="desc", body="body"
        )
        assert "Error" in result


class TestRecallMemoryTool:
    @pytest.fixture
    def mem(self, tmp_path, monkeypatch):
        fake_base = tmp_path / "fake-claude" / "projects"
        monkeypatch.setattr(
            "agent.memory.persistent._MEMORY_DIR_BASE",
            fake_base,
        )
        return PersistentMemory(tmp_path)

    def test_permission_is_agent_state_low(self):
        tool = RecallMemoryTool()
        perm = tool.get_permission()
        assert ToolCapability.AGENT_STATE in perm.capabilities
        assert perm.risk_level == ToolRiskLevel.LOW

    @pytest.mark.asyncio
    async def test_returns_no_memories_when_empty(self, mem):
        tool = RecallMemoryTool(memory=mem)
        result = await tool.execute()
        assert "No memories" in result

    @pytest.mark.asyncio
    async def test_returns_all_memories_when_no_type(self, mem):
        mem.save("user", "role", "role", "Backend engineer.")
        mem.save("project", "milestone", "milestone", "Q3 release.")

        tool = RecallMemoryTool(memory=mem)
        result = await tool.execute()
        assert "Backend engineer." in result
        assert "Q3 release." in result

    @pytest.mark.asyncio
    async def test_filters_by_type(self, mem):
        mem.save("user", "role", "role", "Backend engineer.")
        mem.save("project", "milestone", "milestone", "Q3 release.")

        tool = RecallMemoryTool(memory=mem)
        result = await tool.execute(type="user")
        assert "Backend engineer." in result
        assert "Q3 release." not in result

    @pytest.mark.asyncio
    async def test_no_results_for_unmatched_type(self, mem):
        mem.save("user", "role", "role", "Backend engineer.")
        tool = RecallMemoryTool(memory=mem)
        result = await tool.execute(type="project")
        assert "No memories of type 'project'" in result
