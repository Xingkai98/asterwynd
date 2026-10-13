# tests/agent/team/test_internal_session_ids.py
"""内部会话（人设单聊 / 群内会话）的标识与快照 kind（tasks 2.7 / 3.3）。

判定必须退化为**纯字符串**（id 前缀），不依赖读会话快照——``list_sessions()`` 的
damaged 分支只回目录名，读不出 ``kind``；若依赖快照，内部会话在快照损坏时会漏进
hub 列表（spec delta 的「内部会话不出现且损坏也不泄漏」）。
"""
from agent.run_identity import new_session_id
from agent.session import (
    KIND_CHAT,
    KIND_PERSONA_CHAT,
    KIND_ROOM_MEMBER,
    SessionSnapshot,
    is_internal_session_id,
    new_internal_session_id,
    visible_sessions,
)


class TestInternalSessionId:
    def test_prefixes(self):
        assert is_internal_session_id(new_internal_session_id(KIND_PERSONA_CHAT))
        assert is_internal_session_id(new_internal_session_id(KIND_ROOM_MEMBER))
        assert not is_internal_session_id(new_session_id())

    def test_persona_and_room_prefixes_are_distinct(self):
        persona = new_internal_session_id(KIND_PERSONA_CHAT)
        room = new_internal_session_id(KIND_ROOM_MEMBER)
        assert persona.startswith("persona-")
        assert room.startswith("room-")

    def test_ids_are_unique(self):
        ids = {new_internal_session_id(KIND_PERSONA_CHAT) for _ in range(50)}
        assert len(ids) == 50

    def test_unknown_kind_rejected(self):
        try:
            new_internal_session_id("chat")
        except ValueError:
            return
        raise AssertionError("只允许创建内部会话 kind")

    def test_ids_survive_the_session_store_validator(self, tmp_path):
        from agent.session import SessionStore

        store = SessionStore(str(tmp_path))
        sid = new_internal_session_id(KIND_ROOM_MEMBER)
        store._validate_session_id(sid, str(tmp_path))   # 不抛


class TestVisibleSessions:
    def test_filters_internal_entries(self):
        sessions = [
            {"session_id": "abc123"},
            {"session_id": "persona-deadbeef"},
            {"session_id": "room-cafebabe"},
        ]
        assert [s["session_id"] for s in visible_sessions(sessions)] == ["abc123"]

    def test_damaged_entries_filtered_by_directory_name(self):
        """损坏快照的 session_id 取目录名——前缀判定照样成立。"""
        sessions = [
            {"session_id": "persona-deadbeef", "damaged": True, "reason": "boom"},
            {"session_id": "plain", "damaged": True, "reason": "boom"},
        ]
        assert [s["session_id"] for s in visible_sessions(sessions)] == ["plain"]


class TestSnapshotKind:
    def test_default_kind_is_chat(self):
        snapshot = SessionSnapshot(
            schema_version="1.0", session_id="s", created_at="", updated_at="",
            messages=[], mode=_mode(), todos=[], active_skills=[], run_id="",
            iteration=0,
        )
        assert snapshot.kind == KIND_CHAT

    def test_kind_roundtrips(self):
        snapshot = SessionSnapshot(
            schema_version="1.0", session_id="persona-x", created_at="", updated_at="",
            messages=[], mode=_mode(), todos=[], active_skills=[], run_id="",
            iteration=0, kind=KIND_ROOM_MEMBER,
        )
        data = snapshot.to_dict()
        assert data["kind"] == KIND_ROOM_MEMBER
        restored = SessionSnapshot.from_dict(data, [])
        assert restored.kind == KIND_ROOM_MEMBER

    def test_missing_kind_in_old_snapshot_defaults_to_chat(self):
        restored = SessionSnapshot.from_dict({}, [])
        assert restored.kind == KIND_CHAT


def _mode():
    from agent.run_config import AgentMode

    return AgentMode.BUILD
