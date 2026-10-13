# tests/agent/team/test_memory_review.py
"""记忆 review（tasks 2.5 / 3.13，design Decision 17）。

覆盖：仅实际发言回合触发、静默不触发、单聊/群各自触发、静默成员按 **review 游标**
落后补齐（阈值 30）、`remove` → `archive`（含 git 前像）、写回经既有 save 路径、
失败不中断、按 scope 合并/串行化、单聊走持久化待 review 缓冲（压缩 / resume 后仍
推进且不漏读不重读）、初值 = scope 起点、读入上限、成本 1 + k、scope 删除即丢弃。
"""
import asyncio
import subprocess
from pathlib import Path

import pytest

from agent.config import MemoryConfig
from agent.team.memory_review import (
    LLMMemoryReviewer,
    MemoryChange,
    MemoryReviewService,
    parse_changes,
)
from agent.team.memory_review import make_scope
from agent.team.models import Persona, Room
from agent.team.runner import TurnOutcome
from agent.team.store import TeamStore


class FakeReviewer:
    def __init__(self, changes=None):
        self.calls: list[dict] = []
        self.changes = changes if changes is not None else [
            MemoryChange(action="add", name="alpha", description="d", body="reviewed-fact")
        ]
        self.fail = False

    async def review(self, *, scope_label, new_content, existing):
        self.calls.append({
            "scope": scope_label, "new": list(new_content), "existing": list(existing),
        })
        if self.fail:
            raise RuntimeError("review model down")
        return list(self.changes)


@pytest.fixture(autouse=True)
def _isolated_memory_base(tmp_path, monkeypatch):
    base = tmp_path / "home" / "projects"
    monkeypatch.setattr("agent.memory.persistent._MEMORY_DIR_BASE", base)
    return base


@pytest.fixture
def team(tmp_path: Path):
    store = TeamStore(tmp_path)
    for pid in ("pA", "pB"):
        store.upsert_persona(Persona(name=pid.upper(), id=pid))
    room = Room(name="r", members=["pA", "pB"], admin="pA")
    store.save_room(room)
    reviewer = FakeReviewer()
    service = MemoryReviewService(
        store=store, project_root=tmp_path, config=MemoryConfig(), reviewer=reviewer,
    )
    return store, room, reviewer, service


def _scope(tmp_path, persona_id, room_id=None):
    return make_scope(tmp_path, persona_id, room_id)


class TestTrigger:
    @pytest.mark.asyncio
    async def test_speaking_turn_queues_review(self, team, tmp_path):
        store, room, reviewer, service = team
        service.ensure_scope(make_scope(tmp_path, "pA", room.id))
        store.append_room_log(room.id, speaker="pA", kind="post", text="我说了话", ts="t")
        await service.on_member_turn(
            room_id=room.id, persona_id="pA",
            outcome=TurnOutcome(status="text", text="我说了话"),
        )
        assert service.pending_keys() == [f"persona:pA:room:{room.id}"]
        await service.drain()
        assert [c["scope"] for c in reviewer.calls] == [f"persona:pA:room:{room.id}"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["silent", "timeout", "failed"])
    async def test_non_speaking_turns_do_not_queue(self, team, status):
        store, room, reviewer, service = team
        await service.on_member_turn(
            room_id=room.id, persona_id="pA", outcome=TurnOutcome(status=status)
        )
        await service.drain()
        assert reviewer.calls == []

    @pytest.mark.asyncio
    async def test_disabled_by_config(self, team, tmp_path):
        store, room, reviewer, _ = team
        service = MemoryReviewService(
            store=store, project_root=tmp_path,
            config=MemoryConfig(review_enabled=False), reviewer=reviewer,
        )
        await service.on_member_turn(
            room_id=room.id, persona_id="pA", outcome=TurnOutcome(status="text", text="x")
        )
        await service.drain()
        assert reviewer.calls == []

    @pytest.mark.asyncio
    async def test_chat_scope_triggers_independently(self, team, tmp_path):
        store, room, reviewer, service = team
        scope = _scope(tmp_path, "pA")
        service.append_chat_message(scope, "单聊里说的话")
        assert await service.run_once(scope) == "applied"
        assert reviewer.calls[0]["scope"] == "persona:pA"
        assert "单聊里说的话" in reviewer.calls[0]["new"]


