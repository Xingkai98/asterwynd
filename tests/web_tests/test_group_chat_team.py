# tests/web_tests/test_group_chat_team.py
"""Web 层群聊服务（tasks 2.1 / 2.3 / 2.4 / 2.5 / 2.6 / 2.8 / 2.9）。

覆盖：人设/房间 CRUD 与持久化、删除级联（会话底座 + 记忆 scope + 幂等重试 +
房间 id 复用不继承记忆）、会话分离负向断言、`SessionRunner` 四态契约（并发被拒
不复用陈旧文本）、记忆接线完整性、会话数上限排队 + 懒构造、跨人设共享面声明。
"""
import asyncio
from pathlib import Path

import pytest

from agent.config import AsterwyndConfig, TeamConfig
from agent.run_config import AgentMode
from agent.llm import LLMResponse
from agent.session import (
    KIND_PERSONA_CHAT,
    KIND_ROOM_MEMBER,
    is_internal_session_id,
    visible_sessions,
)
from agent.team import paths
from agent.team.memory_review import make_scope
from tests.support.llm_harness import ScriptedLLM
from web.session import SessionManager
from web.team import TeamService, WebSessionRunner


@pytest.fixture(autouse=True)
def _isolated_memory_base(tmp_path, monkeypatch):
    base = tmp_path / "home" / "projects"
    monkeypatch.setattr("agent.memory.persistent._MEMORY_DIR_BASE", base)
    return base


class _NoopReviewer:
    """默认 review 替身：不调模型、不改写任何记忆。

    测试里**必须**与真 reviewer 隔开：``LLMMemoryReviewer`` 会消耗同一个
    ``ScriptedLLM`` 的脚本响应，而脚本是给「对话」准备的——两者混用会让会话读到
    本该属于 review 的那一条（实测：``test_text_comes_from_this_run_only`` 的第二
    轮拿到了 ``default response``）。真正关心 review 的用例显式注入自己的替身。
    """

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []

    async def review(self, *, scope_label, new_content, existing):
        self.calls.append((scope_label, list(new_content)))
        return []


def _service(
    tmp_path: Path, llm=None, *, config=None, max_sessions=50, reviewer=None
) -> TeamService:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    config = config or AsterwyndConfig(team=TeamConfig(max_sessions=max_sessions))
    manager = SessionManager(config=config, workspace_root=workspace)
    return TeamService(
        manager=manager,
        llm=llm or ScriptedLLM(default_response=LLMResponse(content="好的")),
        config=config,
        reviewer=reviewer or _NoopReviewer(),
    )


def _make_personas(service, workspace, names=("甲", "乙")):
    return [
        service.create_persona(workspace, name=name, instructions=f"你是{name}")
        for name in names
    ]


