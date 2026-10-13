# tests/web_tests/test_group_chat_server.py
"""群聊板块的 HTTP/WS 面（tasks 2.7 / 3.3 / 3.10）。

覆盖：人设/房间 REST CRUD 与级联、内部会话 hub 过滤（含**损坏快照**）、
`DELETE /api/sessions` 拒删内部会话、WS `reset` 拒改内部会话、
房间级 WS 的 `room_state` + 回合事件流 + `@` 点名。
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.config import AsterwyndConfig
from agent.llm import LLMResponse
from agent.session import SessionSnapshot, SessionStore
from tests.support.llm_harness import ScriptedLLM
from web.server import create_app


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
            for _ in range(12):
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

    def test_unknown_room_closes_the_socket(self, client):
        with client.websocket_connect("/ws/room/r-nope") as ws:
            assert ws.receive_json() == {"error": "unknown_room"}


def _mode():
    from agent.run_config import AgentMode

    return AgentMode.BUILD


def _next_event(ws, types, limit=20):
    for _ in range(limit):
        event = ws.receive_json()
        if event.get("type") in types:
            return event
    raise AssertionError(f"no event of {types} within {limit}")