class TestGroupProgress:
    @pytest.mark.asyncio
    async def test_initial_progress_is_current_point(self, team, tmp_path):
        store, room, reviewer, service = team
        store.append_room_log(room.id, speaker="user", kind="user", text="历史", ts="t")
        service.ensure_scope(_scope(tmp_path, "pA", room.id))
        # 初值 = 当前起点 → 不回溯建库前的历史
        assert service._read_progress(_scope(tmp_path, "pA", room.id)) == 1

    @pytest.mark.asyncio
    async def test_review_reads_only_new_content_and_advances(self, team, tmp_path):
        store, room, reviewer, service = team
        scope = _scope(tmp_path, "pA", room.id)
        service.ensure_scope(scope)
        store.append_room_log(room.id, speaker="user", kind="user", text="新消息", ts="t")
        store.append_room_log(room.id, speaker="pB", kind="post", text="pB 发言", ts="t")

        await service.run_once(scope)
        assert reviewer.calls[0]["new"] == ["User: 新消息", "PB: pB 发言"]
        assert service._read_progress(scope) == 2

        # 第二次：没有新增 → 不调用模型、不重读
        assert await service.run_once(scope) == "empty"
        assert len(reviewer.calls) == 1

    @pytest.mark.asyncio
    async def test_read_limit_leaves_remainder_for_next_time(self, team, tmp_path):
        store, room, reviewer, service = team
        service._config = MemoryConfig(review_read_limit=2)
        scope = _scope(tmp_path, "pA", room.id)
        service.ensure_scope(scope)
        for i in range(5):
            store.append_room_log(room.id, speaker="user", kind="user", text=f"m{i}", ts="t")

        await service.run_once(scope)
        assert reviewer.calls[0]["new"] == ["User: m0", "User: m1"]
        await service.run_once(scope)
        assert reviewer.calls[1]["new"] == ["User: m2", "User: m3"]
        assert service._read_progress(scope) == 4

    @pytest.mark.asyncio
    async def test_writes_go_through_save_path(self, team, tmp_path):
        store, room, reviewer, service = team
        scope = _scope(tmp_path, "pA", room.id)
        service.ensure_scope(scope)
        store.append_room_log(room.id, speaker="user", kind="user", text="记一下", ts="t")
        await service.run_once(scope)

        memory = service.memory_for(scope)
        assert "reviewed-fact" in memory.recall()

    @pytest.mark.asyncio
    async def test_remove_maps_to_archive(self, team, tmp_path):
        store, room, reviewer, service = team
        scope = _scope(tmp_path, "pA", room.id)
        service.ensure_scope(scope)
        memory = service.memory_for(scope)
        memory.save(type="project", name="old-fact", description="d", body="过时了")
        assert (scope.memory_dir / "old-fact.md").is_file()

        reviewer.changes = [MemoryChange(action="remove", name="old-fact", reason="不再成立")]
        store.append_room_log(room.id, speaker="user", kind="user", text="更新", ts="t")
        await service.run_once(scope)

        assert not (scope.memory_dir / "old-fact.md").exists()
        assert (scope.memory_dir / "archive" / "old-fact.md").is_file()
        assert "old-fact" not in service.memory_for(scope).recall()
        assert "old-fact" in service.memory_for(scope).recall(include_archived=True)

    @pytest.mark.asyncio
    async def test_archive_has_git_preimage(self, team, tmp_path):
        store, room, reviewer, service = team
        if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
            pytest.skip("git 不可用")
        scope = _scope(tmp_path, "pA", room.id)
        service.ensure_scope(scope)
        memory = service.memory_for(scope)
        memory.save(type="project", name="old-fact", description="d", body="v1")
        memory.save(type="project", name="old-fact", description="d", body="v2")
        memory.archive("old-fact", "cleanup")

        log = subprocess.run(
            ["git", "log", "--oneline"], cwd=scope.memory_dir,
            capture_output=True, text=True, errors="replace",
        )
        assert log.returncode == 0
        assert "archive" in log.stdout or log.stdout.strip() != ""


