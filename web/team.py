"""Web 层的群聊服务：内部会话工厂 + 编排器装配 + 人设/房间 CRUD 与级联（Decision 15）。

分层说明（Decision 4）：编排器在 ``agent/team``，它依赖 ``SessionRunner`` /
``SessionResolver`` 抽象；本模块是**实现并注入**它们的地方——它持有
``SessionManager`` / ``AgentSession``，因此 ``agent/`` 不需要反向 import ``web/``。
"""
from __future__ import annotations

import asyncio
import copy
import logging
import shutil
from pathlib import Path

from agent.config import AsterwyndConfig
from agent.session import (
    KIND_PERSONA_CHAT,
    KIND_ROOM_MEMBER,
    new_internal_session_id,
)
from agent.team import paths
from agent.team.memory_review import MemoryReviewService, MemoryReviewer, make_scope
from agent.run_config import parse_agent_mode
from agent.team.models import (
    DEFAULT_PERSONA_MODE,
    DEFAULT_REPLY_MODE,
    PERSONA_MODES,
    REPLY_MODES,
    Persona,
    Room,
)
from agent.team.orchestrator import RoomOrchestrator, RoundResult
from agent.team.runner import TurnOutcome
from agent.team.store import TeamStore
from web.session import SessionManager, WebSessionRunner

logger = logging.getLogger("asterwynd.web.team")


def clone_llm_with_model(base_llm, model: str):
    """把会话的模型绑定落到一个**共享 provider 配置**的 LLM 实例上。

    人设的「模型绑定」是一个 roster 字段（Decision 13/15）。这里不改 provider 的
    凭据与 base_url，只换 ``model``；任何失败都回落到基础 llm 并如实记日志——
    模型绑定不生效是可见的降级，不是静默失败。
    """
    if not model:
        return base_llm
    if getattr(base_llm, "model", None) == model:
        return base_llm
    try:
        clone = copy.copy(base_llm)
        clone.model = model
        return clone
    except Exception:  # noqa: BLE001 - 绑定失败不阻断会话创建
        logger.warning("人设模型绑定 %r 失败，回落会话默认模型", model, exc_info=True)
        return base_llm


def _normalize_persona_mode(raw) -> str:
    """人设运行模式：非法值结构化拒绝（``ValueError``）。"""
    text = str(raw or "").strip()
    if not text:
        return DEFAULT_PERSONA_MODE
    try:
        return parse_agent_mode(text).value
    except ValueError:
        raise ValueError("invalid_persona_mode") from None


def _persona_mode_or_default(raw) -> str:
    """读盘路径的宽容版：手改坏的 roster 不该让整个会话面建不出来。"""
    try:
        return parse_agent_mode(str(raw or DEFAULT_PERSONA_MODE)).value
    except ValueError:
        logger.warning("人设 mode 取值非法（%r），回落缺省 %s", raw, DEFAULT_PERSONA_MODE)
        return DEFAULT_PERSONA_MODE


def _normalize_reply_mode(raw) -> str:
    text = str(raw or "").strip() or DEFAULT_REPLY_MODE
    if text not in REPLY_MODES:
        raise ValueError("invalid_reply_mode")
    return text


class RoomEventBus:
    """房间级事件订阅（Decision 9：现有 WS 路由按 session 绑定，不适用于房间聚合）。

    多个 tab 同房间时每条连接各自订阅；断开只摘该连接。广播尽力而为——单条连接
    发送失败只摘它，不影响轮次本身。
    """

    def __init__(self) -> None:
        self._subs: dict[str, list] = {}

    def subscribe(self, room_id: str, send) -> object:
        token = object()
        self._subs.setdefault(room_id, []).append((token, send))
        return token

    def unsubscribe(self, room_id: str, token) -> None:
        subs = self._subs.get(room_id)
        if not subs:
            return
        self._subs[room_id] = [(t, s) for t, s in subs if t is not token]
        if not self._subs[room_id]:
            self._subs.pop(room_id, None)

    def subscriber_count(self, room_id: str) -> int:
        return len(self._subs.get(room_id, []))

    async def broadcast(self, room_id: str, payload: dict) -> int:
        subs = list(self._subs.get(room_id, []))
        sent = 0
        for token, send in subs:
            try:
                await send(payload)
                sent += 1
            except Exception:  # noqa: BLE001 - 单条连接失败不拖垮广播
                self.unsubscribe(room_id, token)
        return sent


