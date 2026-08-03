# tests/agent/memory/test_reversibility.py
"""可逆写入回归测试（issue #99 / long-term-memory-reversibility）。

覆盖 tasks 4.1-4.9：pre-image 可恢复 / revert 两步 commit / 索引跟随 /
resolve_conflict / abort 写保护 / fresh repo 首次写 / load_entries 不受影响 /
内联 identity / 工具注册。
"""
import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from agent.memory.persistent import PersistentMemory


def _git_ok():
    return shutil.which("git") is not None


@pytest.fixture
def mem(tmp_path, monkeypatch):
    fake_base = tmp_path / "fake-claude" / "projects"
    monkeypatch.setattr("agent.memory.persistent._MEMORY_DIR_BASE", fake_base)
    return PersistentMemory(tmp_path)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _last_commit_hash(cwd: Path) -> str:
    proc = _git(cwd, "log", "-1", "--format=%H")
    return proc.stdout.strip()


def _log_msgs(cwd: Path) -> list[str]:
    proc = _git(cwd, "log", "--format=%s")
    return [l for l in proc.stdout.splitlines() if l.strip()]


def _log_patch(cwd: Path, name: str) -> str:
    return _git(cwd, "log", "-p", "--", f"{name}.md").stdout


class TestReversibleWrites:
    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_1_update_has_preimage(self, mem):
        """update 前旧 body 在 git 历史可恢复。"""
        mem.save("user", "role", "role", "Old body.")
        # 第二次 save 是覆盖，触发 commit-before-write 快照旧状态
        mem.save("user", "role", "role", "New body.")

        shown = _log_patch(mem.memory_dir, "role")
        assert "Old body." in shown

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_1_supplement_has_preimage(self, mem):
        """supplement 前旧 body 在 git 历史可恢复。"""
        from agent.memory.dedup import Judgment

        mem.save("user", "role", "role", "Original body.")
        result = mem.apply_judgment(
            type="user",
            name="incoming",
            description="incoming",
            body="Added detail.",
            judgment=Judgment(action="supplement", target_name="role", reason="adds detail"),
        )
        assert "supplemented" in result

        shown = _log_patch(mem.memory_dir, "role")
        assert "Original body." in shown

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_2_revert_restores_old_body(self, mem):
        """revert 后 body 回到旧版本，changelog 有 revert 事件。"""
        from agent.memory.git_backend import MemoryGitBackend

        mem.save("user", "role", "role", "Old body.")  # 首次写，无 commit
        mem.save("user", "role", "role", "New body.")  # 覆盖，commit-before-write
        old_commit = _last_commit_hash(mem.memory_dir)  # 该 commit 快照 Old body

        backend = MemoryGitBackend(mem)
        result = backend.revert("role", old_commit)

        content = (mem.memory_dir / "role.md").read_text()
        assert "Old body." in content
        assert "New body." not in content
        changelog = (mem.memory_dir / "changelog.md").read_text()
        assert "revert" in changelog

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_2_revert_two_step_commit_immediate(self, mem):
        """revert 两步 commit：revert 产物立即进历史（无需等下一次写）。"""
        from agent.memory.git_backend import MemoryGitBackend

        mem.save("user", "role", "role", "Old body.")
        mem.save("user", "role", "role", "New body.")
        old_commit = _last_commit_hash(mem.memory_dir)

        backend = MemoryGitBackend(mem)
        backend.revert("role", old_commit)

        # revert 后立即检查 git 历史：应有独立的 revert 记录，无需再触发写
        msgs = _log_msgs(mem.memory_dir)
        assert any("revert" in m for m in msgs)

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_7_revert_syncs_index(self, mem):
        """revert 后 MEMORY.md 索引行与正文 description 一致。"""
        from agent.memory.git_backend import MemoryGitBackend

        mem.save("user", "role", "role", "Old body.")  # description=role
        mem.save("user", "role", "new-description", "New body.")
        old_commit = _last_commit_hash(mem.memory_dir)

        backend = MemoryGitBackend(mem)
        backend.revert("role", old_commit)

        # 回退后 frontmatter 的 description 应是旧值
        content = (mem.memory_dir / "role.md").read_text()
        assert "description: role" in content
        # 索引行 description 跟随正文（与回退后 frontmatter 一致）
        index = (mem.memory_dir / "MEMORY.md").read_text()
        assert "role" in index
        entry = mem._load_entry_by_name("role")
        assert entry is not None and entry.description == "role"

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_6_load_entries_unaffected_by_git(self, mem):
        """git init 后 load_entries 结果与 init 前一致。"""
        mem.save("user", "role", "role", "Body.")
        before = mem.load_entries()
        mem._ensure_git()
        after = mem.load_entries()
        assert [e.name for e in before] == [e.name for e in after]
        assert all(not e.name.startswith(".") for e in after)


