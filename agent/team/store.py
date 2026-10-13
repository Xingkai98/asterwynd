"""workspace 级持久化：roster（人设花名册）与房间记录 + 房间日志的裸文件 IO。

分工：本模块只管**读写与结构**，时序/游标语义在 ``roomlog.py``，轮次编排在
``orchestrator.py``。落点是 ``<workspace>/.asterwynd/team/``（design Decision 14）。
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from agent.team import paths
from agent.team.models import Persona, Room, RoomEntry

logger = logging.getLogger("asterwynd.team.store")

ROSTER_SCHEMA_VERSION = "1.0"


class TeamStore:
    """一个 workspace 的 roster + 房间存储。"""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    # ------------------------------------------------------------------
    # roster
    # ------------------------------------------------------------------

    def load_roster(self) -> dict:
        path = paths.roster_path(self.workspace_root)
        if not path.is_file():
            return {"schema_version": ROSTER_SCHEMA_VERSION, "mainBotIds": [], "personas": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            # 损坏的 roster 不静默丢：记日志并回落空花名册（不抛，避免 hub 整个挂掉）。
            logger.warning("roster 读取失败，回落空花名册: %s", exc)
            return {"schema_version": ROSTER_SCHEMA_VERSION, "mainBotIds": [], "personas": []}
        if not isinstance(data, dict):
            return {"schema_version": ROSTER_SCHEMA_VERSION, "mainBotIds": [], "personas": []}
        data.setdefault("mainBotIds", [])
        data.setdefault("personas", [])
        return data

    def _save_roster(self, data: dict) -> None:
        path = paths.roster_path(self.workspace_root)
        _write_json(path, data)

    def list_personas(self) -> list[Persona]:
        return [Persona.from_dict(p) for p in self.load_roster().get("personas", [])]

    def get_persona(self, persona_id: str) -> Persona | None:
        for p in self.list_personas():
            if p.id == persona_id:
                return p
        return None

    def upsert_persona(self, persona: Persona) -> None:
        data = self.load_roster()
        personas = [p for p in data.get("personas", []) if p.get("id") != persona.id]
        personas.append(persona.to_dict())
        data["personas"] = personas
        self._save_roster(data)

    def remove_persona(self, persona_id: str) -> None:
        data = self.load_roster()
        data["personas"] = [p for p in data.get("personas", []) if p.get("id") != persona_id]
        data["mainBotIds"] = [i for i in data.get("mainBotIds", []) if i != persona_id]
        self._save_roster(data)

    def set_persona_chat_session(self, persona_id: str, session_id: str) -> None:
        data = self.load_roster()
        for p in data.get("personas", []):
            if p.get("id") == persona_id:
                p["chat_session_id"] = session_id
                break
        self._save_roster(data)

    def persona_chat_session(self, persona_id: str) -> str | None:
        persona = self.get_persona(persona_id)
        return persona.chat_session_id if persona else None

    def main_bot_ids(self) -> list[str]:
        return [str(i) for i in self.load_roster().get("mainBotIds", [])]

    def set_main_bot_ids(self, ids: list[str]) -> None:
        data = self.load_roster()
        data["mainBotIds"] = [str(i) for i in ids]
        self._save_roster(data)

    def first_main_bot(self) -> str | None:
        ids = self.main_bot_ids()
        return ids[0] if ids else None

    # ------------------------------------------------------------------
    # rooms
    # ------------------------------------------------------------------

    def list_rooms(self) -> list[Room]:
        directory = paths.rooms_dir(self.workspace_root)
        if not directory.is_dir():
            return []
        rooms: list[Room] = []
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".json"):
                continue
            room = self.get_room(name[: -len(".json")])
            if room is not None:
                rooms.append(room)
        return rooms

    def get_room(self, room_id: str) -> Room | None:
        path = paths.room_record_path(self.workspace_root, room_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            logger.warning("房间记录读取失败 %s: %s", room_id, exc)
            return None
        if not isinstance(data, dict):
            return None
        return Room.from_dict(data)

    def save_room(self, room: Room) -> None:
        _write_json(paths.room_record_path(self.workspace_root, room.id), room.to_dict())

    def remove_room(self, room_id: str) -> None:
        """删房间记录 + 房间日志（不含会话底座 / 记忆——那些在级联里做）。"""
        for path in (
            paths.room_record_path(self.workspace_root, room_id),
            paths.room_log_path(self.workspace_root, room_id),
        ):
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError as exc:  # noqa: BLE001 - 单个文件删除失败不阻断级联
                logger.warning("删除 %s 失败: %s", path, exc)

    # ------------------------------------------------------------------
    # 房间日志（裸 IO；时序语义见 roomlog.RoomLog）
    # ------------------------------------------------------------------

    def append_room_log(
        self, room_id: str, *, speaker: str | None, kind: str, text: str, ts: str
    ) -> RoomEntry:
        """追加一条条目，seq 单调递增（从当前最大 seq 接续）。"""
        entries = self.read_room_log(room_id)
        seq = (entries[-1].seq + 1) if entries else 1
        entry = RoomEntry(seq=seq, speaker=speaker, kind=kind, text=text, ts=ts)
        path = paths.room_log_path(self.workspace_root, room_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        return entry

    def read_room_log(self, room_id: str) -> list[RoomEntry]:
        """读全部条目（跳过无法解码的行，并在日志里如实报告跳过的行号）。"""
        path = paths.room_log_path(self.workspace_root, room_id)
        if not path.is_file():
            return []
        entries: list[RoomEntry] = []
        skipped: list[int] = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    skipped.append(lineno)
                    continue
                if isinstance(data, dict):
                    entries.append(RoomEntry.from_dict(data))
        if skipped:
            logger.warning(
                "房间日志 %s 有 %d 行无法解码（行号 %s），已跳过",
                room_id, len(skipped), skipped[:10],
            )
        return entries


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