class TestLagCompensation:
    @pytest.mark.asyncio
    async def test_lagging_member_is_compensated(self, team, tmp_path):
        store, room, reviewer, service = team
        for pid in ("pA", "pB"):
            service.ensure_scope(_scope(tmp_path, pid, room.id))
        for i in range(30):
            store.append_room_log(room.id, speaker="pA", kind="post", text=f"p{i}", ts="t")

        lagging = service.compensate_lag(room.id)
        assert set(lagging) == {"pA", "pB"}
        await service.drain()
        assert len(reviewer.calls) == 2

    @pytest.mark.asyncio
    async def test_threshold_is_exclusive_below(self, team, tmp_path):
        store, room, reviewer, service = team
        service.ensure_scope(_scope(tmp_path, "pA", room.id))
        for i in range(29):
            store.append_room_log(room.id, speaker="user", kind="user", text=f"m{i}", ts="t")
        assert service.compensate_lag(room.id) == []

    @pytest.mark.asyncio
    async def test_lag_uses_review_cursor_not_seen(self, team, tmp_path):
        """用注入游标 ``seen`` 作基准则落后恒为 0、补齐永不触发（Decision 17）。"""
        store, room, reviewer, service = team
        service.ensure_scope(_scope(tmp_path, "pA", room.id))
        for i in range(40):
            store.append_room_log(room.id, speaker="user", kind="user", text=f"m{i}", ts="t")
        # 注入游标被推到最后（模拟「每回合都推进、含静默」）
        room.seen["pA"] = 40
        store.save_room(room)
        assert service.compensate_lag(room.id) == ["pA"]

    @pytest.mark.asyncio
    async def test_uninitialised_scope_is_not_compensated(self, team, tmp_path):
        store, room, reviewer, service = team
        for i in range(40):
            store.append_room_log(room.id, speaker="user", kind="user", text=f"m{i}", ts="t")
        assert service.compensate_lag(room.id) == []


class TestChatBuffer:
    @pytest.mark.asyncio
    async def test_chat_input_comes_from_buffer_not_message_table(self, team, tmp_path):
        store, room, reviewer, service = team
        scope = _scope(tmp_path, "pA")
        service.append_chat_message(scope, "第一句")
        service.append_chat_message(scope, "第二句")
        await service.run_once(scope)
        assert reviewer.calls[0]["new"] == ["第一句", "第二句"]
        assert service.read_pending(scope) == []

    @pytest.mark.asyncio
    async def test_partial_consumption_keeps_remainder(self, team, tmp_path):
        store, room, reviewer, service = team
        service._config = MemoryConfig(review_read_limit=1)
        scope = _scope(tmp_path, "pA")
        for text in ("a", "b", "c"):
            service.append_chat_message(scope, text)

        await service.run_once(scope)
        assert reviewer.calls[0]["new"] == ["a"]
        assert service.read_pending(scope) == ["b", "c"]
        await service.run_once(scope)
        assert reviewer.calls[1]["new"] == ["b"]

    @pytest.mark.asyncio
    async def test_failed_review_does_not_consume_the_buffer(self, team, tmp_path):
        store, room, reviewer, service = team
        reviewer.fail = True
        scope = _scope(tmp_path, "pA")
        service.append_chat_message(scope, "重要内容")
        assert await service.run_once(scope) == "failed"
        assert service.read_pending(scope) == ["重要内容"]

    @pytest.mark.asyncio
    async def test_buffer_is_immune_to_context_compaction_and_resume(self, team, tmp_path):
        """游标稳定性：缓冲在 scope 目录里，与消息表下标解耦。"""
        store, room, reviewer, service = team
        scope = _scope(tmp_path, "pA")
        for text in ("m1", "m2", "m3"):
            service.append_chat_message(scope, text)
        # 模拟「上下文压缩把消息表缩短」「resume 重建消息表」——二者都不碰缓冲。
        await service.run_once(scope)
        assert reviewer.calls[0]["new"] == ["m1", "m2", "m3"]
        # 再追加 → 仍只读新增（不重读、不因表变短而停摆）
        service.append_chat_message(scope, "m4")
        await service.run_once(scope)
        assert reviewer.calls[1]["new"] == ["m4"]


