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
    # Subagent checkpoint extras (issue 79, decision D2): the objective and a
    # minimal "what next" summary aligned with the community minimal-snapshot
    # proposal (Claude Code #16375). Optional so main-session snapshots are
    # unaffected.
    objective: str = ""
    blockers: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    # Compact orchestration-bus summary (issue 79 D5): a resume that lost the
    # in-memory bus still has a readable view of what was exchanged.
    bus_summary: str = ""

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
            "objective": self.objective,
            "blockers": list(self.blockers),
            "next_steps": list(self.next_steps),
            "bus_summary": self.bus_summary,
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
            objective=data.get("objective", ""),
            blockers=list(data.get("blockers", [])),
            next_steps=list(data.get("next_steps", [])),
            bus_summary=data.get("bus_summary", ""),
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
            with open(snapshot_path, encoding="utf-8") as f:
                snapshot_data = json.load(f)
            with open(messages_path, encoding="utf-8") as f:
                messages_data = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            # ``UnicodeDecodeError`` 是 ``ValueError`` 的子类、**不是** ``OSError``：
            # 不显式列出它，locale 非 UTF-8 平台上读到历史脏文件会直接把异常抛给调用方
            # （实测：Windows/GBK 下 `GET /api/sessions` 整个 500）。
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
        """列出会话元数据。

        **单条损坏 SHALL NOT 打掉整个列表**（change ``fix-windows-encoding-and-guard``）：
        某条会话的落盘文件不可解码/损坏时，该条 SHALL 以 ``damaged: True`` + 可读
        ``reason`` 出现在结果里（``session_id`` 取**目录名**，因为它一定可信），
        其余会话 SHALL 正常返回。坏条目**不许静默消失**——用户看到「少了几个会话」
        却没有任何解释，与「不显示 = 没事」是同一种误读。
        """
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
                with open(snapshot_path, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
                sessions.append({
                    "session_id": name,
                    "created_at": "",
                    "updated_at": "",
                    "mode": "",
                    "messages": 0,
                    "damaged": True,
                    "reason": f"snapshot.json 无法读取（{type(exc).__name__}）",
                })
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
            if s.get("damaged"):
                continue
            sid = s["session_id"]
            msg_path = os.path.join(self._root, sid, "messages.json")
            if os.path.isfile(msg_path):
                try:
                    with open(msg_path, encoding="utf-8") as f:
                        msg_data = json.load(f)
                    s["messages"] = len(msg_data)
                except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
                    # 快照可读、消息不可读：条目保留（会话确实存在），但如实标注。
                    s["damaged"] = True
                    s["reason"] = f"messages.json 无法读取（{type(exc).__name__}）"

        return sorted(sessions, key=lambda s: s.get("updated_at", ""), reverse=True)

    def remove(self, session_id: str) -> bool:
        session_dir = self._validate_session_id(session_id, self._root)
        if not os.path.isdir(session_dir):
            return False
        import shutil
        shutil.rmtree(session_dir)
        self._last_hash.pop(session_id, None)
        # change tool-result-lifecycle D4: agent artifacts live OUTSIDE the
        # session dir (`.asterwynd/artifacts/<scope>`, deliberately not under
        # `sessions/<id>/` so this rmtree never destroys a live ref). The
        # `_sessions` dict is never cleaned up, so this deletion must be
        # explicit — otherwise spilled tool-result refs leak forever.
        self._remove_artifacts(session_id)
        return True

    def _remove_artifacts(self, scope_id: str) -> None:
        """显式清理该会话的 agent artifacts（D4）；失败不阻塞会话删除。"""
        try:
            from agent.artifact_store import AgentArtifactStore

            workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(self._root)))
            AgentArtifactStore.remove_results(workspace_root, scope_id)
        except Exception:  # noqa: BLE001 - 清理是尽力而为，不能把删除会话变成失败
            pass

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

        # 显式 UTF-8：存储格式就是 UTF-8，依赖 locale 默认编码在非 UTF-8 平台上会把
        # 含 emoji/CJK 的会话写成 GBK 或直接抛 UnicodeEncodeError（实测 Windows/GBK）。
        with open(tmp_snapshot, "w", encoding="utf-8") as f:
            json.dump(snapshot_dict, f, ensure_ascii=False, indent=2)
        with open(tmp_messages, "w", encoding="utf-8") as f:
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
