# tests/agent/team/test_team_store.py
"""人设（roster）与房间模型 + workspace 级持久化（tasks 2.1 / 3.1 / 3.2）。

覆盖：稳定 id、跨重启（重新构造 store 后仍读到）、跨 workspace（不同 workspace
互不可见）、人设指令恢复、房间成员 / admin / notice / 会话映射 / seen 游标。
"""
from pathlib import Path

from agent.team.models import Persona, Room
from agent.team.paths import team_dir
from agent.team.store import TeamStore


def _store(ws: Path) -> TeamStore:
    return TeamStore(ws)


class TestPersonaPersistence:
    def test_create_persona_returns_stable_id_and_survives_restart(self, tmp_path):
        store = _store(tmp_path)
        persona = Persona(name="阿曼", role="researcher", instructions="你负责调研", model="m1")
        store.upsert_persona(persona)

        assert persona.id, "persona 必须有稳定 id"

        # 跨重启：新建一个 store 实例（模拟进程重启）仍能读回。
        reopened = _store(tmp_path)
        loaded = reopened.get_persona(persona.id)
        assert loaded is not None
        assert loaded.name == "阿曼"
        assert loaded.instructions == "你负责调研"
        assert loaded.model == "m1"

    def test_persona_ids_are_unique(self, tmp_path):
        store = _store(tmp_path)
        a = Persona(name="a")
        b = Persona(name="b")
        store.upsert_persona(a)
        store.upsert_persona(b)
        assert a.id != b.id

    def test_main_bot_ids_persist(self, tmp_path):
        store = _store(tmp_path)
        a = Persona(name="chief")
        b = Persona(name="chief2")
        store.upsert_persona(a)
        store.upsert_persona(b)
        store.set_main_bot_ids([a.id, b.id])

        reopened = _store(tmp_path)
        assert reopened.main_bot_ids() == [a.id, b.id]
        assert reopened.main_bot_ids()[0] == a.id

    def test_main_bot_ids_empty_without_chief(self, tmp_path):
        store = _store(tmp_path)
        store.upsert_persona(Persona(name="solo"))
        assert store.main_bot_ids() == []

    def test_remove_persona(self, tmp_path):
        store = _store(tmp_path)
        a = Persona(name="a")
        store.upsert_persona(a)
        store.remove_persona(a.id)
        assert store.get_persona(a.id) is None
        assert store.list_personas() == []

    def test_workspaces_are_isolated(self, tmp_path):
        ws_a = tmp_path / "a"
        ws_b = tmp_path / "b"
        ws_a.mkdir()
        ws_b.mkdir()
        _store(ws_a).upsert_persona(Persona(name="only-in-a"))
        assert _store(ws_b).list_personas() == []

    def test_roster_lives_under_workspace_asterwynd(self, tmp_path):
        _store(tmp_path).upsert_persona(Persona(name="a"))
        assert team_dir(tmp_path).is_dir()
        assert str(team_dir(tmp_path)).startswith(str(tmp_path))

    def test_update_persona_keeps_id(self, tmp_path):
        store = _store(tmp_path)
        p = Persona(name="a")
        store.upsert_persona(p)
        p.name = "renamed"
        p.instructions = "new"
        store.upsert_persona(p)

        loaded = _store(tmp_path).get_persona(p.id)
        assert loaded.name == "renamed"
        assert loaded.instructions == "new"


class TestRoomPersistence:
    def test_room_roundtrip(self, tmp_path):
        store = _store(tmp_path)
        a, b = Persona(name="a"), Persona(name="b")
        store.upsert_persona(a)
        store.upsert_persona(b)
        room = Room(
            name="研究组",
            members=[a.id, b.id],
            admin=a.id,
            notice="先说结论",
        )
        room.sessions[b.id] = "room-abc"
        room.seen[a.id] = 3
        store.save_room(room)

        loaded = _store(tmp_path).get_room(room.id)
        assert loaded is not None
        assert loaded.name == "研究组"
        assert loaded.members == [a.id, b.id]
        assert loaded.admin == a.id
        assert loaded.notice == "先说结论"
        assert loaded.sessions == {b.id: "room-abc"}
        assert loaded.seen == {a.id: 3}

    def test_admin_may_be_none(self, tmp_path):
        store = _store(tmp_path)
        room = Room(name="r", members=[])
        store.save_room(room)
        assert _store(tmp_path).get_room(room.id).admin is None

    def test_remove_room_drops_record_and_log(self, tmp_path):
        store = _store(tmp_path)
        room = Room(name="r", members=[])
        store.save_room(room)
        store.append_room_log(room.id, speaker="user", kind="user", text="hi", ts="t0")

        store.remove_room(room.id)

        assert _store(tmp_path).get_room(room.id) is None
        assert store.read_room_log(room.id) == []

    def test_list_rooms(self, tmp_path):
        store = _store(tmp_path)
        store.save_room(Room(name="a", members=[]))
        store.save_room(Room(name="b", members=[]))
        names = sorted(r.name for r in _store(tmp_path).list_rooms())
        assert names == ["a", "b"]

    def test_reply_mode_roundtrips_and_defaults_to_admin(self, tmp_path):
        store = _store(tmp_path)
        room = Room(name="r", members=[], reply_mode="everyone")
        store.save_room(room)
        assert _store(tmp_path).get_room(room.id).reply_mode == "everyone"
        # 缺省
        plain = Room(name="plain", members=[])
        store.save_room(plain)
        assert _store(tmp_path).get_room(plain.id).reply_mode == "admin"

    def test_legacy_room_record_without_reply_mode_reads_as_admin(self, tmp_path):
        import json

        store = _store(tmp_path)
        room = Room(name="legacy", members=[])
        store.save_room(room)
        path = tmp_path / ".asterwynd" / "team" / "rooms" / f"{room.id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("reply_mode", None)          # 模拟本 change 之前写入的记录
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        assert _store(tmp_path).get_room(room.id).reply_mode == "admin"

    def test_legacy_persona_record_without_mode_reads_as_bypass(self, tmp_path):
        import json

        store = _store(tmp_path)
        persona = Persona(name="legacy")
        store.upsert_persona(persona)
        path = tmp_path / ".asterwynd" / "team" / "roster.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data["personas"]:
            item.pop("mode", None)            # 模拟本 change 之前写入的记录
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        assert _store(tmp_path).get_persona(persona.id).mode == "bypass"

    def test_persona_mode_roundtrips(self, tmp_path):
        store = _store(tmp_path)
        persona = Persona(name="a", mode="read_only")
        store.upsert_persona(persona)
        assert _store(tmp_path).get_persona(persona.id).mode == "read_only"

    def test_persona_session_map_roundtrip(self, tmp_path):
        store = _store(tmp_path)
        p = Persona(name="a")
        store.upsert_persona(p)
        store.set_persona_chat_session(p.id, "persona-xyz")
        assert _store(tmp_path).persona_chat_session(p.id) == "persona-xyz"