class TeamSessionPool:
    """内部会话的**懒构造 + 上限 + 排队 + LRU 淘汰**（Decision 1 / Q4）。

    上限口径 = **内部会话数**（人设单聊 + (人设, 群) 群内会话）；达到上限时新建
    **排队**等待执行槽释放，SHALL NOT 拒绝创建。槽的释放来自「淘汰一个空闲的
    最久未用会话」（其快照仍在盘上，下次按同一 id 恢复）。
    """

    def __init__(self, *, max_sessions: int) -> None:
        self._max = max(1, int(max_sessions))
        self._live: list[str] = []
        self._event = asyncio.Event()

    def live(self) -> list[str]:
        return list(self._live)

    def track(self, session_id: str) -> None:
        if session_id in self._live:
            self._live.remove(session_id)
        self._live.append(session_id)

    def touch(self, session_id: str) -> None:
        self.track(session_id)

    def forget(self, session_id: str) -> None:
        if session_id in self._live:
            self._live.remove(session_id)
        self._event.set()

    async def acquire(self, manager: SessionManager) -> None:
        """等到有执行槽：直接有空位，或淘汰一个空闲会话。"""
        while True:
            if len(self._live) < self._max:
                return
            victim = self._lru_idle(manager)
            if victim is not None:
                manager.unload_session(victim)
                self.forget(victim)
                return
            self._event.clear()
            # 通知点覆盖「成员 run 结束」与「会话被淘汰」，但外部**直接**释放
            # ``run_lock``（测试或其它调用方）不可观测 ⇒ 加一个有界轮询兜底。
            # 只在满员时以 ~10Hz 轮询，正常路径仍由事件立即唤醒。
            try:
                await asyncio.wait_for(self._event.wait(), timeout=0.1)
            except (asyncio.TimeoutError, TimeoutError):
                pass

    def notify_capacity(self) -> None:
        self._event.set()

    def _lru_idle(self, manager: SessionManager) -> str | None:
        for session_id in list(self._live):
            session = manager.get_session(session_id)
            if session is None:
                self._live.remove(session_id)
                continue
            if not session.run_lock.locked():
                return session_id
        return None


class _WorkspaceTeam:
    """一个 workspace 的群聊装配（store / 记忆 review / 编排器 / 会话池）。"""

    def __init__(self, service: "TeamService", workspace: Path) -> None:
        self.workspace = workspace
        self.store = TeamStore(workspace)
        self.review = MemoryReviewService(
            store=self.store,
            project_root=workspace,
            config=service.config.memory,
            cost_ledger=service.cost_ledger,
        )
        if service.llm is not None:
            self.review.build_llm_parts(service.llm)
        self.pool = TeamSessionPool(max_sessions=service.config.team.max_sessions)
        self.orchestrator = RoomOrchestrator(
            store=self.store,
            resolver=_WorkspaceResolver(service, self),
            runner=_WorkspaceRunner(service, self),
            turn_timeout=service.config.team.turn_timeout_seconds,
            extra_turns=service.config.team.extra_turns,
            admin_extra_turns=service.config.team.admin_extra_turns,
            turns_each=service.config.team.turns_each,
            admin_turns_each=service.config.team.admin_turns_each,
            review_sink=self.review,
            on_event=service.event_sink,
        )


class _WorkspaceRunner(WebSessionRunner):
    """带「跑完通知会话池」的 runner：成员 run 结束后可能有槽可用。"""

    def __init__(self, service: "TeamService", team: _WorkspaceTeam) -> None:
        super().__init__(service.manager)
        self._team = team

    async def run(self, session_id, message, *, timeout=None, silent_marker=None):
        try:
            return await super().run(
                session_id, message, timeout=timeout, silent_marker=silent_marker
            )
        finally:
            self._team.pool.notify_capacity()


