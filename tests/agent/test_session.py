import json
import os

import pytest

from agent.message import Message
from agent.run_config import AgentMode
from agent.session import SessionStore, SessionSnapshot, CURRENT_SCHEMA_VERSION


def _make_message(role, content, tool_call_id=None):
    return Message(role=role, content=content, tool_call_id=tool_call_id)


class TestSessionStore:
    def test_save_and_load(self, tmp_path):
        store = SessionStore(sessions_root=str(tmp_path / ".asterwynd" / "sessions"))
        messages = [
            _make_message("user", "hello"),
            _make_message("assistant", "hi there"),
        ]
        snapshot = SessionSnapshot(
            schema_version=CURRENT_SCHEMA_VERSION,
            session_id="sess_001",
            created_at="2026-07-10T10:00:00",
            updated_at="2026-07-10T10:01:00",
            messages=messages,
            mode=AgentMode.BUILD,
            todos=[],
            active_skills=[],
            run_id="run_001",
            iteration=3,
            runtime_fingerprint={"cwd": "/tmp", "model": "test", "provider": "test", "agent_version": "0.1.0"},
        )
        saved = store.save(snapshot)
        assert saved

        loaded = store.load("sess_001")
        assert loaded is not None
        assert loaded.session_id == "sess_001"
        assert loaded.mode == AgentMode.BUILD
        assert loaded.iteration == 3
        assert len(loaded.messages) == 2
        assert loaded.messages[0].role == "user"
        assert loaded.messages[0].content == "hello"

    def test_load_nonexistent(self, tmp_path):
        store = SessionStore(sessions_root=str(tmp_path / ".asterwynd" / "sessions"))
        assert store.load("nonexistent") is None

    def test_list_sessions(self, tmp_path):
        store = SessionStore(sessions_root=str(tmp_path / ".asterwynd" / "sessions"))
        for i in range(3):
            snapshot = SessionSnapshot(
                schema_version=CURRENT_SCHEMA_VERSION,
                session_id=f"sess_{i:03d}",
                created_at="2026-07-10T10:00:00",
                updated_at="2026-07-10T10:01:00",
                messages=[],
                mode=AgentMode.BUILD,
                todos=[],
                active_skills=[],
                run_id=f"run_{i:03d}",
                iteration=0,
                runtime_fingerprint={"cwd": "/tmp", "model": "test", "provider": "test", "agent_version": "0.1.0"},
            )
            store.save(snapshot)

        sessions = store.list_sessions()
        assert len(sessions) == 3

    def test_remove(self, tmp_path):
        store = SessionStore(sessions_root=str(tmp_path / ".asterwynd" / "sessions"))
        snapshot = SessionSnapshot(
            schema_version=CURRENT_SCHEMA_VERSION,
            session_id="sess_rm",
            created_at="2026-07-10T10:00:00",
            updated_at="2026-07-10T10:01:00",
            messages=[],
            mode=AgentMode.BUILD,
            todos=[],
            active_skills=[],
            run_id="run_rm",
            iteration=0,
            runtime_fingerprint={"cwd": "/tmp", "model": "test", "provider": "test", "agent_version": "0.1.0"},
        )
        store.save(snapshot)
        assert store.load("sess_rm") is not None

        removed = store.remove("sess_rm")
        assert removed
        assert store.load("sess_rm") is None

    def test_save_no_change_skips_write(self, tmp_path):
        root = str(tmp_path / ".asterwynd" / "sessions")
        store = SessionStore(sessions_root=root)
        messages = [_make_message("user", "hello")]

        snapshot = SessionSnapshot(
            schema_version=CURRENT_SCHEMA_VERSION,
            session_id="sess_dedup",
            created_at="2026-07-10T10:00:00",
            updated_at="2026-07-10T10:01:00",
            messages=messages,
            mode=AgentMode.BUILD,
            todos=[],
            active_skills=[],
            run_id="run_dedup",
            iteration=0,
            runtime_fingerprint={"cwd": "/tmp", "model": "test", "provider": "test", "agent_version": "0.1.0"},
        )
        assert store.save(snapshot)  # 第一次写入
        assert not store.save(snapshot)  # 无变更，跳过

    def test_corrupted_snapshot(self, tmp_path):
        session_dir = tmp_path / ".asterwynd" / "sessions" / "sess_corrupt"
        session_dir.mkdir(parents=True)
        (session_dir / "snapshot.json").write_text("not valid json")
        (session_dir / "messages.json").write_text("[]")

        store = SessionStore(sessions_root=str(tmp_path / ".asterwynd" / "sessions"))
        assert store.load("sess_corrupt") is None

    def test_missing_pair_file(self, tmp_path):
        session_dir = tmp_path / ".asterwynd" / "sessions" / "sess_missing"
        session_dir.mkdir(parents=True)
        (session_dir / "snapshot.json").write_text('{"schema_version": "1.0"}')
        # no messages.json

        store = SessionStore(sessions_root=str(tmp_path / ".asterwynd" / "sessions"))
        assert store.load("sess_missing") is None

    def test_schema_version_major_mismatch(self, tmp_path):
        store = SessionStore(sessions_root=str(tmp_path / ".asterwynd" / "sessions"))
        snapshot = SessionSnapshot(
            schema_version="2.0",  # future major version
            session_id="sess_v2",
            created_at="2026-07-10T10:00:00",
            updated_at="2026-07-10T10:01:00",
            messages=[],
            mode=AgentMode.BUILD,
            todos=[],
            active_skills=[],
            run_id="run_v2",
            iteration=0,
            runtime_fingerprint={"cwd": "/tmp", "model": "test", "provider": "test", "agent_version": "0.1.0"},
        )
        store.save(snapshot)
        assert store.load("sess_v2") is None  # major mismatch, refuse

    def test_runtime_fingerprint_mismatch_warns(self, tmp_path):
        store = SessionStore(sessions_root=str(tmp_path / ".asterwynd" / "sessions"))
        snapshot = SessionSnapshot(
            schema_version=CURRENT_SCHEMA_VERSION,
            session_id="sess_fp",
            created_at="2026-07-10T10:00:00",
            updated_at="2026-07-10T10:01:00",
            messages=[],
            mode=AgentMode.BUILD,
            todos=[],
            active_skills=[],
            run_id="run_fp",
            iteration=0,
            runtime_fingerprint={"cwd": "/old/path", "model": "old-model", "provider": "test", "agent_version": "0.1.0"},
        )
        store.save(snapshot)

        with pytest.warns(UserWarning, match="fingerprint mismatch"):
            loaded = store.load("sess_fp", current_runtime_fingerprint={"cwd": "/new/path", "model": "new-model", "provider": "test", "agent_version": "0.1.0"})
        assert loaded is not None  # 不拒绝，只是 warn

    def test_rejects_path_escape_session_id(self, tmp_path):
        store = SessionStore(sessions_root=str(tmp_path / ".asterwynd" / "sessions"))

        with pytest.raises(ValueError, match="escapes root"):
            store._validate_session_id("../../etc", store._root)

        with pytest.raises(ValueError, match="Invalid"):
            store._validate_session_id("/absolute/path", store._root)

        with pytest.raises(ValueError, match="Invalid"):
            store._validate_session_id("", store._root)

    def test_remove_rejects_path_escape(self, tmp_path):
        store = SessionStore(sessions_root=str(tmp_path / ".asterwynd" / "sessions"))

        with pytest.raises(ValueError, match="escapes root"):
            store.remove("../../etc")
