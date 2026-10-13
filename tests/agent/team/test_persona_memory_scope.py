# tests/agent/team/test_persona_memory_scope.py
"""人设记忆 scope：落点、scope 取值、隔离与注入块标题（tasks 2.5 / 3.8）。

代码前提（Issue 36）：``PersistentMemory`` 的 ``memory_dir`` 恒由 ``project_root``
哈希推导（``agent/memory/persistent.py:183`` 是唯一赋值点），**传一个 scope 目录
进去只会被再 hash 成另一个顶层目录**——落点会跑到 ``personas/<id>/`` 子树之外，
级联删除永远删不到。故本 change 新增显式 ``memory_dir`` 入参。
"""
import pytest

from agent.memory.persistent import PersistentMemory
from agent.team.paths import (
    persona_memory_dir,
    persona_scope_string,
    persona_subtree,
    project_scope_base,
    project_scope_string,
)


@pytest.fixture(autouse=True)
def _isolated_memory_base(tmp_path, monkeypatch):
    base = tmp_path / "asterwynd-home" / "projects"
    monkeypatch.setattr("agent.memory.persistent._MEMORY_DIR_BASE", base)
    return base


class TestExplicitMemoryDir:
    def test_given_memory_dir_is_used_verbatim(self, tmp_path):
        target = tmp_path / "personas" / "p1" / "chat" / "memory"
        mem = PersistentMemory(tmp_path, memory_dir=target)
        assert mem.memory_dir == target

    def test_given_scope_is_used_verbatim(self, tmp_path):
        mem = PersistentMemory(
            tmp_path,
            memory_dir=tmp_path / "m",
            scope="<project>:persona:p1:room:r1",
        )
        assert mem.scope == "<project>:persona:p1:room:r1"

    def test_without_args_behaviour_is_unchanged(self, tmp_path):
        """零回归：两个新入参都是可选且 keyword-only。"""
        mem = PersistentMemory(tmp_path)
        assert mem.memory_dir.name == "memory"
        assert mem.memory_dir.parent.parent.name == "projects"
        # scope 仍由 project_root 的 scope-root 推导（本机 /tmp 本身是 git 仓库，
        # 故不能断言它等于 tmp_path——用同一个推导函数作参照）。
        assert mem.scope == project_scope_string(tmp_path)
        assert mem.label == "project"

    def test_writes_land_in_the_given_dir(self, tmp_path):
        target = tmp_path / "personas" / "p1" / "chat" / "memory"
        mem = PersistentMemory(tmp_path, memory_dir=target, scope="s")
        mem.save(type="project", name="alpha", description="d", body="b")
        assert (target / "alpha.md").is_file()


class TestPathLayout:
    def test_persona_dirs_are_siblings_of_project_memory(self, tmp_path):
        base = project_scope_base(tmp_path)
        chat_dir = persona_memory_dir(tmp_path, "p1")
        assert chat_dir == base / "personas" / "p1" / "chat" / "memory"
        # 同级（不是嵌在 <hash>/memory/ 内）——避免与项目记忆的 git add -A 形成嵌套仓库
        assert "memory" not in chat_dir.relative_to(base).parts[:-1]

    def test_room_scope_dir(self, tmp_path):
        base = project_scope_base(tmp_path)
        assert persona_memory_dir(tmp_path, "p1", "r1") == (
            base / "personas" / "p1" / "rooms" / "r1" / "memory"
        )

    def test_persona_subtree_covers_chat_and_all_rooms(self, tmp_path):
        subtree = persona_subtree(tmp_path, "p1")
        assert subtree in persona_memory_dir(tmp_path, "p1").parents
        assert subtree in persona_memory_dir(tmp_path, "p1", "r1").parents
        assert subtree in persona_memory_dir(tmp_path, "p1", "r2").parents

    def test_scope_strings(self, tmp_path):
        project = project_scope_string(tmp_path)
        assert persona_scope_string(tmp_path, "p1") == f"{project}:persona:p1"
        assert persona_scope_string(tmp_path, "p1", "r1") == (
            f"{project}:persona:p1:room:r1"
        )

    def test_scope_strings_differ_between_faces(self, tmp_path):
        assert persona_scope_string(tmp_path, "p1") != persona_scope_string(
            tmp_path, "p1", "r1"
        )
        assert persona_scope_string(tmp_path, "p1", "r1") != persona_scope_string(
            tmp_path, "p1", "r2"
        )