class _WorkspaceResolver:
    """``SessionResolver`` 的 workspace 版实现（懒构造 + 上限 + 排队）。"""

    def __init__(self, service: "TeamService", team: _WorkspaceTeam) -> None:
        self._service = service
        self._team = team

    async def ensure_room_session(self, room_id: str, persona_id: str) -> str:
        room = self._team.store.get_room(room_id)
        if room is None:
            raise KeyError(f"unknown room: {room_id}")
        persona = self._team.store.get_persona(persona_id)
        if persona is None:
            raise KeyError(f"unknown persona: {persona_id}")
        session_id = room.sessions.get(persona_id) or new_internal_session_id(
            KIND_ROOM_MEMBER
        )
        if room.sessions.get(persona_id) != session_id:
            room.sessions[persona_id] = session_id
            self._team.store.save_room(room)
        await self._service._ensure_session(
            team=self._team, kind=KIND_ROOM_MEMBER, session_id=session_id,
            persona=persona, room=room,
        )
        return session_id

    async def ensure_persona_chat_session(self, persona_id: str) -> str:
        persona = self._team.store.get_persona(persona_id)
        if persona is None:
            raise KeyError(f"unknown persona: {persona_id}")
        session_id = persona.chat_session_id or new_internal_session_id(
            KIND_PERSONA_CHAT
        )
        if persona.chat_session_id != session_id:
            self._team.store.set_persona_chat_session(persona_id, session_id)
        await self._service._ensure_session(
            team=self._team, kind=KIND_PERSONA_CHAT, session_id=session_id,
            persona=persona, room=None,
        )
        return session_id