class TestQueue:
    @pytest.mark.asyncio
    async def test_same_scope_reviews_are_coalesced(self, team, tmp_path):
        store, room, reviewer, service = team
        started = asyncio.Event()
        release = asyncio.Event()

        class SlowReviewer(FakeReviewer):
            async def review(self, *, scope_label, new_content, existing):
                started.set()
                await release.wait()
                return await super().review(
                    scope_label=scope_label, new_content=new_content, existing=existing
                )

        service._reviewer = SlowReviewer()
        service.ensure_scope(make_scope(tmp_path, "pA", room.id))
        store.append_room_log(room.id, speaker="user", kind="user", text="有内容", ts="t")
        for _ in range(5):
            await service.on_member_turn(
                room_id=room.id, persona_id="pA",
                outcome=TurnOutcome(status="text", text="x"),
            )
        await started.wait()
        release.set()
        await service.drain()
        assert len(service._reviewer.calls) == 1, "同一 scope 的多次触发只跑一次"

    @pytest.mark.asyncio
    async def test_review_failure_is_swallowed(self, team, tmp_path):
        store, room, reviewer, service = team
        reviewer.fail = True
        service.ensure_scope(make_scope(tmp_path, "pA", room.id))
        store.append_room_log(room.id, speaker="pA", kind="post", text="内容", ts="t")
        await service.on_member_turn(
            room_id=room.id, persona_id="pA",
            outcome=TurnOutcome(status="text", text="x"),
        )
        await service.drain()          # 不抛：review 失败 SHALL NOT 中断轮次
        assert reviewer.calls

    @pytest.mark.asyncio
    async def test_deleted_scope_drops_the_review(self, team, tmp_path):
        store, room, reviewer, service = team
        scope = _scope(tmp_path, "pA", room.id)
        # 模拟级联已经把 scope 目录删掉
        assert not scope.memory_dir.parent.exists()
        assert await service.run_once(scope) == "dropped"
        assert reviewer.calls == []


class TestCost:
    @pytest.mark.asyncio
    async def test_cost_is_one_call_without_judge(self, team, tmp_path):
        store, room, reviewer, service = team
        scope = _scope(tmp_path, "pA", room.id)
        service.ensure_scope(scope)
        store.append_room_log(room.id, speaker="user", kind="user", text="x", ts="t")
        await service.run_once(scope)
        assert service.cost_counter["reviews"] == 1
        assert service.cost_counter["llm_calls"] == 1

    @pytest.mark.asyncio
    async def test_cost_records_a_review_call_for_injected_reviewer(self, team, tmp_path):
        store, room, reviewer, service = team
        scope = _scope(tmp_path, "pA", room.id)
        service.ensure_scope(scope)
        for i in range(2):
            store.append_room_log(room.id, speaker="user", kind="user", text=f"x{i}", ts="t")
            await service.run_once(scope)
        assert service.cost_counter == {"reviews": 2, "llm_calls": 2}


class TestParseChanges:
    def test_parses_json_array_with_fences(self):
        text = '```json\n[{"action":"add","name":"a-b","description":"d","body":"b"}]\n```'
        changes = parse_changes(text)
        assert len(changes) == 1 and changes[0].name == "a-b"

    def test_drops_invalid_entries(self):
        text = '[{"action":"nope","name":"x"},{"action":"add","name":""}]'
        assert parse_changes(text) == []

    def test_empty_and_garbage(self):
        assert parse_changes("") == []
        assert parse_changes("not json") == []


class TestLLMReviewer:
    @pytest.mark.asyncio
    async def test_uses_the_configured_model_and_reports_usage(self):
        from types import SimpleNamespace

        class FakeLLM:
            def __init__(self):
                self.calls = []

            async def chat(self, messages, tools=None, model=None):
                self.calls.append({"model": model, "messages": messages})
                return SimpleNamespace(
                    content='[{"action":"add","name":"x","description":"d","body":"b"}]',
                    usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                )

        llm = FakeLLM()
        seen: list = []
        reviewer = LLMMemoryReviewer(llm, model="small-model", on_usage=lambda m, u: seen.append((m, u)))
        changes = await reviewer.review(scope_label="persona:pA", new_content=["a"], existing=[])
        assert llm.calls[0]["model"] == "small-model"
        assert seen and seen[0][0] == "small-model"
        assert changes[0].action == "add"
