# tests/web_tests/test_group_chat_server.py
"""群聊板块的 HTTP/WS 面（tasks 2.7 / 3.3 / 3.10）。

覆盖：人设/房间 REST CRUD 与级联、内部会话 hub 过滤（含**损坏快照**）、
`DELETE /api/sessions` 拒删内部会话、WS `reset` 拒改内部会话、
房间级 WS 的 `room_state` + 回合事件流 + `@` 点名。
"""
import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse, ToolCallDelta
from agent.session import SessionSnapshot, SessionStore
from tests.support.llm_harness import ScriptedLLM
from web.server import _discussion_snapshot, _room_handshake, create_app


@pytest.fixture
def app(tmp_path):
    llm = ScriptedLLM(default_response=LLMResponse(content="收到"))
    return create_app(llm, config=AsterwyndConfig(), workspace_root=tmp_path)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _create_persona(client, name="甲", **extra):
    payload = {"name": name, **extra}
    resp = client.post("/api/team/personas", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestTeamRest:
    def test_state_starts_empty(self, client):
        resp = client.get("/api/team")
        assert resp.status_code == 200
        body = resp.json()
        assert body["personas"] == [] and body["rooms"] == []

    def test_persona_crud(self, client):
        body = _create_persona(client, "甲", instructions="只说实话", main_bot=True)
        pid = body["persona"]["id"]
        assert body["main_bot_ids"] == [pid]

        updated = client.patch(f"/api/team/personas/{pid}", json={"name": "乙"}).json()
        assert updated["persona"]["name"] == "乙"

        deleted = client.request(
            "DELETE", f"/api/team/personas/{pid}", params={"workspace": str(client.app.state.session_manager.primary_workspace)}
        ).json()
        assert deleted["deleted"] is True
        assert deleted["personas"] == []

    def test_room_crud_and_timeline(self, client):
        a = _create_persona(client, "甲")["persona"]["id"]
        b = _create_persona(client, "乙")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "研究组", "members": [a, b], "admin": a, "notice": "先说结论",
        }).json()["room"]

        state = client.get(f"/api/team/rooms/{room['id']}/timeline").json()
        assert state["room"]["notice"] == "先说结论"
        assert {m["id"] for m in state["members"]} == {a, b}

        patched = client.patch(f"/api/team/rooms/{room['id']}", json={"name": "改个名"}).json()
        assert patched["room"]["name"] == "改个名"

    def test_persona_chat_entrypoint_returns_session(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        resp = client.get(f"/api/team/personas/{pid}/chat")
        assert resp.status_code == 200
        assert resp.json()["session_id"].startswith("persona-")

    def test_unknown_workspace_rejected(self, client):
        assert client.get("/api/team", params={"workspace": "/nope"}).status_code == 403

    def test_room_message_runs_a_round(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={"name": "r", "members": [pid], "admin": pid}).json()["room"]
        resp = client.post(f"/api/team/rooms/{room['id']}/messages", json={"content": "你好"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["termination"] == "completed"
        kinds = [e["kind"] for e in body["timeline"]]
        assert kinds[0] == "user"
        assert "post" in kinds


class TestModeRest:
    """Decision 18/19 的 REST 面：mode / reply_mode 的读写与拒绝。"""

    def test_persona_mode_defaults_to_bypass_and_roundtrips(self, client):
        body = _create_persona(client, "甲")
        pid = body["persona"]["id"]
        assert body["persona"]["mode"] == "bypass"

        updated = client.patch(f"/api/team/personas/{pid}", json={"mode": "read_only"})
        assert updated.status_code == 200
        assert updated.json()["persona"]["mode"] == "read_only"
        state = client.get("/api/team").json()
        assert state["personas"][0]["mode"] == "read_only"

    def test_room_reply_mode_defaults_to_admin_and_roundtrips(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        assert room["reply_mode"] == "admin"

        patched = client.patch(f"/api/team/rooms/{room['id']}", json={"reply_mode": "everyone"})
        assert patched.status_code == 200
        assert patched.json()["room"]["reply_mode"] == "everyone"

    def test_invalid_modes_rejected_with_400(self, client):
        assert client.post("/api/team/personas",
                           json={"name": "甲", "mode": "nope"}).status_code == 400
        pid = _create_persona(client, "乙")["persona"]["id"]
        assert client.patch(f"/api/team/personas/{pid}",
                            json={"mode": "nope"}).status_code == 400
        assert client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "reply_mode": "nope",
        }).status_code == 400

    def test_everyone_room_gives_every_member_a_turn(self, client):
        a = _create_persona(client, "甲")["persona"]["id"]
        b = _create_persona(client, "乙")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [a, b], "admin": a, "reply_mode": "everyone",
        }).json()["room"]
        body = client.post(f"/api/team/rooms/{room['id']}/messages",
                           json={"content": "大家好"}).json()
        speakers = [e["speaker"] for e in body["timeline"] if e["kind"] == "post"]
        assert speakers == [a, b]


