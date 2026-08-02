# tests/agent/tools/test_memory_tools.py
import pytest
from pathlib import Path

from agent.memory.dedup import Judgment
from agent.memory.persistent import PersistentMemory
from agent.tool_permissions import ToolCapability, ToolRiskLevel
from agent.tools.builtin.memory import SaveMemoryTool, RecallMemoryTool, SearchMemoryTool


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


# ---------------------------------------------------------------------------
# SearchMemory tool (#75)
# ---------------------------------------------------------------------------


class TestSearchMemoryTool:
    @pytest.fixture
    def mem(self, tmp_path, monkeypatch):
        fake_base = tmp_path / "fake-claude" / "projects"
        monkeypatch.setattr(
            "agent.memory.persistent._MEMORY_DIR_BASE",
            fake_base,
        )
        return PersistentMemory(tmp_path)

    def test_permission_is_agent_state_low(self):
        tool = SearchMemoryTool()
        perm = tool.get_permission()
        assert ToolCapability.AGENT_STATE in perm.capabilities
        assert perm.risk_level == ToolRiskLevel.LOW

    @pytest.mark.asyncio
    async def test_returns_no_memories_when_empty(self, mem):
        tool = SearchMemoryTool(memory=mem)
        result = await tool.execute(query="anything")
        assert "No memories" in result

    @pytest.mark.asyncio
    async def test_returns_matching_memories_with_score(self, mem):
        mem.save("feedback", "go-pref", "likes Go", "User prefers Go for backends.")
        mem.save("project", "release", "release date", "Ship in December.")

        tool = SearchMemoryTool(memory=mem)
        result = await tool.execute(query="prefers the Go language", top_k=5)
        assert "go-pref" in result
        assert "similarity=" in result
        assert "User prefers Go for backends." in result

    @pytest.mark.asyncio
    async def test_scope_mismatch_returns_nothing(self, mem):
        mem.save("project", "secret", "secret", "internal detail")
        tool = SearchMemoryTool(memory=mem)
        result = await tool.execute(query="secret", scope="/other/project")
        assert "No memories" in result

    @pytest.mark.asyncio
    async def test_type_filter(self, mem):
        mem.save("user", "role", "role", "backend engineer")
        mem.save("project", "deadline", "deadline", "backend release")
        tool = SearchMemoryTool(memory=mem)
        result = await tool.execute(query="backend", type="user")
        assert "role" in result
        assert "deadline" not in result


# ---------------------------------------------------------------------------
# SaveMemory write-time dedup semantics (#75)
# ---------------------------------------------------------------------------


class _StubJudge:
    """Returns a canned judgment, recording the incoming text it saw."""

    def __init__(self, judgment):
        self._judgment = judgment
        self.calls = []

    async def judge(self, incoming_text, candidates):
        self.calls.append((incoming_text, candidates))
        return self._judgment


class TestSaveMemoryToolDedup:
    @pytest.fixture
    def mem(self, tmp_path, monkeypatch):
        fake_base = tmp_path / "fake-claude" / "projects"
        monkeypatch.setattr(
            "agent.memory.persistent._MEMORY_DIR_BASE",
            fake_base,
        )
        return PersistentMemory(tmp_path)

    @pytest.mark.asyncio
    async def test_no_judge_falls_back_to_direct_save(self, mem):
        tool = SaveMemoryTool(memory=mem)
        result = await tool.execute(
            type="user", name="role", description="desc", body="body"
        )
        assert "saved" in result
        assert (mem.memory_dir / "role.md").exists()

    @pytest.mark.asyncio
    async def test_update_judgment_replaces_existing(self, mem):
        mem.save("user", "role", "v1", "Old content.")
        judge = _StubJudge(Judgment("update", target_name="role", reason="supersedes"))
        tool = SaveMemoryTool(memory=mem, judge=judge)
        result = await tool.execute(
            type="user", name="incoming", description="v2", body="New content."
        )
        assert "updated (dedup)" in result
        entry = mem._load_entry_by_name("role")
        assert entry.body == "New content."
        # no separate file for the incoming name
        assert mem._load_entry_by_name("incoming") is None
        # judge saw candidates
        assert judge.calls and judge.calls[0][1]

    @pytest.mark.asyncio
    async def test_supplement_judgment_appends(self, mem):
        mem.save("feedback", "prefs", "prefs", "Likes Go.")
        judge = _StubJudge(Judgment("supplement", target_name="prefs", reason="adds detail"))
        tool = SaveMemoryTool(memory=mem, judge=judge)
        result = await tool.execute(
            type="feedback", name="incoming", description="prefs", body="Also likes Python."
        )
        assert "supplemented" in result
        entry = mem._load_entry_by_name("prefs")
        assert "Likes Go." in entry.body
        assert "Also likes Python." in entry.body

    @pytest.mark.asyncio
    async def test_conflict_judgment_keeps_both(self, mem):
        mem.save("project", "deadline-a", "release", "August.")
        judge = _StubJudge(Judgment("conflict", target_name="deadline-a", reason="contradicts"))
        tool = SaveMemoryTool(memory=mem, judge=judge)
        result = await tool.execute(
            type="project", name="deadline-b", description="release", body="December."
        )
        assert "conflict marked" in result
        a = mem._load_entry_by_name("deadline-a")
        b = mem._load_entry_by_name("deadline-b")
        assert b is not None
        assert "deadline-b" in a.conflict_with
        assert "deadline-a" in b.conflict_with

    @pytest.mark.asyncio
    async def test_importance_param_accepted(self, mem):
        tool = SaveMemoryTool(memory=mem)
        result = await tool.execute(
            type="project", name="deadline", description="d", body="Ship Friday.", importance=5
        )
        assert "saved" in result
        assert mem._load_entry_by_name("deadline").importance == 5