class TestGitAbort:
    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_4_git_failure_aborts_write(self, mem, monkeypatch):
        """commit 失败（git 真坏）时中止写入，旧内容保留。"""
        import agent.memory.persistent as mod

        mem.save("user", "role", "role", "Old body.")
        # 让下一次 commit 失败
        def _fail(*args, **kwargs):
            raise RuntimeError("git broken")

        monkeypatch.setattr(mod.PersistentMemory, "_git_commit", _fail)
        with pytest.raises(RuntimeError):
            mem.save("user", "role", "role", "New body.")
        # 旧内容保留
        content = (mem.memory_dir / "role.md").read_text()
        assert "Old body." in content

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_5_nothing_to_commit_first_write_continues(self, mem):
        """fresh repo 首次写：nothing to commit 不是失败，安全继续。"""
        result = mem.save("user", "role", "role", "First body.")
        assert "saved" in result
        content = (mem.memory_dir / "role.md").read_text()
        assert "First body." in content

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_8_inline_identity(self, mem, monkeypatch):
        """commit 用内联 -c identity，不依赖全局/仓库配置。"""
        monkeypatch.delenv("GIT_CONFIG_GLOBAL", raising=False)
        monkeypatch.delenv("GIT_CONFIG_SYSTEM", raising=False)
        mem.save("user", "role", "role", "Body.")
        # 触发一次覆盖写产生 commit
        mem.save("user", "role", "role", "Body v2.")
        proc = _git(mem.memory_dir, "log", "-1", "--format=%an")
        assert proc.stdout.strip() == "Asterwynd Memory"


class TestResolveConflict:
    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_3_resolve_clears_flags(self, mem):
        """resolve 后双方 conflict_with 清空 + changelog resolve 事件。"""
        from agent.memory.dedup import Judgment

        mem.save("user", "a", "a", "A body.")
        mem.save("user", "b", "b", "B body.")
        mem.apply_judgment(
            type="user", name="a", description="a", body="A body.",
            judgment=Judgment(action="conflict", target_name="b", reason="conflicts"),
        )
        # 双方应互打标记
        a = mem._load_entry_by_name("a")
        b = mem._load_entry_by_name("b")
        assert a is not None and "b" in a.conflict_with
        assert b is not None and "a" in b.conflict_with

        result = mem.resolve_conflict("a", "b", reason="resolved")
        assert "resolved" in result
        a2 = mem._load_entry_by_name("a")
        b2 = mem._load_entry_by_name("b")
        assert a2 is not None and a2.conflict_with == []
        assert b2 is not None and b2.conflict_with == []
        changelog = (mem.memory_dir / "changelog.md").read_text()
        assert "resolve" in changelog

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_3_resolve_archives_loser(self, mem):
        """resolve 时归档 loser。"""
        from agent.memory.dedup import Judgment

        mem.save("user", "a", "a", "A body.")
        mem.save("user", "b", "b", "B body.")
        mem.apply_judgment(
            type="user", name="a", description="a", body="A body.",
            judgment=Judgment(action="conflict", target_name="b", reason="conflicts"),
        )
        result = mem.resolve_conflict("a", "b", loser="b", archive=True, reason="b wins")
        assert "archived" in result or "resolved" in result
        assert not (mem.memory_dir / "b.md").exists()
        assert (mem.memory_dir / "archive" / "b.md").exists()

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_3_resolve_default_loser_archives_name_b(self, mem):
        """审阅 Round 1 Issue 1: archive=True 未传 loser 时默认归档 name_b。"""
        from agent.memory.dedup import Judgment

        mem.save("user", "a", "a", "A body.")
        mem.save("user", "b", "b", "B body.")
        mem.apply_judgment(
            type="user", name="a", description="a", body="A body.",
            judgment=Judgment(action="conflict", target_name="b", reason="conflicts"),
        )
        result = mem.resolve_conflict("a", "b", archive=True, reason="b loses")
        assert "archived" in result
        assert not (mem.memory_dir / "b.md").exists()
        assert (mem.memory_dir / "archive" / "b.md").exists()
        assert (mem.memory_dir / "a.md").exists()

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_3_resolve_same_name_rejected(self, mem):
        """审阅 Round 1 Issue 4: name_a == name_b 自解防护。"""
        mem.save("user", "a", "a", "A body.")
        result = mem.resolve_conflict("a", "a")
        assert "itself" in result

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_3_resolve_rejects_path_traversal_loser(self, mem):
        """审阅 Round 2 Issue 6: loser 路径穿越被拒，不写不删文件。"""
        from agent.memory.dedup import Judgment

        mem.save("user", "a", "a", "A body.")
        mem.save("user", "b", "b", "B body.")
        mem.apply_judgment(
            type="user", name="a", description="a", body="A body.",
            judgment=Judgment(action="conflict", target_name="b", reason="conflicts"),
        )
        result = mem.resolve_conflict("a", "b", loser="../../../victim", archive=True)
        assert "Error" in result
        # 未写入 memory_dir 外、未删除任何文件
        assert not (mem.memory_dir.parent / "victim.md").exists()
        assert (mem.memory_dir / "a.md").exists()
        assert (mem.memory_dir / "b.md").exists()
        assert not (mem.memory_dir / "archive" / "victim.md").exists()

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_3_resolve_rejects_third_party_loser(self, mem):
        """审阅 Round 2 Issue 6: loser 非 a/b 之一被拒，不误删无关记忆。"""
        from agent.memory.dedup import Judgment

        mem.save("user", "a", "a", "A body.")
        mem.save("user", "b", "b", "B body.")
        mem.save("user", "c", "c", "C body.")
        mem.apply_judgment(
            type="user", name="a", description="a", body="A body.",
            judgment=Judgment(action="conflict", target_name="b", reason="conflicts"),
        )
        result = mem.resolve_conflict("a", "b", loser="c", archive=True)
        assert "Error" in result
        # c 未被删除
        assert (mem.memory_dir / "c.md").exists()