class TestPersonaAndRoomCrud:
    def test_persona_crud_persists(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        persona = service.create_persona(ws, name="甲", instructions="只说实话", model="m1")
        assert service.list_personas(ws)[0].instructions == "只说实话"

        # 跨重启：新建一个 TeamService 读回
        other = TeamService(
            manager=SessionManager(config=service.config, workspace_root=ws),
            llm=service.llm, config=service.config,
        )
        loaded = other.list_personas(ws)[0]
        assert loaded.id == persona.id
        assert loaded.instructions == "只说实话"
        assert loaded.model == "m1"

    def test_room_crud_persists(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        a, b = _make_personas(service, ws)
        room = service.create_room(ws, name="研究组", members=[a.id, b.id], admin=a.id,
                                   notice="先说结论")
        loaded = service.get_room(ws, room.id)
        assert loaded.members == [a.id, b.id]
        assert loaded.admin == a.id
        assert loaded.notice == "先说结论"

    def test_room_admin_defaults_to_chief(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        chief = service.create_persona(ws, name="chief", main_bot=True)
        member = service.create_persona(ws, name="member")
        room = service.create_room(ws, name="r", members=[chief.id, member.id],
                                   created_by=chief.id)
        assert room.admin == chief.id

    def test_room_rejects_unknown_member(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        with pytest.raises(ValueError):
            service.create_room(ws, name="r", members=["nope"])


class TestDeleteCascade:
    @pytest.mark.asyncio
    async def test_delete_persona_cascades(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        a, b = _make_personas(service, ws)
        room = service.create_room(ws, name="r", members=[a.id, b.id], admin=a.id)

        chat_id = await service.ensure_persona_chat_session(ws, a.id)
        room_id = await service.team_for(ws).orchestrator._resolver.ensure_room_session(
            room.id, a.id
        )
        # 写一条记忆，确认级联会把它清掉
        scope = make_scope(ws, a.id, room.id)
        service.team_for(ws).review.memory_for(scope).save(
            type="project", name="alpha", description="d", body="b"
        )
        assert paths.persona_subtree(ws, a.id).exists()

        result = await service.delete_persona(ws, a.id)
        assert result["deleted"] is True

        assert [p.id for p in service.list_personas(ws)] == [b.id]
        assert service.team_for(ws).store.get_persona(a.id) is None
        assert service.manager.get_session(chat_id) is None
        assert service.manager.get_session(room_id) is None
        assert not paths.persona_subtree(ws, a.id).exists()
        # 房间记录里该成员也被移除
        assert a.id not in service.get_room(ws, room.id).members

    @pytest.mark.asyncio
    async def test_delete_persona_is_idempotent_and_leaves_no_orphan(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        room = service.create_room(ws, name="r", members=[a.id], admin=a.id)
        chat_id = await service.ensure_persona_chat_session(ws, a.id)

        # 模拟「第一次级联中断在删完会话底座之后」：底座已被删，roster 还在。
        service.manager.remove_session(chat_id, workspace=ws)
        assert service.team_for(ws).store.get_persona(a.id) is not None
        assert service.get_room(ws, room.id) is not None

        result = await service.delete_persona(ws, a.id)      # 重试
        assert result["deleted"] is True
        assert service.team_for(ws).store.get_persona(a.id) is None
        assert service.get_room(ws, room.id).members == []

        again = await service.delete_persona(ws, a.id)       # 幂等
        assert again["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_room_cascades(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        a, b = _make_personas(service, ws)
        room = service.create_room(ws, name="r", members=[a.id, b.id], admin=a.id)
        sid_a = await service.team_for(ws).orchestrator._resolver.ensure_room_session(
            room.id, a.id
        )
        scope = make_scope(ws, a.id, room.id)
        service.team_for(ws).review.memory_for(scope).save(
            type="project", name="alpha", description="d", body="b"
        )
        service.team_for(ws).orchestrator.log_for(room.id).append_user("hi")

        result = await service.delete_room(ws, room.id)
        assert result["deleted"] is True
        assert service.get_room(ws, room.id) is None
        assert service.manager.get_session(sid_a) is None
        assert not paths.persona_room_subtree(ws, a.id, room.id).exists()
        assert service.team_for(ws).orchestrator.log_for(room.id).entries() == []
        # 人设本身不被删除
        assert {p.id for p in service.list_personas(ws)} == {a.id, b.id}

    @pytest.mark.asyncio
    async def test_room_id_reuse_does_not_inherit_memory(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        room = service.create_room(ws, name="r", members=[a.id], admin=a.id)
        scope = make_scope(ws, a.id, room.id)
        service.team_for(ws).review.memory_for(scope).save(
            type="project", name="alpha", description="d", body="旧群的秘密"
        )
        await service.delete_room(ws, room.id)

        # 复用同一个 room id 重建
        rebuilt = service.create_room(ws, name="r2", members=[a.id], admin=a.id)
        rebuilt.id = room.id
        service.team_for(ws).store.save_room(rebuilt)
        new_scope = make_scope(ws, a.id, room.id)
        assert "旧群的秘密" not in service.team_for(ws).review.memory_for(new_scope).recall()


class TestSessionSeparation:
    @pytest.mark.asyncio
    async def test_chat_and_room_sessions_are_distinct(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        room = service.create_room(ws, name="r", members=[a.id], admin=a.id)
        chat_id = await service.ensure_persona_chat_session(ws, a.id)
        room_sid = await service.team_for(ws).orchestrator._resolver.ensure_room_session(
            room.id, a.id
        )
        assert chat_id != room_sid
        assert is_internal_session_id(chat_id) and is_internal_session_id(room_sid)

        chat_session = service.manager.get_session(chat_id)
        room_session = service.manager.get_session(room_sid)
        assert chat_session.session_id != room_session.session_id
        assert chat_session.messages is not room_session.messages
        assert chat_session.event_channel is not room_session.event_channel

    @pytest.mark.asyncio
    async def test_room_chatter_does_not_reach_the_single_chat(self, tmp_path):
        service = _service(tmp_path, ScriptedLLM(default_response=LLMResponse(content="群里的发言")))
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        room = service.create_room(ws, name="r", members=[a.id], admin=a.id)
        chat_id = await service.ensure_persona_chat_session(ws, a.id)

        await service.submit_room_message(ws, room.id, "大家好")
        chat_session = service.manager.get_session(chat_id)
        assert all("群里的发言" not in str(m.content) for m in chat_session.messages)

    @pytest.mark.asyncio
    async def test_single_chat_does_not_enter_the_room_log(self, tmp_path):
        service = _service(tmp_path, ScriptedLLM(default_response=LLMResponse(content="私聊内容")))
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        room = service.create_room(ws, name="r", members=[a.id], admin=a.id)
        chat_id = await service.ensure_persona_chat_session(ws, a.id)
        await service.manager.run_session(service.manager.get_session(chat_id), "私聊一句")

        timeline = service.room_timeline(ws, room.id)
        assert all("私聊内容" not in entry["text"] for entry in timeline)


class TestRunnerContract:
    @pytest.mark.asyncio
    async def test_text_comes_from_this_run_only(self, tmp_path):
        llm = ScriptedLLM([
            LLMResponse(content="第一次"),
            LLMResponse(content="第二次"),
        ])
        service = _service(tmp_path, llm)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        sid = await service.ensure_persona_chat_session(ws, a.id)
        runner = WebSessionRunner(service.manager)

        first = await runner.run(sid, "hi")
        second = await runner.run(sid, "hi again")
        assert first.status == "text" and first.text.strip() == "第一次"
        assert second.status == "text" and second.text.strip() == "第二次"

    @pytest.mark.asyncio
    async def test_concurrent_rejection_does_not_reuse_stale_text(self, tmp_path):
        service = _service(tmp_path, ScriptedLLM(default_response=LLMResponse(content="陈旧内容")))
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        sid = await service.ensure_persona_chat_session(ws, a.id)
        session = service.manager.get_session(sid)
        runner = WebSessionRunner(service.manager)

        await runner.run(sid, "第一次")               # 让 last_turn 有陈旧内容
        await session.run_lock.acquire()             # 模拟另一个 run 正在跑
        try:
            outcome = await runner.run(sid, "并发")
        finally:
            session.run_lock.release()
        assert outcome.status == "failed"
        assert outcome.code == "run_in_progress"
        assert outcome.text == "", "并发被拒时 SHALL NOT 复用陈旧文本"

    @pytest.mark.asyncio
    async def test_unknown_session_is_failed_not_raised(self, tmp_path):
        service = _service(tmp_path)
        runner = WebSessionRunner(service.manager)
        outcome = await runner.run("persona-missing", "hi")
        assert outcome.status == "failed" and outcome.code == "session_not_found"

    @pytest.mark.asyncio
    async def test_silent_marker_maps_to_silent(self, tmp_path):
        service = _service(tmp_path, ScriptedLLM(default_response=LLMResponse(content="[PASS]")))
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        sid = await service.ensure_persona_chat_session(ws, a.id)
        runner = WebSessionRunner(service.manager)
        outcome = await runner.run(sid, "hi", silent_marker="[PASS]")
        assert outcome.status == "silent"

    @pytest.mark.asyncio
    async def test_timeout_maps_to_timeout(self, tmp_path):
        class HangingLLM(ScriptedLLM):
            async def chat(self, messages, tools=None, model=None, **kwargs):
                await asyncio.sleep(5)
                return LLMResponse(content="late")

        service = _service(tmp_path, HangingLLM())
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        sid = await service.ensure_persona_chat_session(ws, a.id)
        runner = WebSessionRunner(service.manager)
        outcome = await runner.run(sid, "hi", timeout=0.05)
        assert outcome.status == "timeout"


class TestMemoryWiring:
    @pytest.mark.asyncio
    async def test_persona_session_has_dedup_judge_and_memory_config(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        sid = await service.ensure_persona_chat_session(ws, a.id)
        session = service.manager.get_session(sid)

        registry = session.agent.tool_registry
        save_tool = registry.get_tool("SaveMemory")
        assert save_tool._judge is not None, "缺 LLM 去重判官 = 与 CLI 不同策略的记忆"
        assert save_tool._memory is not None
        assert save_tool._memory.memory_dir == paths.persona_memory_dir(ws, a.id, None)
        assert save_tool._memory.label == "persona"
        assert registry.get_tool("RecallMemory")._memory is save_tool._memory
        assert registry.get_tool("SearchMemory")._memory is save_tool._memory

    @pytest.mark.asyncio
    async def test_room_member_memory_is_per_room_and_isolated(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        r1 = service.create_room(ws, name="r1", members=[a.id], admin=a.id)
        r2 = service.create_room(ws, name="r2", members=[a.id], admin=a.id)
        sid1 = await service.team_for(ws).orchestrator._resolver.ensure_room_session(r1.id, a.id)
        sid2 = await service.team_for(ws).orchestrator._resolver.ensure_room_session(r2.id, a.id)

        mem1 = service.manager.get_session(sid1).agent.tool_registry.get_tool("SaveMemory")._memory
        mem2 = service.manager.get_session(sid2).agent.tool_registry.get_tool("SaveMemory")._memory
        assert mem1.memory_dir != mem2.memory_dir
        mem1.save(type="project", name="alpha", description="d", body="群一秘密")
        assert "群一秘密" not in mem2.recall()

    @pytest.mark.asyncio
    async def test_memory_index_block_title_is_persona(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        scope = make_scope(ws, a.id, None)
        memory = service.team_for(ws).review.memory_for(scope)
        memory.save(type="project", name="alpha", description="d", body="b")
        assert "## Persona Memory" in (memory.load_summary() and "## Persona Memory" or "")
        assert memory.index_title == "## Persona Memory"


class TestNoticeInjection:
    @pytest.mark.asyncio
    async def test_notice_reaches_the_room_session_only(self, tmp_path):
        service = _service(tmp_path, ScriptedLLM(default_response=LLMResponse(content="知道了")))
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        room = service.create_room(ws, name="r", members=[a.id], admin=a.id,
                                   notice="先说结论，再说理由")
        chat_id = await service.ensure_persona_chat_session(ws, a.id)
        room_sid = await service.team_for(ws).orchestrator._resolver.ensure_room_session(
            room.id, a.id
        )

        await service.submit_room_message(ws, room.id, "开始")
        room_session = service.manager.get_session(room_sid)
        assert any("先说结论，再说理由" in str(m.content) for m in room_session.messages)

        # 单聊不经过群提示词构造，notice 不进单聊
        await service.manager.run_session(service.manager.get_session(chat_id), "聊聊")
        chat_session = service.manager.get_session(chat_id)
        assert all("先说结论，再说理由" not in str(m.content) for m in chat_session.messages)


class TestPersonaMode:
    """Decision 18：人设运行模式（默认 bypass，单聊与所有群内会话都用它）。"""

    def test_default_mode_is_bypass(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        persona = service.create_persona(ws, name="甲")
        assert persona.mode == "bypass"

    @pytest.mark.asyncio
    async def test_persona_chat_uses_the_persona_mode(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        persona = service.create_persona(ws, name="甲")
        sid = await service.ensure_persona_chat_session(ws, persona.id)
        loop = service.manager.get_session(sid).agent
        assert loop.run_config.mode is AgentMode.BYPASS

    @pytest.mark.asyncio
    async def test_room_member_uses_the_persona_mode(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        persona = service.create_persona(ws, name="甲", mode="read_only")
        room = service.create_room(ws, name="r", members=[persona.id], admin=persona.id)
        sid = await service.team_for(ws).orchestrator._resolver.ensure_room_session(
            room.id, persona.id
        )
        loop = service.manager.get_session(sid).agent
        assert loop.run_config.mode is AgentMode.READ_ONLY

    @pytest.mark.asyncio
    async def test_mode_change_applies_to_newly_constructed_sessions(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        persona = service.create_persona(ws, name="甲")
        sid = await service.ensure_persona_chat_session(ws, persona.id)
        assert service.manager.get_session(sid).agent.run_config.mode is AgentMode.BYPASS

        service.update_persona(ws, persona.id, mode="read_only")
        service.manager.unload_session(sid)                 # 模拟进程重启
        again = await service.ensure_persona_chat_session(ws, persona.id)
        assert again == sid
        assert service.manager.get_session(sid).agent.run_config.mode is AgentMode.READ_ONLY

    @pytest.mark.asyncio
    async def test_mode_change_beats_the_stale_snapshot_mode(self, tmp_path):
        """roster 是模式的事实来源：已跑过的会话（快照里存着旧模式）也要跟着改。"""
        service = _service(tmp_path, ScriptedLLM(default_response=LLMResponse(content="ok")))
        ws = service.team_for(None).workspace
        persona = service.create_persona(ws, name="甲")     # 默认 bypass
        sid = await service.ensure_persona_chat_session(ws, persona.id)
        await service.manager.run_session(service.manager.get_session(sid), "你好")
        store = service.manager._store_for(ws)
        assert store.load(sid).mode is AgentMode.BYPASS      # 快照已落盘

        service.update_persona(ws, persona.id, mode="plan")
        service.manager.unload_session(sid)
        await service.ensure_persona_chat_session(ws, persona.id)
        session = service.manager.get_session(sid)
        assert session.agent.run_config.mode is AgentMode.PLAN
        # resume 时 AgentLoop 会用快照 mode 覆盖 → 快照必须已被 roster 值规整
        assert session.resume_snapshot.mode is AgentMode.PLAN

    @pytest.mark.asyncio
    async def test_bypass_persona_is_not_blocked_by_approval(self, tmp_path):
        """Decision 18 的理由：bypass 下高风险工具不再被审批卡死。"""
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        persona = service.create_persona(ws, name="甲")
        room = service.create_room(ws, name="r", members=[persona.id], admin=persona.id)
        sid = await service.team_for(ws).orchestrator._resolver.ensure_room_session(
            room.id, persona.id
        )
        assert service.manager.get_session(sid).agent.run_config.mode is AgentMode.BYPASS


class TestReplyModeApi:
    @pytest.mark.asyncio
    async def test_create_room_reply_mode_persists(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        room = service.create_room(ws, name="r", members=[a.id], reply_mode="everyone")
        assert service.get_room(ws, room.id).reply_mode == "everyone"
        assert service.create_room(ws, name="r2", members=[a.id]).reply_mode == "admin"

    @pytest.mark.asyncio
    async def test_update_room_reply_mode(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        room = service.create_room(ws, name="r", members=[a.id])
        updated = service.update_room(ws, room.id, reply_mode="everyone")
        assert updated.reply_mode == "everyone"
        assert service.get_room(ws, room.id).reply_mode == "everyone"

    def test_invalid_reply_mode_rejected(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        with pytest.raises(ValueError):
            service.create_room(ws, name="r", members=[a.id], reply_mode="nope")
        room = service.create_room(ws, name="ok", members=[a.id])
        with pytest.raises(ValueError):
            service.update_room(ws, room.id, reply_mode="nope")

    def test_invalid_persona_mode_rejected(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        with pytest.raises(ValueError):
            service.create_persona(ws, name="甲", mode="nope")
        persona = service.create_persona(ws, name="乙")
        with pytest.raises(ValueError):
            service.update_persona(ws, persona.id, mode="nope")


class _RecordingReviewer:
    """记录 review 调用（scope + 输入），不真调模型。"""

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []

    async def review(self, *, scope_label, new_content, existing):
        self.calls.append((scope_label, list(new_content)))
        return []


class TestSingleChatReview:
    """I1/I3 回归：单聊回合必须**真的**排队 review（正确 scope）并消费缓冲。

    此前 `_attach_turn_listener` 把单聊的 `room_id=None` 传成 `""`，于是
    `MemoryScope.is_group`（`room_id is not None`）把空串判成群 ⇒ 伪 scope、`run_once`
    直接 dropped，而缓冲写的是**正确**的 chat scope ⇒ 那个文件永不被消费、无界增长。
    """

    @pytest.mark.asyncio
    async def test_single_chat_turn_triggers_review_on_the_chat_scope(self, tmp_path):
        reviewer = _RecordingReviewer()
        service = _service(
            tmp_path, ScriptedLLM(default_response=LLMResponse(content="好的呀")),
            reviewer=reviewer,
        )
        ws = service.team_for(None).workspace
        persona = service.create_persona(ws, name="甲")
        sid = await service.ensure_persona_chat_session(ws, persona.id)

        await service.manager.run_session(service.manager.get_session(sid), "请记住我爱喝咖啡")
        await service.team_for(ws).review.drain()

        assert [c[0] for c in reviewer.calls] == [f"persona:{persona.id}"], (
            "单聊回合必须在 persona/chat scope 上排 review"
        )

    @pytest.mark.asyncio
    async def test_single_chat_review_input_covers_both_sides(self, tmp_path):
        """I3：缓冲必须同时含用户消息与助手回复（与群 scope 的 `User:` 口径对称）。"""
        reviewer = _RecordingReviewer()
        service = _service(
            tmp_path, ScriptedLLM(default_response=LLMResponse(content="好的呀")),
            reviewer=reviewer,
        )
        ws = service.team_for(None).workspace
        persona = service.create_persona(ws, name="甲")
        sid = await service.ensure_persona_chat_session(ws, persona.id)

        await service.manager.run_session(service.manager.get_session(sid), "请记住我爱喝咖啡")
        await service.team_for(ws).review.drain()

        _, new_content = reviewer.calls[0]
        joined = "\n".join(new_content)
        assert "请记住我爱喝咖啡" in joined, "用户消息必须进入 review 输入"
        assert "好的呀" in joined, "助手回复必须进入 review 输入"

    @pytest.mark.asyncio
    async def test_single_chat_pending_buffer_is_consumed(self, tmp_path):
        """I1 的另一半：缓冲**不**再无界增长。"""
        reviewer = _RecordingReviewer()
        service = _service(
            tmp_path, ScriptedLLM(default_response=LLMResponse(content="好的呀")),
            reviewer=reviewer,
        )
        ws = service.team_for(None).workspace
        persona = service.create_persona(ws, name="甲")
        sid = await service.ensure_persona_chat_session(ws, persona.id)
        scope = make_scope(ws, persona.id)

        await service.manager.run_session(service.manager.get_session(sid), "第一句")
        await service.team_for(ws).review.drain()
        assert service.team_for(ws).review.read_pending(scope) == []

        await service.manager.run_session(service.manager.get_session(sid), "第二句")
        await service.team_for(ws).review.drain()
        assert service.team_for(ws).review.read_pending(scope) == []
        assert len(reviewer.calls) == 2
        assert "第二句" in "\n".join(reviewer.calls[1][1])

    @pytest.mark.asyncio
    async def test_group_review_is_not_double_triggered(self, tmp_path):
        """I6：群内会话的 review 只由编排器一条路径触发（不早于发言落日志）。"""
        reviewer = _RecordingReviewer()
        service = _service(
            tmp_path, ScriptedLLM(default_response=LLMResponse(content="群发言")),
            reviewer=reviewer,
        )
        ws = service.team_for(None).workspace
        persona = service.create_persona(ws, name="甲")
        room = service.create_room(ws, name="r", members=[persona.id], admin=persona.id)

        await service.submit_room_message(ws, room.id, "大家好")
        await service.team_for(ws).review.drain()

        room_calls = [c for c in reviewer.calls if c[0] == f"persona:{persona.id}:room:{room.id}"]
        assert len(room_calls) == 1
        # 触发时读到的是**本人刚发出的那条**（发言先落日志、review 后排队）
        assert "群发言" in "\n".join(room_calls[0][1])


class TestPendingDowngrade:
    @pytest.mark.asyncio
    async def test_room_member_has_no_ask_tool_and_fails_closed(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        room = service.create_room(ws, name="r", members=[a.id], admin=a.id)
        sid = await service.team_for(ws).orchestrator._resolver.ensure_room_session(
            room.id, a.id
        )
        session = service.manager.get_session(sid)
        registry = session.agent.tool_registry
        assert "AskUserQuestion" not in registry._tools
        from agent.approval import ApprovalDecisionStatus, ApprovalRequest

        response = await session.approval_handler.request_approval(ApprovalRequest(
            approval_id="x", tool_call_id="c", tool_name="Bash", mode="build",
            capability=[], risk="high", origin="test", reason="r",
            profile_name="build_default", redacted_args={}, args_summary="",
        ))
        assert response.status is ApprovalDecisionStatus.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_persona_chat_keeps_interactive_pending(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        sid = await service.ensure_persona_chat_session(ws, a.id)
        session = service.manager.get_session(sid)
        assert "AskUserQuestion" in session.agent.tool_registry._tools
        assert session.approval_handler.pending_approval_id is None


class TestSessionCapAndLaziness:
    @pytest.mark.asyncio
    async def test_sessions_are_created_lazily(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a, b) = _make_personas(service, ws)
        service.create_room(ws, name="r", members=[a.id, b.id], admin=a.id)
        # 只是定义了人设与房间：没有任何会话被构造
        assert service.manager._sessions == {}

    @pytest.mark.asyncio
    async def test_cap_queues_instead_of_rejecting(self, tmp_path):
        service = _service(tmp_path, max_sessions=1)
        ws = service.team_for(None).workspace
        (a, b) = _make_personas(service, ws)
        a_chat = await service.ensure_persona_chat_session(ws, a.id)
        session_a = service.manager.get_session(a_chat)
        await session_a.run_lock.acquire()          # 唯一的槽被占用

        pending = asyncio.create_task(service.ensure_persona_chat_session(ws, b.id))
        await asyncio.sleep(0.05)
        assert not pending.done(), "达上限时新建 SHALL 排队等待，SHALL NOT 拒绝"

        session_a.run_lock.release()
        b_chat = await asyncio.wait_for(pending, timeout=5)
        assert b_chat != a_chat
        assert service.manager.get_session(b_chat) is not None
        # 淘汰的是空闲的那个（a 的槽被回收，快照仍在盘上可恢复）
        assert service.manager.get_session(a_chat) is None

    @pytest.mark.asyncio
    async def test_evicted_session_restores_from_snapshot(self, tmp_path):
        service = _service(tmp_path, ScriptedLLM(default_response=LLMResponse(content="记住了")),
                           max_sessions=1)
        ws = service.team_for(None).workspace
        (a, b) = _make_personas(service, ws)
        a_chat = await service.ensure_persona_chat_session(ws, a.id)
        await service.manager.run_session(service.manager.get_session(a_chat), "你好")

        await service.ensure_persona_chat_session(ws, b.id)      # 触发淘汰
        assert service.manager.get_session(a_chat) is None

        again = await service.ensure_persona_chat_session(ws, a.id)
        assert again == a_chat
        restored = service.manager.get_session(a_chat)
        assert restored is not None
        assert restored.resume_snapshot is not None, "淘汰后应从快照恢复上下文"
        assert restored.agent.session_kind == KIND_PERSONA_CHAT


class TestSharedSurface:
    @pytest.mark.asyncio
    async def test_workflow_asset_library_is_shared_across_personas(self, tmp_path):
        """Decision 12：资产库是**声明过的**跨人设共享面，不是隔离缺陷。"""
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a, b) = _make_personas(service, ws)
        sid_a = await service.ensure_persona_chat_session(ws, a.id)
        sid_b = await service.ensure_persona_chat_session(ws, b.id)
        loop_a = service.manager.get_session(sid_a).agent
        loop_b = service.manager.get_session(sid_b).agent
        assert loop_a.include_workflow_asset_index is True
        assert loop_b.include_workflow_asset_index is True


class TestKindsAndHubVisibility:
    @pytest.mark.asyncio
    async def test_internal_sessions_carry_their_kind_in_the_snapshot(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        room = service.create_room(ws, name="r", members=[a.id], admin=a.id)
        chat_id = await service.ensure_persona_chat_session(ws, a.id)
        room_sid = await service.team_for(ws).orchestrator._resolver.ensure_room_session(
            room.id, a.id
        )
        for sid, _persona in ((chat_id, a),):
            await service.manager.run_session(service.manager.get_session(sid), "hi")
        await service.manager.run_session(service.manager.get_session(room_sid), "hi")

        store = service.manager._store_for(ws)
        assert store.load(chat_id).kind == KIND_PERSONA_CHAT
        assert store.load(room_sid).kind == KIND_ROOM_MEMBER
        assert visible_sessions(store.list_sessions()) == []


class TestConcurrentRuns:
    @pytest.mark.asyncio
    async def test_two_personas_run_concurrently(self, tmp_path):
        """多人设并发 run 与既有 ``run_lock`` 语义不冲突（不同 session）。"""
        service = _service(tmp_path, ScriptedLLM(default_response=LLMResponse(content="ok")))
        ws = service.team_for(None).workspace
        (a, b) = _make_personas(service, ws)
        sid_a = await service.ensure_persona_chat_session(ws, a.id)
        sid_b = await service.ensure_persona_chat_session(ws, b.id)
        runner = WebSessionRunner(service.manager)

        results = await asyncio.gather(
            runner.run(sid_a, "a"), runner.run(sid_b, "b"),
        )
        assert [r.status for r in results] == ["text", "text"]


class TestAdoptInternalSession:
    @pytest.mark.asyncio
    async def test_adopt_routes_through_team_factory(self, tmp_path):
        service = _service(tmp_path)
        ws = service.team_for(None).workspace
        (a,) = _make_personas(service, ws, names=("甲",))
        chat_id = await service.ensure_persona_chat_session(ws, a.id)
        service.manager.unload_session(chat_id)

        assert await service.adopt_internal_session(chat_id, ws) is True
        session = service.manager.get_session(chat_id)
        assert session is not None
        assert session.agent.tool_registry.get_tool("SaveMemory")._memory.label == "persona"

    @pytest.mark.asyncio
    async def test_adopt_returns_false_for_unknown(self, tmp_path):
        service = _service(tmp_path)
        assert await service.adopt_internal_session("persona-nope") is False