def _persona_store(root, persona_id, room_id=None) -> PersistentMemory:
    return PersistentMemory(
        root,
        memory_dir=persona_memory_dir(root, persona_id, room_id),
        scope=persona_scope_string(root, persona_id, room_id),
        label="persona",
    )


class TestIsolation:
    def test_personas_do_not_see_each_other(self, tmp_path):
        a = _persona_store(tmp_path, "p1")
        b = _persona_store(tmp_path, "p2")
        a.save(type="project", name="alpha", description="d", body="secret-a")
        assert "secret-a" not in b.recall()
        assert b.search("secret-a") == []

    def test_same_persona_chat_and_room_are_isolated(self, tmp_path):
        chat = _persona_store(tmp_path, "p1")
        room = _persona_store(tmp_path, "p1", "r1")
        chat.save(type="project", name="alpha", description="d", body="secret-chat")
        assert "secret-chat" not in room.recall()
        assert room.search("secret-chat") == []

    def test_same_persona_two_rooms_are_isolated(self, tmp_path):
        r1 = _persona_store(tmp_path, "p1", "r1")
        r2 = _persona_store(tmp_path, "p1", "r2")
        r1.save(type="project", name="alpha", description="d", body="secret-r1")
        assert r2.search("secret-r1") == []
        assert "secret-r1" in r1.recall()

    def test_persona_store_is_isolated_from_project_store(self, tmp_path):
        project = PersistentMemory(tmp_path)
        persona = _persona_store(tmp_path, "p1")
        project.save(type="project", name="alpha", description="d", body="proj-secret")
        assert persona.search("proj-secret") == []


class TestScopeFilterTolerance:
    """Issue 39：``SearchMemory`` 的 ``scope`` 参数在 persona scope 下不能变成静默假阴性。"""

    def test_project_scope_prefix_matches_persona_scope(self, tmp_path):
        persona = _persona_store(tmp_path, "p1", "r1")
        persona.save(type="project", name="alpha", description="d", body="hello world")
        hits = persona.search("hello world", scope=project_scope_string(tmp_path))
        assert len(hits) == 1

    def test_exact_scope_still_matches(self, tmp_path):
        persona = _persona_store(tmp_path, "p1", "r1")
        persona.save(type="project", name="alpha", description="d", body="hello world")
        scope = persona_scope_string(tmp_path, "p1", "r1")
        assert len(persona.search("hello world", scope=scope)) == 1
        assert "hello world" in persona.recall(scope=scope)

    def test_other_project_scope_is_still_rejected(self, tmp_path):
        persona = _persona_store(tmp_path, "p1")
        persona.save(type="project", name="alpha", description="d", body="hello world")
        assert persona.search("hello world", scope="/other/project") == []
        assert persona.recall(scope="/other/project") == "No memories found."


class TestInjectionTitle:
    def test_project_store_keeps_project_title(self, tmp_path):
        assert PersistentMemory(tmp_path).index_title == "## Project Memory"

    def test_persona_store_uses_persona_title(self, tmp_path):
        mem = _persona_store(tmp_path, "p1")
        assert mem.index_title == "## Persona Memory"

    @pytest.mark.asyncio
    async def test_memory_index_source_renders_persona_title(self, tmp_path):
        from agent.context.protocol import BuildContext
        from agent.context.sources import MemoryIndexSource
        from agent.run_config import AgentMode

        mem = _persona_store(tmp_path, "p1")
        mem.save(type="project", name="alpha", description="d", body="body")
        source = MemoryIndexSource(persistent_memory=mem)
        context = BuildContext(
            cwd=str(tmp_path), mode=AgentMode.BUILD,
            context_window=100_000, total_budget=10_000,
        )
        rendered = await source.render(context)
        assert rendered.startswith("## Persona Memory")

    async def test_memory_index_source_keeps_project_title_for_project_store(
        self, tmp_path
    ):
        from agent.context.protocol import BuildContext
        from agent.context.sources import MemoryIndexSource
        from agent.run_config import AgentMode

        mem = PersistentMemory(tmp_path)
        mem.save(type="project", name="alpha", description="d", body="body")
        source = MemoryIndexSource(persistent_memory=mem)
        context = BuildContext(
            cwd=str(tmp_path), mode=AgentMode.BUILD,
            context_window=100_000, total_budget=10_000,
        )
        assert (await source.render(context)).startswith("## Project Memory")