class TestTools:
    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_9_resolve_memory_conflict_tool_registered(self, mem):
        """ResolveMemoryConflict 工具注册 + 调用。"""
        from agent.tools.builtin.memory import ResolveMemoryConflictTool
        from agent.memory.dedup import Judgment

        mem.save("user", "a", "a", "A body.")
        mem.save("user", "b", "b", "B body.")
        mem.apply_judgment(
            type="user", name="a", description="a", body="A body.",
            judgment=Judgment(action="conflict", target_name="b", reason="conflicts"),
        )

        tool = ResolveMemoryConflictTool(memory=mem)
        result = asyncio.run(tool.execute(name_a="a", name_b="b", reason="resolved"))
        assert "resolved" in result
        a = mem._load_entry_by_name("a")
        b = mem._load_entry_by_name("b")
        assert a is not None and a.conflict_with == []
        assert b is not None and b.conflict_with == []

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_9_memory_git_backend_tool_history(self, mem):
        """MemoryGitBackend 工具 history 调用。"""
        from agent.tools.builtin.memory import MemoryGitBackendTool

        mem.save("user", "role", "role", "Old body.")
        mem.save("user", "role", "role", "New body.")

        tool = MemoryGitBackendTool(memory=mem)
        result = asyncio.run(tool.execute(action="history", name="role"))
        assert "update" in result or "role" in result

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_9_memory_git_backend_tool_revert(self, mem):
        """MemoryGitBackend 工具 revert 调用。"""
        from agent.tools.builtin.memory import MemoryGitBackendTool

        mem.save("user", "role", "role", "Old body.")
        mem.save("user", "role", "role", "New body.")
        old_commit = _last_commit_hash(mem.memory_dir)

        tool = MemoryGitBackendTool(memory=mem)
        result = asyncio.run(tool.execute(action="revert", name="role", commit_a=old_commit))
        assert "reverted" in result
        content = (mem.memory_dir / "role.md").read_text()
        assert "Old body." in content

    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_4_9_git_backend_rejects_invalid_name(self, mem):
        """审阅 Round 1 Issue 2: MemoryGitBackend history/diff/revert 校验 name。"""
        from agent.memory.git_backend import MemoryGitBackend

        backend = MemoryGitBackend(mem)
        assert "Error" in backend.history("../escape")
        assert "Error" in backend.diff("../escape", "a", "b")
        assert "Error" in backend.revert("../escape", "abc1234")


class TestGitBackendConfig:
    @pytest.mark.skipif(not _git_ok(), reason="git not available")
    def test_3_2_git_backend_disabled_skips_tool(self, mem, tmp_path):
        """审阅 Round 1 Issue 3: git_backend_enabled=False 时 MemoryGitBackend 不注册，
        ResolveMemoryConflict 仍注册。"""
        from agent.config import MemoryConfig
        from agent.tools.factory import get_default_tools

        mem.memory_dir.mkdir(parents=True, exist_ok=True)

        # enabled=False → 无 MemoryGitBackend，有 ResolveMemoryConflict
        disabled_config = MemoryConfig(git_backend_enabled=False)
        tools_off = get_default_tools(persistent_memory=mem, memory_config=disabled_config)
        names_off = {t.name for t in tools_off}
        assert "MemoryGitBackend" not in names_off
        assert "ResolveMemoryConflict" in names_off

        # 默认 → 两者都有
        tools_on = get_default_tools(persistent_memory=mem, memory_config=MemoryConfig())
        names_on = {t.name for t in tools_on}
        assert "MemoryGitBackend" in names_on
        assert "ResolveMemoryConflict" in names_on
