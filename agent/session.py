import hashlib
import json
import os
import warnings
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from agent.message import Message
from agent.planning.manager import PlanItem
from agent.run_config import AgentMode

CURRENT_SCHEMA_VERSION = "1.0"


@dataclass
class SessionSnapshot:
    schema_version: str
    session_id: str
    created_at: str
    updated_at: str
    messages: list[Message]
    mode: AgentMode
    todos: list[PlanItem]
    active_skills: list[str]
    run_id: str
    iteration: int
    user_system_prompt: str = ""
    runtime_fingerprint: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "mode": self.mode.value,
            "todos": [t.to_dict() for t in self.todos],
            "active_skills": self.active_skills,
            "run_id": self.run_id,
            "iteration": self.iteration,
            "user_system_prompt": self.user_system_prompt,
            "runtime_fingerprint": self.runtime_fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict, messages: list[Message]) -> "SessionSnapshot":
        return cls(
            schema_version=data.get("schema_version", "1.0"),
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            messages=messages,
            mode=AgentMode(data.get("mode", "build")),
            todos=[PlanItem.from_dict(t) for t in data.get("todos", [])],
            active_skills=data.get("active_skills", []),
            run_id=data.get("run_id", ""),
            iteration=data.get("iteration", 0),
            user_system_prompt=data.get("user_system_prompt", ""),
            runtime_fingerprint=data.get("runtime_fingerprint", {}),
        )


class SessionStore:
    def __init__(self, sessions_root: str):
        self._root = sessions_root
        self._last_hash: dict[str, str] = {}

    # ---- public API ----

    def save(self, snapshot: SessionSnapshot) -> bool:
        """保存 session 快照。无变更时跳过写入返回 False。"""
        self._validate_session_id(snapshot.session_id, self._root)
        snapshot_dict = snapshot.to_dict()
        # dedup hash 去掉 updated_at（每次保存都会变）
        dedup_dict = {k: v for k, v in snapshot_dict.items() if k != "updated_at"}
        new_hash = _hash_dict(dedup_dict, snapshot.messages)

        if self._last_hash.get(snapshot.session_id) == new_hash:
            return False

        snapshot.updated_at = _now_iso()
        snapshot_dict["updated_at"] = snapshot.updated_at
        self._write(snapshot.session_id, snapshot_dict, snapshot.messages)
        self._last_hash[snapshot.session_id] = new_hash
        return True

    def load(
        self,
        session_id: str,
        current_runtime_fingerprint: dict | None = None,
    ) -> SessionSnapshot | None:
        """加载 session 快照。不存在或损坏返回 None。"""
        session_dir = self._validate_session_id(session_id, self._root)
        snapshot_path = os.path.join(session_dir, "snapshot.json")
        messages_path = os.path.join(session_dir, "messages.json")

        if not os.path.isfile(snapshot_path) or not os.path.isfile(messages_path):
            return None

        try:
            with open(snapshot_path) as f:
                snapshot_data = json.load(f)
            with open(messages_path) as f:
                messages_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        # schema_version 兼容检查
        schema_ver = snapshot_data.get("schema_version", "1.0")
        if not self._is_schema_compatible(schema_ver):
            warnings.warn(
                f"Session schema v{schema_ver} is incompatible with current v{CURRENT_SCHEMA_VERSION}. "
                f"Session {session_id} cannot be restored."
            )
            return None

        # runtime fingerprint 对比
        stored_fp = snapshot_data.get("runtime_fingerprint", {})
        if current_runtime_fingerprint and stored_fp:
            _warn_fingerprint_mismatch(session_id, stored_fp, current_runtime_fingerprint)

        messages = [Message.from_dict(m) for m in messages_data]
        return SessionSnapshot.from_dict(snapshot_data, messages)

    def list_sessions(self) -> list[dict]:
        if not os.path.isdir(self._root):
            return []

        sessions = []
        for name in sorted(os.listdir(self._root)):
            try:
                session_dir = self._validate_session_id(name, self._root)
            except ValueError:
                continue
            if not os.path.isdir(session_dir):
                continue
            snapshot_path = os.path.join(session_dir, "snapshot.json")
            if not os.path.isfile(snapshot_path):
                continue
            try:
                with open(snapshot_path) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            sessions.append({
                "session_id": data.get("session_id", name),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "mode": data.get("mode", ""),
                "messages": data.get("message_count", 0),
            })
        # 补充消息数（从 messages.json 统计）
        for s in sessions:
            sid = s["session_id"]
            msg_path = os.path.join(self._root, sid, "messages.json")
            if os.path.isfile(msg_path):
                try:
                    with open(msg_path) as f:
                        msg_data = json.load(f)
                    s["messages"] = len(msg_data)
                except (json.JSONDecodeError, OSError):
                    pass

        return sorted(sessions, key=lambda s: s.get("updated_at", ""), reverse=True)

    def remove(self, session_id: str) -> bool:
        session_dir = self._validate_session_id(session_id, self._root)
        if not os.path.isdir(session_dir):
            return False
        import shutil
        shutil.rmtree(session_dir)
        self._last_hash.pop(session_id, None)
        return True

    # ---- internal ----

    @staticmethod
    def _validate_session_id(session_id: str, root: str) -> str:
        if not session_id or os.path.isabs(session_id):
            raise ValueError(f"Invalid session_id: {session_id!r}")
        full = os.path.realpath(os.path.join(root, session_id))
        root_real = os.path.realpath(root)
        if os.path.commonpath([full, root_real]) != root_real:
            raise ValueError(f"Session path escapes root: {session_id!r}")
        return full

    def _write(self, session_id: str, snapshot_dict: dict, messages: list[Message]):
        session_dir = self._validate_session_id(session_id, self._root)
        os.makedirs(session_dir, exist_ok=True)

        snapshot_dict["message_count"] = len(messages)

        tmp_snapshot = os.path.join(session_dir, "snapshot.json.tmp")
        tmp_messages = os.path.join(session_dir, "messages.json.tmp")

        with open(tmp_snapshot, "w") as f:
            json.dump(snapshot_dict, f, ensure_ascii=False, indent=2)
        with open(tmp_messages, "w") as f:
            json.dump([m.to_dict() for m in messages], f, ensure_ascii=False, indent=2)

        os.replace(tmp_snapshot, os.path.join(session_dir, "snapshot.json"))
        os.replace(tmp_messages, os.path.join(session_dir, "messages.json"))

    def _is_schema_compatible(self, stored_version: str) -> bool:
        try:
            stored_major = int(stored_version.split(".")[0])
            current_major = int(CURRENT_SCHEMA_VERSION.split(".")[0])
        except (ValueError, IndexError):
            return False
        return stored_major == current_major


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_dict(snapshot_dict: dict, messages: list[Message]) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(snapshot_dict, sort_keys=True, ensure_ascii=False).encode())
    for m in messages:
        h.update(json.dumps(m.to_dict(), sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()


def _warn_fingerprint_mismatch(session_id: str, stored: dict, current: dict):
    mismatches = []
    for key in ("cwd", "model", "provider", "agent_version"):
        if stored.get(key) != current.get(key):
            mismatches.append(f"  {key}: stored={stored.get(key)!r}, current={current.get(key)!r}")
    if mismatches:
        warning_msg = (
            f"Session {session_id} runtime fingerprint mismatch:\n"
            + "\n".join(mismatches)
            + "\nSession may behave differently than expected."
        )
        warnings.warn(warning_msg, stacklevel=2)