class TeamService:
    """Web 群聊板块的服务入口（人设/房间 CRUD + 内部会话 + 编排 + 级联）。"""

    def __init__(
        self,
        *,
        manager: SessionManager,
        llm,
        config: AsterwyndConfig | None = None,
        cost_ledger=None,
        event_sink=None,
        reviewer: MemoryReviewer | None = None,
    ) -> None:
        self.manager = manager
        self.llm = llm
        self.config = config or manager.config
        self.cost_ledger = cost_ledger
        self.event_sink = event_sink
        self._reviewer = reviewer
        self._teams: dict[str, _WorkspaceTeam] = {}

    # ------------------------------------------------------------------
    # 装配
    # ------------------------------------------------------------------

    def team_for(self, workspace: str | Path | None) -> _WorkspaceTeam:
        resolved = self.manager.resolve_workspace(workspace)
        key = str(resolved)
        team = self._teams.get(key)
        if team is None:
            team = _WorkspaceTeam(self, resolved)
            if self._reviewer is not None:
                team.review._reviewer = self._reviewer
            self._teams[key] = team
        return team

    def workspace_of_room(self, room_id: str) -> Path | None:
        for team in self._scan_teams():
            if team.store.get_room(room_id) is not None:
                return team.workspace
        return None

    def workspace_of_session(self, session_id: str) -> Path | None:
        for team in self._scan_teams():
            for persona in team.store.list_personas():
                if persona.chat_session_id == session_id:
                    return team.workspace
            for room in team.store.list_rooms():
                if session_id in room.sessions.values():
                    return team.workspace
        return None

    def _scan_teams(self) -> list[_WorkspaceTeam]:
        teams: list[_WorkspaceTeam] = []
        for workspace, _is_primary in self.manager.list_workspaces():
            teams.append(self.team_for(workspace))
        for key in list(self._teams):
            if all(str(t.workspace) != key for t in teams):
                teams.append(self._teams[key])
        return teams

    # ------------------------------------------------------------------
    # 内部会话工厂（懒构造 + 上限 + 排队）
    # ------------------------------------------------------------------

    async def _ensure_session(
        self, *, team: _WorkspaceTeam, kind: str, session_id: str,
        persona: Persona | None, room: Room | None,
    ) -> str:
        manager = self.manager
        existing = manager.get_session(session_id)
        if existing is not None:
            team.pool.touch(session_id)
            return session_id
        # 懒构造：**首次使用时**才建底座（未使用的会话面不构造 AgentLoop）。
        await team.pool.acquire(manager)
        snapshot = manager._store_for(team.workspace).load(session_id)
        room_id = room.id if room is not None else None
        # 人设运行模式（Decision 18）：单聊与所有群内会话都以它构造。
        persona_mode = (
            parse_agent_mode(_persona_mode_or_default(persona.mode))
            if persona is not None
            else None
        )
        if snapshot is not None and persona_mode is not None:
            # roster 是模式的事实来源：``AgentLoop`` 的 resume 分支会用**快照** 的
            # mode 覆盖构造期模式（``agent/loop.py`` 的 `set_mode(snapshot.mode)`），
            # 若用户改过人设模式，快照里的旧值会把新值顶回去。故在传给 loop 之前
            # 用 roster 值规整快照；下一次 run 落盘后快照即与新值一致。
            snapshot.mode = persona_mode
        memory = None
        if persona is not None:
            scope = make_scope(team.workspace, persona.id, room_id)
            memory = team.review.memory_for(scope)
            if room_id is not None:
                team.review.ensure_scope(scope)
        await manager.create_team_session_async(
            session_id=session_id,
            kind=kind,
            llm=clone_llm_with_model(self.llm, persona.model if persona else ""),
            workspace_root=team.workspace,
            persona_memory=memory,
            memory_config=self.config.memory,
            quality_config=self.config.tools.quality,
            system_prompt=persona.instructions if persona else None,
            resume_snapshot=snapshot,
            initial_mode=persona_mode,
        )
        team.pool.track(session_id)
        if persona is not None:
            self._attach_turn_listener(team, session_id, persona.id, room_id)
        return session_id

    def _attach_turn_listener(
        self, team: _WorkspaceTeam, session_id: str, persona_id: str, room_id: str | None
    ) -> None:
        """给**人设单聊**会话挂回合结束监听器（群内会话不走这里）。

        触发路径分工（单一来源，避免同一次发言排两次 review）：

        - **单聊**：本监听器负责——把这一回合的**用户消息与助手回复**都写进该
          chat scope 的待 review 缓冲（与消息表下标解耦：压缩 / resume 都会让
          下标语义漂移），并在**实际产生发言**时排一次 review；
        - **群内会话**：由编排器的 ``review_sink`` 负责（``on_member_turn``），
          它在发言**落房间日志之后**触发，因此 review 一定能读到本人刚发出的那条。
        """
        if room_id is not None:
            return
        session = self.manager.get_session(session_id)
        if session is None:
            return
        scope = make_scope(team.workspace, persona_id, None)

        async def _listener(outcome: TurnOutcome, user_text: str) -> None:
            # 用户那句通常才是可记事实的来源，必须与群 scope 的 ``User:`` 口径对称。
            if user_text and user_text.strip():
                team.review.append_chat_message(scope, f"User: {user_text.strip()}")
            if outcome.spoke and outcome.text.strip():
                team.review.append_chat_message(scope, f"Assistant: {outcome.text.strip()}")
            await team.review.on_member_turn(
                room_id=None, persona_id=persona_id, outcome=outcome
            )

        session.turn_listeners.append(_listener)

    # ------------------------------------------------------------------
    # 运行时入口
    # ------------------------------------------------------------------

    async def ensure_persona_chat_session(
        self, workspace: str | Path | None, persona_id: str
    ) -> str:
        team = self.team_for(workspace)
        resolver = _WorkspaceResolver(self, team)
        return await resolver.ensure_persona_chat_session(persona_id)

    async def submit_room_message(
        self, workspace: str | Path | None, room_id: str, text: str
    ) -> RoundResult:
        team = self.team_for(workspace)
        if team.store.get_room(room_id) is None:
            discovered = self.workspace_of_room(room_id)
            if discovered is None:
                raise KeyError(f"unknown room: {room_id}")
            team = self.team_for(discovered)
        return await team.orchestrator.submit_user_message(room_id, text)

    async def adopt_internal_session(
        self, session_id: str, workspace: str | Path | None = None
    ) -> bool:
        """把（恢复请求命中的）内部会话 id 接回群聊服务：按 kind 懒构造底座。

        普通 WS 的 ``resume_session_async`` 走的是通用建会话路径，**不带**人设
        记忆接线与 pending 降级；内部会话必须经本方法，否则会静默落成半接线形态。
        """
        for team in self._scan_teams():
            if workspace is not None:
                resolved = self.manager.resolve_workspace(workspace)
                if team.workspace != resolved:
                    continue
            for persona in team.store.list_personas():
                if persona.chat_session_id == session_id:
                    await self._ensure_session(
                        team=team, kind=KIND_PERSONA_CHAT, session_id=session_id,
                        persona=persona, room=None,
                    )
                    return True
            for room in team.store.list_rooms():
                for persona_id, sid in room.sessions.items():
                    if sid != session_id:
                        continue
                    persona = team.store.get_persona(persona_id)
                    if persona is None:
                        continue
                    await self._ensure_session(
                        team=team, kind=KIND_ROOM_MEMBER, session_id=session_id,
                        persona=persona, room=room,
                    )
                    return True
        return False

    # ------------------------------------------------------------------
    # 人设 CRUD
    # ------------------------------------------------------------------

    def list_personas(self, workspace=None) -> list[Persona]:
        return self.team_for(workspace).store.list_personas()

    def create_persona(
        self, workspace, *, name: str, role: str = "", instructions: str = "",
        model: str = "", main_bot: bool = False, mode: str | None = None,
    ) -> Persona:
        team = self.team_for(workspace)
        if not (name or "").strip():
            raise ValueError("missing_name")
        persona = Persona(
            name=name.strip(), role=role or "", instructions=instructions or "",
            model=model or "", mode=_normalize_persona_mode(mode),
        )
        team.store.upsert_persona(persona)
        if main_bot:
            ids = team.store.main_bot_ids()
            if persona.id not in ids:
                team.store.set_main_bot_ids([*ids, persona.id])
        return persona

    def update_persona(self, workspace, persona_id: str, **fields) -> Persona:
        team = self.team_for(workspace)
        persona = team.store.get_persona(persona_id)
        if persona is None:
            raise KeyError(persona_id)
        for field in ("name", "role", "instructions", "model"):
            if field in fields and fields[field] is not None:
                setattr(persona, field, str(fields[field]))
        if fields.get("mode") is not None:
            persona.mode = _normalize_persona_mode(fields["mode"])
        team.store.upsert_persona(persona)
        if "main_bot" in fields and fields["main_bot"] is not None:
            ids = [i for i in team.store.main_bot_ids() if i != persona_id]
            if fields["main_bot"]:
                ids.append(persona_id)
            team.store.set_main_bot_ids(ids)
        return persona

    def set_main_bots(self, workspace, ids: list[str]) -> None:
        self.team_for(workspace).store.set_main_bot_ids(list(ids))

    def main_bot_ids(self, workspace=None) -> list[str]:
        return self.team_for(workspace).store.main_bot_ids()

    async def delete_persona(self, workspace, persona_id: str) -> dict:
        """删除人设 + 级联（Decision 15）。

        顺序钉死：**先删会话底座与该人设的全部记忆 scope，最后删 roster 条目**。
        这样中断时 roster 仍在、删除可重试（先删 roster 会留下「hub 不列、接口
        又拒删」的孤儿内部会话）。每步对「已不存在」都当成功 ⇒ 幂等。
        """
        team = self.team_for(workspace)
        store = team.store
        persona = store.get_persona(persona_id)
        if persona is None:
            return {"deleted": True, "already_absent": True}

        managers = self.manager
        # 1) 单聊会话底座
        if persona.chat_session_id:
            managers.remove_session(persona.chat_session_id, workspace=team.workspace)
            team.pool.forget(persona.chat_session_id)
        team.review.forget_scope(make_scope(team.workspace, persona_id, None))

        # 2) 从所有房间移除该成员（含群内会话底座与该 (人设, 群) 记忆 scope）
        for room in store.list_rooms():
            scope = make_scope(team.workspace, persona_id, room.id)
            changed = False
            session_id = room.sessions.pop(persona_id, None)
            if session_id:
                managers.remove_session(session_id, workspace=team.workspace)
                team.pool.forget(session_id)
                changed = True
            if persona_id in room.members:
                room.members = [m for m in room.members if m != persona_id]
                changed = True
            if persona_id in room.seen:
                room.seen.pop(persona_id, None)
                changed = True
            if room.admin == persona_id:
                room.admin = None
                changed = True
            team.review.forget_scope(scope)
            if changed:
                store.save_room(room)
            _rmtree(paths.persona_room_subtree(team.workspace, persona_id, room.id))

        # 3) 该人设的整棵记忆子树（含 chat/ 与 rooms/<rid>/）
        _rmtree(paths.persona_subtree(team.workspace, persona_id))

        # 4) 最后删 roster 条目
        store.remove_persona(persona_id)
        return {"deleted": True, "persona_id": persona_id}

    # ------------------------------------------------------------------
    # 房间 CRUD
    # ------------------------------------------------------------------

    def list_rooms(self, workspace=None) -> list[Room]:
        return self.team_for(workspace).store.list_rooms()

    def get_room(self, workspace, room_id: str) -> Room | None:
        return self.team_for(workspace).store.get_room(room_id)

    def create_room(
        self, workspace, *, name: str, members: list[str], admin: str | None = None,
        notice: str = "", created_by: str | None = None, reply_mode: str | None = None,
    ) -> Room:
        team = self.team_for(workspace)
        if not (name or "").strip():
            raise ValueError("missing_name")
        known = {p.id for p in team.store.list_personas()}
        unknown = [m for m in members if m not in known]
        if unknown:
            raise ValueError("unknown_member")
        resolved_admin = admin
        if resolved_admin is None:
            # 创建房间时默认把创建者的 Chief 身份者设为 admin（Decision 13）。
            chiefs = team.store.main_bot_ids()
            resolved_admin = created_by if created_by in members else (
                chiefs[0] if chiefs and chiefs[0] in members else None
            )
        room = Room(
            name=name.strip(), members=list(dict.fromkeys(members)),
            admin=resolved_admin, notice=notice or "", created_by=created_by,
            reply_mode=_normalize_reply_mode(reply_mode),
        )
        team.store.save_room(room)
        return room

    def update_room(self, workspace, room_id: str, **fields) -> Room:
        team = self.team_for(workspace)
        room = team.store.get_room(room_id)
        if room is None:
            raise KeyError(room_id)
        if fields.get("name"):
            room.name = str(fields["name"])
        if fields.get("notice") is not None:
            room.notice = str(fields.get("notice") or "")
        if fields.get("reply_mode") is not None:
            room.reply_mode = _normalize_reply_mode(fields["reply_mode"])
        if fields.get("admin") is not None:
            room.admin = fields["admin"] or None
        if fields.get("members") is not None:
            known = {p.id for p in team.store.list_personas()}
            members = [str(m) for m in fields["members"]]
            if any(m not in known for m in members):
                raise ValueError("unknown_member")
            removed = [m for m in room.members if m not in members]
            room.members = list(dict.fromkeys(members))
            for persona_id in removed:
                session_id = room.sessions.pop(persona_id, None)
                if session_id:
                    self.manager.remove_session(session_id, workspace=team.workspace)
                    team.pool.forget(session_id)
                room.seen.pop(persona_id, None)
                team.review.forget_scope(make_scope(team.workspace, persona_id, room.id))
                _rmtree(
                    paths.persona_room_subtree(team.workspace, persona_id, room.id)
                )
                if room.admin == persona_id:
                    room.admin = None
        team.store.save_room(room)
        return room

    async def delete_room(self, workspace, room_id: str) -> dict:
        """删除房间 + 级联：群内会话底座 + 所有该房间的 (人设, 房间) 记忆目录，
        最后删房间记录与房间日志。幂等（可中断重试）。"""
        team = self.team_for(workspace)
        store = team.store
        room = store.get_room(room_id)
        if room is None:
            return {"deleted": True, "already_absent": True}

        persona_ids = set(room.sessions) | set(room.members) | set(room.seen)
        for persona_id in persona_ids:
            session_id = room.sessions.get(persona_id)
            if session_id:
                self.manager.remove_session(session_id, workspace=team.workspace)
                team.pool.forget(session_id)
            team.review.forget_scope(make_scope(team.workspace, persona_id, room_id))
            _rmtree(paths.persona_room_subtree(team.workspace, persona_id, room_id))

        store.remove_room(room_id)
        return {"deleted": True, "room_id": room_id}

    # ------------------------------------------------------------------
    # 房间时间线
    # ------------------------------------------------------------------

    def room_timeline(self, workspace, room_id: str) -> list[dict]:
        team = self.team_for(workspace)
        return [e.to_dict() for e in team.store.read_room_log(room_id)]

    def room_members(self, workspace, room_id: str) -> list[dict]:
        team = self.team_for(workspace)
        room = team.store.get_room(room_id)
        if room is None:
            return []
        personas = {p.id: p for p in team.store.list_personas()}
        return [
            {
                "id": pid,
                "name": personas[pid].name if pid in personas else pid,
                "role": personas[pid].role if pid in personas else "",
                "is_admin": room.admin == pid,
            }
            for pid in room.members
        ]


def _rmtree(path: Path) -> None:
    """删除目录树，**不存在**当成功（级联幂等的前提之一）。"""
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return
    except OSError as exc:  # noqa: BLE001 - 单个目录失败不阻断级联的其余步骤
        logger.warning("级联删除 %s 失败: %s", path, exc)


# ``TurnOutcome`` 在 web 层只是转发（避免上层再从 agent.team 导入）。
__all__ = [
    "RoomEventBus",
    "TeamService",
    "TeamSessionPool",
    "TurnOutcome",
    "clone_llm_with_model",
]