class TestAdminClearingRest:
    """I4 回归（REST 层）：PATCH `admin: null` 必须清空房间 admin。"""

    def test_patch_admin_null_clears_it(self, client):
        a = _create_persona(client, "甲")["persona"]["id"]
        b = _create_persona(client, "乙")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [a, b], "admin": a,
        }).json()["room"]
        assert room["admin"] == a

        patched = client.patch(f"/api/team/rooms/{room['id']}", json={"admin": None})
        assert patched.status_code == 200
        assert patched.json()["room"]["admin"] is None
        assert client.get(f"/api/team/rooms/{room['id']}/timeline").json()["room"]["admin"] is None

    def test_patch_without_admin_keeps_it(self, client):
        a = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [a], "admin": a,
        }).json()["room"]
        patched = client.patch(f"/api/team/rooms/{room['id']}", json={"name": "r2"})
        assert patched.json()["room"]["admin"] == a


class TestInternalSessionProtection:
    def test_hub_hides_internal_sessions(self, client, tmp_path):
        pid = _create_persona(client, "甲")["persona"]["id"]
        session_id = client.get(f"/api/team/personas/{pid}/chat").json()["session_id"]
        ws = client.app.state.session_manager.primary_workspace

        # 普通会话
        normal_id = "normal-session"
        SessionStore(str(Path(ws) / ".asterwynd" / "sessions")).save(SessionSnapshot(
            schema_version="1.0", session_id=normal_id, created_at="", updated_at="",
            messages=[], mode=_mode(), todos=[], active_skills=[], run_id="", iteration=0,
        ))

        listed = client.get("/api/sessions").json()["sessions"]
        assert [s["session_id"] for s in listed] == [normal_id]
        assert session_id not in [s["session_id"] for s in listed]

    def test_hub_hides_damaged_internal_snapshot(self, client):
        """损坏快照的 session_id 取目录名——前缀判定照常成立，不泄漏。"""
        ws = client.app.state.session_manager.primary_workspace
        sessions_dir = Path(ws) / ".asterwynd" / "sessions"
        broken = sessions_dir / "persona-broken"
        broken.mkdir(parents=True)
        (broken / "snapshot.json").write_text("{not json", encoding="utf-8")
        (broken / "messages.json").write_text("[]", encoding="utf-8")

        listed = client.get("/api/sessions").json()["sessions"]
        assert listed == []

    def test_workspace_session_count_excludes_internal(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        client.get(f"/api/team/personas/{pid}/chat")
        # 新会话尚未 run、快照未落盘，计数为 0；关键是它不因内部会话而变
        entries = client.get("/api/workspaces").json()["workspaces"]
        primary = next(e for e in entries if e["is_primary"])
        assert primary["session_count"] == 0

    def test_delete_api_refuses_internal_session(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        session_id = client.get(f"/api/team/personas/{pid}/chat").json()["session_id"]
        ws = client.app.state.session_manager.primary_workspace
        resp = client.request(
            "DELETE", f"/api/sessions/{session_id}", params={"workspace": str(ws)}
        )
        assert resp.status_code == 403
        assert resp.json()["error"] == "internal_session_protected"
        # 底座仍在（可继续恢复）
        assert client.app.state.session_manager.get_session(session_id) is not None

    def test_ws_reset_refused_for_internal_session(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        session_id = client.get(f"/api/team/personas/{pid}/chat").json()["session_id"]
        with client.websocket_connect(f"/ws/{session_id}") as ws:
            ws.receive_json()                       # session_resumed / session_created
            ws.send_json({"type": "reset"})
            event = _next_event(ws, {"error"})
            assert event["data"]["code"] == "internal_session_protected"
        # roster 的稳定映射保持有效
        assert client.app.state.session_manager.get_session(session_id) is not None


class TestRoomWebSocket:
    def test_room_state_then_round_events(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]

        with client.websocket_connect(f"/ws/room/{room['id']}") as ws:
            state = ws.receive_json()
            assert state["type"] == "room_state"
            assert state["data"]["room"]["id"] == room["id"]
            assert [m["id"] for m in state["data"]["members"]] == [pid]

            ws.send_json({"type": "chat", "content": "大家好"})
            seen = []
            # 收到 round_ended 即停；64 只是防挂死的安全上限（新增 member_status 后
            # 一个回合的事件数会高于旧上限 12）。
            for _ in range(64):
                event = ws.receive_json()
                seen.append(event["type"])
                if event["type"] == "round_ended":
                    break
            assert "user_message" in seen
            assert "member_post" in seen
            assert "round_ended" in seen

    def test_room_state_replays_the_log(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        client.post(f"/api/team/rooms/{room['id']}/messages", json={"content": "先说话"})

        with client.websocket_connect(f"/ws/room/{room['id']}") as ws:
            state = ws.receive_json()
            texts = [e["text"] for e in state["data"]["timeline"]]
            assert "先说话" in texts

    def test_malformed_frame_does_not_kill_the_connection(self, client):
        """review I10：畸形帧 ≠ 断连——连接必须活着（否则实时输出整条丢失）。"""
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        with client.websocket_connect(f"/ws/room/{room['id']}") as ws:
            ws.receive_json()                       # room_state
            ws.send_text("this is not json")
            ws.send_text("{}")                      # 合法 JSON 但不是已知类型
            ws.send_text("[]")                      # 非对象帧
            ws.send_json({"type": "ping"})
            assert _next_event(ws, {"pong"})["type"] == "pong"
            ws.send_json({"type": "chat", "content": "还在吗"})
            assert "user_message" in _collect_types(ws, until="round_ended")

    def test_unknown_room_closes_the_socket(self, client):
        with client.websocket_connect("/ws/room/r-nope") as ws:
            assert ws.receive_json() == {"error": "unknown_room"}


class TestRoomStateStatusSnapshot:
    def test_room_state_has_status_fields_after_a_round(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        client.post(f"/api/team/rooms/{room['id']}/messages", json={"content": "你好"})

        with client.websocket_connect(f"/ws/room/{room['id']}") as ws:
            state = ws.receive_json()
            assert state["type"] == "room_state"
            data = state["data"]
            assert data["member_statuses"] == []
            assert data["round_active"] is False
            assert isinstance(data["status_seq"], int) and data["status_seq"] >= 1

    def test_reconnect_during_busy_round_sees_member_status(self, tmp_path):
        class SlowLLM(ScriptedLLM):
            async def chat(self, messages, tools=None, model="gpt-4"):
                await asyncio.sleep(2)
                return LLMResponse(content="慢回答")

        app = create_app(SlowLLM(), config=AsterwyndConfig(), workspace_root=tmp_path)
        with TestClient(app) as client:
            pid = _create_persona(client, "甲")["persona"]["id"]
            room = client.post("/api/team/rooms", json={
                "name": "r", "members": [pid], "admin": pid,
            }).json()["room"]
            with client.websocket_connect(f"/ws/room/{room['id']}") as ws1:
                ws1.send_json({"type": "chat", "content": "你好"})
                assert _next_event(ws1, {"member_speaking"})["type"] == "member_speaking"
                time.sleep(0.2)      # 让 before_iteration 把状态推到 thinking
                with client.websocket_connect(f"/ws/room/{room['id']}") as ws2:
                    state = ws2.receive_json()
                    assert state["type"] == "room_state"
                    statuses = state["data"]["member_statuses"]
                    assert state["data"]["round_active"] is True
                    assert len(statuses) == 1
                    assert statuses[0]["persona_id"] == pid
                    assert statuses[0]["phase"] in ("running", "thinking")
                    assert statuses[0]["tools"] == []
                    assert state["data"]["status_seq"] >= 1


class TestRoomHandshakeOrdering:
    @pytest.mark.asyncio
    async def test_snapshot_is_first_and_broadcast_waits_for_lock(self):
        lock = asyncio.Lock()
        sent: list[str] = []
        started = asyncio.Event()
        release = asyncio.Event()

        async def send(payload):
            async with lock:
                sent.append(payload["type"])

        async def send_raw(payload):
            sent.append(payload["type"])
            started.set()
            await release.wait()

        task = asyncio.create_task(_room_handshake(
            lock,
            build_payload=lambda: {"type": "room_state"},
            subscribe=lambda: "tok",
            send_raw=send_raw,
            unsubscribe=lambda token: None,
        ))
        await started.wait()
        broadcaster = asyncio.create_task(send({"type": "member_status"}))
        await asyncio.sleep(0)
        assert sent == ["room_state"], "广播必须等待首帧发送完成"
        release.set()
        assert await task == "tok"
        await broadcaster
        assert sent == ["room_state", "member_status"]

    @pytest.mark.asyncio
    async def test_handshake_failure_unsubscribes(self):
        lock = asyncio.Lock()
        removed: list[str] = []

        async def send_raw(payload):
            raise RuntimeError("gone")

        with pytest.raises(RuntimeError):
            await _room_handshake(
                lock,
                build_payload=lambda: {"type": "room_state"},
                subscribe=lambda: "tok",
                send_raw=send_raw,
                unsubscribe=removed.append,
            )
        assert removed == ["tok"]


class TestMemberStatusWebSocket:
    def test_scripted_tool_round_emits_tool_status(self, tmp_path):
        llm = ScriptedLLM([
            LLMResponse(
                content="先查一下",
                tool_calls=[ToolCallDelta(
                    id="c1", name="Bash", arguments='{"cmd": "echo hi"}',
                )],
                stop_reason="tool_calls",
            ),
            LLMResponse(content="完成", stop_reason="end_turn"),
        ], stream=True)
        app = create_app(llm, config=AsterwyndConfig(), workspace_root=tmp_path)
        with TestClient(app) as client:
            pid = _create_persona(client, "甲")["persona"]["id"]
            room = client.post("/api/team/rooms", json={
                "name": "r", "members": [pid], "admin": pid,
            }).json()["room"]
            with client.websocket_connect(f"/ws/room/{room['id']}") as ws:
                ws.receive_json()                    # room_state
                ws.send_json({"type": "chat", "content": "你好"})
                events = []
                for _ in range(64):
                    event = ws.receive_json()
                    events.append(event)
                    if event["type"] == "round_ended":
                        break
                assert events[-1]["type"] == "round_ended"
                statuses = [
                    status
                    for event in events if event["type"] == "member_status"
                    for status in event["data"]["statuses"]
                ]
                assert any(
                    status["phase"] == "tool" and status["tools"] == ["Bash"]
                    for status in statuses
                )
                assert any(event["type"] == "member_post" for event in events)

    def test_non_streaming_round_never_emits_typing(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        with client.websocket_connect(f"/ws/room/{room['id']}") as ws:
            ws.receive_json()
            ws.send_json({"type": "chat", "content": "你好"})
            events = []
            for _ in range(64):
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "round_ended":
                    break
            statuses = [
                status
                for event in events if event["type"] == "member_status"
                for status in event["data"]["statuses"]
            ]
            assert statuses, "至少应有 running/thinking 状态"
            assert all(status["phase"] != "typing" for status in statuses)

    def test_disconnect_cancels_round_and_notifies_other_tab(self, tmp_path):
        class SlowLLM(ScriptedLLM):
            async def chat(self, messages, tools=None, model="gpt-4"):
                await asyncio.sleep(2)
                return LLMResponse(content="慢回答")

        app = create_app(SlowLLM(), config=AsterwyndConfig(), workspace_root=tmp_path)
        with TestClient(app) as client:
            pid = _create_persona(client, "甲")["persona"]["id"]
            room = client.post("/api/team/rooms", json={
                "name": "r", "members": [pid], "admin": pid,
            }).json()["room"]
            with client.websocket_connect(f"/ws/room/{room['id']}") as watcher:
                watcher.receive_json()
                with client.websocket_connect(f"/ws/room/{room['id']}") as sender:
                    sender.receive_json()
                    sender.send_json({"type": "chat", "content": "你好"})
                    assert _next_event(sender, {"member_speaking"})["type"] == "member_speaking"
                # sender 断开 → 轮次被取消；另一标签页应收到 status-only teardown。
                ended = _next_event(watcher, {"round_ended"}, limit=64)
                assert ended["data"]["termination"] == "cancelled"
                assert isinstance(ended["data"]["status_seq"], int)


class TestGoldenPath:
    """tasks 5.3 的脚本化 golden path：建人设 → 建群 → @ 点名 → 单聊。"""

    def test_persona_room_mention_and_single_chat(self, client, app):
        chief = _create_persona(client, "Chief", instructions="你是主持人", main_bot=True)["persona"]["id"]
        member = _create_persona(client, "小王", instructions="你负责补充")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "讨论组", "members": [chief, member], "admin": chief,
            "notice": "先说结论",
        }).json()["room"]

        # @ 点名让非 admin 先发言
        resp = client.post(f"/api/team/rooms/{room['id']}/messages",
                           json={"content": "@小王 你的看法？"})
        assert resp.status_code == 200, resp.text
        posts = [e for e in resp.json()["timeline"] if e["kind"] == "post"]
        assert posts and posts[0]["speaker"] == member

        # 人设单聊：独立会话、可被 hub 之外的入口打开
        chat = client.get(f"/api/team/personas/{member}/chat").json()
        assert chat["session_id"].startswith("persona-")
        with client.websocket_connect(
            f"/ws/{chat['session_id']}?workspace={chat['workspace']}"
        ) as ws:
            first = ws.receive_json()
            assert first["type"] in {"session_resumed", "session_created"}
            ws.send_json({"type": "chat", "content": "单独聊聊"})
            seen = []
            for _ in range(40):
                event = ws.receive_json()
                seen.append(event["type"])
                if event["type"] == "done":
                    break
            assert "done" in seen

        # 单聊内容不出现在房间时间线里
        timeline = client.get(f"/api/team/rooms/{room['id']}/timeline").json()["timeline"]
        assert all("单独聊聊" not in e["text"] for e in timeline)


def _collect_types(ws, *, until, limit=20):
    seen = []
    for _ in range(limit):
        event = ws.receive_json()
        seen.append(event.get("type"))
        if event.get("type") == until:
            return seen
    raise AssertionError(f"no {until} within {limit} events: {seen}")


def _mode():
    from agent.run_config import AgentMode

    return AgentMode.BUILD


def _next_event(ws, types, limit=20):
    for _ in range(limit):
        event = ws.receive_json()
        if event.get("type") in types:
            return event
    raise AssertionError(f"no event of {types} within {limit}")


# ---------------------------------------------------------------------------
# change group-unlimited-discussion：讨论链的 HTTP/WS 面（tasks 1.4 / 2.4 / 2.5）
# ---------------------------------------------------------------------------


class _FakeRoomOrchestrator:
    """房间 WS / REST stop 的注入替身：覆盖 room_state 快照与停止委托。

    只实现 web 层用到的四个面（状态快照 / 轮次活跃 / 讨论链快照 / 停止），
    让 web 契约测试不依赖 agent 层讨论链实现是否已落地。
    """

    def __init__(
        self, *, stopping: bool = False, round_: int = 0, reason=None,
        active: bool = False,
    ) -> None:
        self.stopping = stopping
        self.round = round_
        self.reason = reason
        self.active = active
        self.stop_calls: list[str] = []

    def is_round_active(self, room_id):          # noqa: ANN001 - 测试替身
        return self.active

    def status_snapshot(self, room_id):          # noqa: ANN001
        return [], 0

    def discussion_snapshot(self, room_id):      # noqa: ANN001
        return {"round": self.round, "reason": self.reason}

    async def request_stop(self, room_id: str) -> bool:
        self.stop_calls.append(room_id)
        return self.stopping


def _inject_orchestrator(client, fake):
    ws = client.app.state.session_manager.primary_workspace
    client.app.state.team_service.team_for(ws).orchestrator = fake
    return ws


class TestDiscussionSnapshotAdapter:
    """`_discussion_snapshot`：编排器快照读取的容错适配（无 API 等价「无链」）。"""

    def test_missing_api_falls_back_to_no_chain(self):
        class Bare:
            pass

        assert _discussion_snapshot(Bare(), "r1") == {"round": 0, "reason": None}

    def test_accepts_dict_and_tuple_forms(self):
        class DictOrch:
            def discussion_snapshot(self, room_id):      # noqa: ANN001
                return {"round": 2, "reason": "converged"}

        class TupleOrch:
            def discussion_snapshot(self, room_id):      # noqa: ANN001
                return (3, "stopped")

        assert _discussion_snapshot(DictOrch(), "r") == {
            "round": 2, "reason": "converged",
        }
        assert _discussion_snapshot(TupleOrch(), "r") == {
            "round": 3, "reason": "stopped",
        }

    def test_unexpected_shape_falls_back_to_no_chain(self):
        class Weird:
            def discussion_snapshot(self, room_id):      # noqa: ANN001
                return "nope"

        assert _discussion_snapshot(Weird(), "r") == {"round": 0, "reason": None}


class TestDiscussionModeRest:
    """Decision 1：`discussion_mode` 的 REST 读写与三种非法组合。"""

    def test_room_payload_exposes_discussion_mode(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        assert room["discussion_mode"] == "single"
        assert client.get(
            f"/api/team/rooms/{room['id']}/timeline"
        ).json()["room"]["discussion_mode"] == "single"

    def test_create_rejects_invalid_discussion_mode(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        resp = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "discussion_mode": "nope",
        })
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_discussion_mode"

    def test_create_rejects_unlimited_without_everyone(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        resp = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "discussion_mode": "unlimited",
        })
        assert resp.status_code == 400
        assert resp.json()["error"] == "discussion_mode_requires_everyone"
        # 被拒绝的创建不落盘
        assert client.get("/api/team").json()["rooms"] == []

    def test_patch_rejects_invalid_discussion_mode(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        resp = client.patch(
            f"/api/team/rooms/{room['id']}", json={"discussion_mode": "nope"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_discussion_mode"

    def test_patch_persists_discussion_mode_and_rejects_reply_mode_conflict(self, client):
        a = _create_persona(client, "甲")["persona"]["id"]
        b = _create_persona(client, "乙")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [a, b], "admin": a, "reply_mode": "everyone",
        }).json()["room"]

        patched = client.patch(
            f"/api/team/rooms/{room['id']}", json={"discussion_mode": "unlimited"},
        )
        assert patched.status_code == 200
        assert patched.json()["room"]["discussion_mode"] == "unlimited"
        # 字段穿透：room_state/timeline 与 /api/team 的 rooms 都带它
        timeline = client.get(f"/api/team/rooms/{room['id']}/timeline").json()
        assert timeline["room"]["discussion_mode"] == "unlimited"
        state = client.get("/api/team").json()
        assert state["rooms"][0]["discussion_mode"] == "unlimited"

        # 只把 reply_mode 改成 admin（未同时给 single）→ 400，且两字段保持原值
        conflict = client.patch(
            f"/api/team/rooms/{room['id']}", json={"reply_mode": "admin"},
        )
        assert conflict.status_code == 400
        assert conflict.json()["error"] == "discussion_mode_requires_everyone"
        unchanged = client.get(f"/api/team/rooms/{room['id']}/timeline").json()
        assert unchanged["room"]["reply_mode"] == "everyone"
        assert unchanged["room"]["discussion_mode"] == "unlimited"


class TestDiscussionStopRest:
    """Decision 5：REST 停止端点（幂等 no-op / unknown_room / workspace 回落）。"""

    def test_unknown_room_returns_404(self, client):
        resp = client.post("/api/team/rooms/r-nope/discussion/stop", json={})
        assert resp.status_code == 404
        assert resp.json()["error"] == "unknown_room"

    def test_unknown_room_without_body_returns_404(self, client):
        """body 可选：前端 REST 降级可以不传 workspace（回落主 workspace）。"""
        resp = client.post("/api/team/rooms/r-nope/discussion/stop")
        assert resp.status_code == 404
        assert resp.json()["error"] == "unknown_room"

    def test_workspace_not_allowed_returns_403(self, client):
        resp = client.post(
            "/api/team/rooms/r-nope/discussion/stop", json={"workspace": "/nope"},
        )
        assert resp.status_code == 403
        assert resp.json()["error"] == "workspace_not_allowed"

    def test_stop_is_idempotent(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        fake = _FakeRoomOrchestrator(stopping=False)
        _inject_orchestrator(client, fake)

        first = client.post(f"/api/team/rooms/{room['id']}/discussion/stop", json={})
        second = client.post(f"/api/team/rooms/{room['id']}/discussion/stop", json={})
        expected = {"stopping": False, "room_id": room["id"]}
        assert first.status_code == 200 and first.json() == expected
        assert second.status_code == 200 and second.json() == expected
        # 幂等重试仍到达编排器（is_first 判重由编排器负责）
        assert fake.stop_calls == [room["id"], room["id"]]

    def test_stop_returns_stopping_true(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        fake = _FakeRoomOrchestrator(stopping=True)
        _inject_orchestrator(client, fake)

        resp = client.post(
            f"/api/team/rooms/{room['id']}/discussion/stop",
            json={"workspace": str(client.app.state.session_manager.primary_workspace)},
        )
        assert resp.status_code == 200
        assert resp.json() == {"stopping": True, "room_id": room["id"]}
        assert fake.stop_calls == [room["id"]]

    def test_stop_on_idle_room_is_real_orchestrator_noop(self, client):
        """真实编排器端到端：无活动链 → stopping False，重复请求仍幂等。"""
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        expected = {"stopping": False, "room_id": room["id"]}
        for _ in range(2):
            resp = client.post(
                f"/api/team/rooms/{room['id']}/discussion/stop", json={},
            )
            assert resp.status_code == 200
            assert resp.json() == expected

    def test_stop_falls_back_to_room_owner_workspace(self, client, tmp_path):
        """请求 workspace 里没有该房间 → 回落房间所属 workspace（与发消息同口径）。"""
        other = tmp_path / "other-ws"
        other.mkdir()
        client.app.state.session_manager.register_workspace(other)
        pid = _create_persona(client, "甲", workspace=str(other))["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
            "workspace": str(other),
        }).json()["room"]

        wrong_workspace = str(client.app.state.session_manager.primary_workspace)
        resp = client.post(
            f"/api/team/rooms/{room['id']}/discussion/stop",
            json={"workspace": wrong_workspace},
        )
        assert resp.status_code == 200
        assert resp.json() == {"stopping": False, "room_id": room["id"]}


class TestRoomStateDiscussionFields:
    """Decision 7：`room_state` 带 `discussion_round` / `discussion_reason`（无 `discussion_active`）。"""

    def test_room_state_has_discussion_fields_with_defaults(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        with client.websocket_connect(f"/ws/room/{room['id']}") as ws:
            state = ws.receive_json()
        assert state["type"] == "room_state"
        data = state["data"]
        assert data["room"]["discussion_mode"] == "single"
        assert data["discussion_round"] == 0
        assert data["discussion_reason"] is None
        # Decision 1：不新增 discussion_active（前端自行用 round_active 推导）
        assert "discussion_active" not in data

    def test_room_state_reads_live_snapshot(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        _inject_orchestrator(client, _FakeRoomOrchestrator(
            round_=2, reason="converged", active=True,
        ))
        with client.websocket_connect(f"/ws/room/{room['id']}") as ws:
            data = ws.receive_json()["data"]
        assert data["discussion_round"] == 2
        assert data["discussion_reason"] == "converged"
        assert data["round_active"] is True


class TestRoomStopDiscussionWebSocket:
    """Decision 5：房间 WS 消息 `{"type": "stop_discussion"}` 走 TeamService。"""

    def test_stop_discussion_message_delegates_to_service(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]
        fake = _FakeRoomOrchestrator(stopping=True)
        _inject_orchestrator(client, fake)

        with client.websocket_connect(f"/ws/room/{room['id']}") as ws:
            ws.receive_json()                       # room_state
            ws.send_json({"type": "stop_discussion"})
            # 接收循环顺序处理：pong 到达即说明 stop 已被处理（不新增 ack 契约）
            ws.send_json({"type": "ping"})
            assert _next_event(ws, {"pong"})["type"] == "pong"
        assert fake.stop_calls == [room["id"]]


class TestSingleModeEventFlowUnchanged:
    """Decision 3/7：`single` 房间事件流逐字段不变，负向断言零 `discussion_*`。"""

    def test_single_room_emits_no_discussion_events(self, client):
        pid = _create_persona(client, "甲")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [pid], "admin": pid,
        }).json()["room"]

        with client.websocket_connect(f"/ws/room/{room['id']}") as ws:
            ws.receive_json()                       # room_state
            ws.send_json({"type": "chat", "content": "你好"})
            events = []
            for _ in range(64):
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "round_ended":
                    break

        types = [event["type"] for event in events]
        assert not any(t.startswith("discussion_") for t in types)
        assert "system_entry" not in types
        ended = events[-1]
        assert ended["type"] == "round_ended"
        assert set(ended["data"]) == {"room_id", "termination", "limit", "status_seq"}
        assert ended["data"]["termination"] == "completed"


def test_unlimited_event_order_then_stopped(tmp_path):
    """决策 7 的事件顺序：discussion_started → member_* → stop_requested → round_ended(stopped) → discussion_ended(stopped)。"""
    class SlowLLM(ScriptedLLM):
        async def chat(self, messages, tools=None, model="gpt-4"):
            await asyncio.sleep(0.3)
            return LLMResponse(content="继续讨论")

    app = create_app(SlowLLM(), config=AsterwyndConfig(), workspace_root=tmp_path)
    with TestClient(app) as client:
        a = _create_persona(client, "甲")["persona"]["id"]
        b = _create_persona(client, "乙")["persona"]["id"]
        room = client.post("/api/team/rooms", json={
            "name": "r", "members": [a, b], "admin": a,
            "reply_mode": "everyone", "discussion_mode": "unlimited",
        }).json()["room"]
        assert room["discussion_mode"] == "unlimited"

        with client.websocket_connect(f"/ws/room/{room['id']}") as ws:
            state = ws.receive_json()
            assert state["type"] == "room_state"
            ws.send_json({"type": "chat", "content": "开始讨论"})
            events = []
            stop_sent = False
            for _ in range(200):
                event = ws.receive_json()
                events.append(event)
                if event["type"] == "member_speaking" and not stop_sent:
                    ws.send_json({"type": "stop_discussion"})
                    stop_sent = True
                if event["type"] == "discussion_ended":
                    break

    types = [event["type"] for event in events]
    assert stop_sent
    assert "member_speaking" in types
    assert "discussion_started" in types
    assert "discussion_stop_requested" in types
    assert "round_ended" in types
    assert "discussion_ended" in types
    i_started = types.index("discussion_started")
    i_member = types.index("member_speaking")
    i_stop = types.index("discussion_stop_requested")
    i_round = types.index("round_ended")
    i_ended = types.index("discussion_ended")
    assert i_started < i_member < i_stop < i_round < i_ended

    last_round_ended = [
        event for event in events if event["type"] == "round_ended"
    ][-1]
    assert last_round_ended["data"]["termination"] == "stopped"
    ended = events[-1]
    assert ended["type"] == "discussion_ended"
    assert ended["data"]["reason"] == "stopped"

    chain_ids = {
        event["data"]["chain_id"]
        for event in events
        if event["type"] in {
            "discussion_started", "discussion_stop_requested",
            "round_ended", "discussion_ended",
        }
    }
    assert len(chain_ids) == 1, f"同一条链的 chain_id 必须一致: {chain_ids}"
