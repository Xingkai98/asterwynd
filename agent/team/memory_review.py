"""人设记忆的 review：触发、游标、写回与成本（design Decision 17）。

三条钉死的口径：

1. **触发**：一个回合结束、且该回合**实际产生了发言**（``TurnOutcome.status ==
   "text"``）时，为该会话对应的记忆 scope 排一次 review。``silent`` / ``timeout`` /
   ``failed`` 出口**不**触发——这类成员的记忆停滞由「落后补齐」兜底。
   （与参照的差异：参照对**任何** idle 都触发，``ds-bot/src/host/memory.js:1326``；
   本 change 收紧为仅实际发言，以与「①+兜底」语义自洽并控制成本。）

2. **落后补齐**：度量基准是 **review 游标 ``reviewed``**（**不是** Decision 6 的
   注入游标 ``seen``——后者每回合推进、含静默，用它作基准则落后恒为 0、补齐永不
   触发）；落后 = ``room.seq − reviewed``，单位 = 房间日志条目数，缺省阈值 30。

3. **游标 / 输入**：每个 scope 一个进度记录。**群 scope** 以房间日志 ``seq`` 为单位
   （稳定）。**单聊 scope SHALL NOT 用消息表下标**——``Message`` 无 id/timestamp/seq，
   而上下文压缩会就地缩短消息表、session resume 会重建消息表，下标语义必漂移
   （压缩后游标越过表尾 ⇒ review 永久停摆）。故单聊 scope 的输入是**持久化待 review
   缓冲**（``<scope>/pending_review.jsonl``），与消息表下标解耦。
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from agent.config import MemoryConfig
from agent.memory.persistent import PersistentMemory
from agent.team import paths
from agent.team.models import RoomEntry
from agent.team.runner import TurnOutcome
from agent.team.store import TeamStore

logger = logging.getLogger("asterwynd.team.memory_review")

#: 进度记录文件名（落在该 scope 的记忆目录内）。
PROGRESS_FILENAME = "reviewed.json"
#: 单聊 scope 的待 review 缓冲文件名（同样落在 scope 记忆目录内）。
PENDING_FILENAME = "pending_review.jsonl"

#: 写回动作枚举（review 的输出）。
WRITE_ACTIONS = ("add", "update", "supplement", "conflict")
REMOVE_ACTION = "remove"


@dataclass(frozen=True)
class MemoryChange:
    """review 判定出的单条记忆变更。"""

    action: str
    name: str
    type: str = "project"
    description: str = ""
    body: str = ""
    importance: int | None = None
    reason: str = ""


class MemoryReviewer(Protocol):
    """把「自上次 review 之后的新增内容」判成变更列表的一次小模型调用。"""

    async def review(
        self,
        *,
        scope_label: str,
        new_content: list[str],
        existing: list[str],
    ) -> list[MemoryChange]:
        ...


@dataclass(frozen=True)
class MemoryScope:
    """一个「人设 × 会话面」的记忆 scope。"""

    persona_id: str
    room_id: str | None
    memory_dir: Path
    scope: str
    label: str = "persona"

    @property
    def key(self) -> str:
        return (
            f"persona:{self.persona_id}"
            if self.room_id is None
            else f"persona:{self.persona_id}:room:{self.room_id}"
        )

    @property
    def is_group(self) -> bool:
        return self.room_id is not None


def make_scope(project_root: Path, persona_id: str, room_id: str | None) -> MemoryScope:
    return MemoryScope(
        persona_id=persona_id,
        room_id=room_id,
        memory_dir=paths.persona_memory_dir(project_root, persona_id, room_id),
        scope=paths.persona_scope_string(project_root, persona_id, room_id),
    )


class MemoryReviewService:
    """按 scope 合并/串行化的 review 队列 + 触发口径。"""

    def __init__(
        self,
        *,
        store: TeamStore,
        project_root: Path,
        config: MemoryConfig | None = None,
        reviewer: MemoryReviewer | None = None,
        judge=None,
        cost_ledger=None,
        delay_seconds: float = 0.0,
        on_cost: Callable[[object], None] | None = None,
    ) -> None:
        self._store = store
        self._project_root = Path(project_root)
        self._config = config or MemoryConfig()
        self._reviewer = reviewer
        self._judge = judge
        self._cost_ledger = cost_ledger
        self._delay_seconds = delay_seconds
        self._on_cost = on_cost
        self._tasks: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        #: 已排队的 scope key（合并语义：同一 scope 的多次触发只跑一次）。
        self._pending_marked: set[str] = set()
        #: 成本口径 ``1 + k``：``reviews`` 是 review 本身的小模型调用次数；
        #: ``llm_calls`` 是含判官在内的全部模型调用次数（``llm_calls - reviews``
        #: 即被去重判官命中的次数 k）。
        self.cost_counter = {"reviews": 0, "llm_calls": 0}

    # ------------------------------------------------------------------
    # 缺省装配（可注入替身）
    # ------------------------------------------------------------------

    def build_llm_parts(self, llm, model: str | None = None) -> None:
        """用注入的 ``llm`` 装配缺省的 reviewer 与去重判官（都走同一个成本回调）。"""
        if self._reviewer is None:
            self._reviewer = LLMMemoryReviewer(
                llm, model=model or self._config.review_model,
                on_usage=self.record_usage,
            )
        if self._judge is None:
            from agent.memory.dedup import MemoryDedupJudge

            self._judge = MemoryDedupJudge(
                llm=llm,
                recall_threshold=self._config.dedup_recall_threshold,
                on_usage=self.record_usage,
            )

    def record_usage(self, model, usage) -> None:
        """记录一次 loop 之外的模型调用（review 本身或去重判官）。"""
        self.cost_counter["llm_calls"] += 1
        if self._on_cost is not None:
            self._on_cost(model, usage)
        if self._cost_ledger is None:
            return
        self._cost_ledger.record(
            model=str(model or "unknown"),
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            session_id="memory-review",
            phase="memory_review",
            tool_name="MemoryReview",
            cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            cache_write_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        )

    # ------------------------------------------------------------------
    # scope 生命周期
    # ------------------------------------------------------------------

    def ensure_scope(self, scope: MemoryScope) -> None:
        """scope 建立时把进度初值定在**当前起点**（不回溯建库前的历史，控成本）。"""
        if not scope.is_group:
            return
        progress_path = scope.memory_dir / PROGRESS_FILENAME
        if progress_path.exists():
            return
        room = self._store.get_room(scope.room_id or "")
        if room is None:
            return
        self._write_progress(scope, self._store.read_room_log(room.id)[-1].seq
                             if self._store.read_room_log(room.id) else 0)

    def forget_scope(self, scope: MemoryScope) -> None:
        """scope 已被删除（级联）→ 丢弃排队中的 review，避免重建孤儿目录。"""
        self._pending_marked.discard(scope.key)
        task = self._tasks.pop(scope.key, None)
        if task is not None and not task.done():
            task.cancel()

    # ------------------------------------------------------------------
    # 触发
    # ------------------------------------------------------------------

    async def on_member_turn(
        self, *, room_id: str, persona_id: str, outcome: TurnOutcome
    ) -> None:
        """编排器的每回合回调：**仅实际发言**的回合触发（Decision 17 主触发）。"""
        if not self._config.review_enabled:
            return
        if not outcome.spoke:
            return
        self._queue(make_scope(self._project_root, persona_id, room_id))

    async def on_round_end(self, *, room_id: str) -> None:
        """轮次结束时的「落后补齐」（度量基准 = review 游标）。"""
        if not self._config.review_enabled:
            return
        self.compensate_lag(room_id)

    def compensate_lag(self, room_id: str) -> list[str]:
        """为 review 游标落后达到阈值的成员排一次 review；返回被补齐的 persona id。"""
        room = self._store.get_room(room_id)
        if room is None:
            return []
        entries = self._store.read_room_log(room_id)
        seq = entries[-1].seq if entries else 0
        threshold = self._config.review_group_lag
        lagging: list[str] = []
        for persona_id in room.members:
            scope = make_scope(self._project_root, persona_id, room_id)
            reviewed = self._read_progress(scope)
            if reviewed is None:
                continue      # 该 scope 还没建立（成员从未在此群发言）→ 不补齐
            if seq - reviewed >= threshold:
                lagging.append(persona_id)
                self._queue(scope)
        return lagging

    # ------------------------------------------------------------------
    # 队列（按 scope 合并 / 串行化）
    # ------------------------------------------------------------------

    def pending_keys(self) -> list[str]:
        return sorted(self._pending_marked)

    def _queue(self, scope: MemoryScope) -> None:
        self._pending_marked.add(scope.key)
        existing = self._tasks.get(scope.key)
        if existing is not None and not existing.done():
            return                    # 合并：同一个 scope 的多次触发只跑一次
        self._tasks[scope.key] = asyncio.create_task(self._run_key(scope))

    async def _run_key(self, scope: MemoryScope) -> None:
        lock = self._locks.setdefault(scope.key, asyncio.Lock())
        async with lock:              # 串行化：同一 scope 同时至多一次 review
            self._pending_marked.discard(scope.key)
            if self._delay_seconds:
                await asyncio.sleep(self._delay_seconds)
            try:
                await self.run_once(scope)
            except asyncio.CancelledError:
                raise
            except Exception:         # noqa: BLE001 - review 失败 SHALL NOT 中断轮次
                logger.exception("记忆 review 失败（已忽略，不影响轮次）: %s", scope.key)

    async def drain(self) -> None:
        """等待所有排队 review 结束（测试与关停用）。"""
        while True:
            tasks = [t for t in self._tasks.values() if not t.done()]
            if not tasks:
                return
            await asyncio.gather(*tasks, return_exceptions=True)

    async def aclose(self) -> None:
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        await self.drain()

    # ------------------------------------------------------------------
    # 单聊待 review 缓冲
    # ------------------------------------------------------------------

    def append_chat_message(self, scope: MemoryScope, text: str) -> None:
        """运行期向单聊 scope 追加消息时写入待 review 缓冲（与消息表下标解耦）。"""
        if not text:
            return
        scope.memory_dir.mkdir(parents=True, exist_ok=True)
        path = scope.memory_dir / PENDING_FILENAME
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")

    def read_pending(self, scope: MemoryScope) -> list[str]:
        path = scope.memory_dir / PENDING_FILENAME
        if not path.is_file():
            return []
        items: list[str] = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict) and data.get("text"):
                    items.append(str(data["text"]))
        return items

    def _rewrite_pending(self, scope: MemoryScope, remaining: list[str]) -> None:
        path = scope.memory_dir / PENDING_FILENAME
        if not remaining:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return
        scope.memory_dir.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for text in remaining:
                f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # 单次 review
    # ------------------------------------------------------------------

    async def run_once(self, scope: MemoryScope) -> str:
        """跑一次 review，返回出口：``dropped`` / ``empty`` / ``applied`` / ``failed``。"""
        if not scope.memory_dir.parent.exists():
            # scope 已被级联删除 → 丢弃（否则会重建孤儿目录与 reviewed.json）。
            return "dropped"
        if self._reviewer is None:
            return "failed"

        if scope.is_group:
            new_content, mark = self._read_group_new(scope)
        else:
            new_content, mark = self._read_chat_new(scope)
        if not new_content:
            return "empty"

        existing = self._existing_summaries(scope)
        try:
            changes = await self._reviewer.review(
                scope_label=scope.key, new_content=new_content, existing=existing
            )
        except Exception:  # noqa: BLE001 - review 失败不推进游标、不中断轮次
            logger.exception("记忆 review 调用失败: %s", scope.key)
            return "failed"

        self.cost_counter["reviews"] += 1
        if not isinstance(self._reviewer, LLMMemoryReviewer):
            # 注入的替身 reviewer 不会经 ``on_usage`` 报用量：这里补记「review 本身」
            # 这一次调用，使 ``1 + k`` 口径在替身装配下同样可观测。
            self.cost_counter["llm_calls"] += 1
        memory = self._memory_for(scope)
        for change in changes:
            try:
                await self._apply(memory, change)
            except Exception:  # noqa: BLE001 - 单条写回失败不影响其余
                logger.exception("记忆 review 写回失败: %s / %s", scope.key, change.name)

        # 写回**成功之后**才推进游标 / 清除已消费部分（Issue 38）。
        self._commit(scope, mark)
        return "applied"

    def _read_group_new(self, scope: MemoryScope) -> tuple[list[str], int]:
        room = self._store.get_room(scope.room_id or "")
        if room is None:
            return [], 0
        entries = self._store.read_room_log(room.id)
        reviewed = self._read_progress(scope)
        if reviewed is None:
            reviewed = entries[-1].seq if entries else 0
        fresh = [e for e in entries if e.seq > reviewed][: self._config.review_read_limit]
        if not fresh:
            return [], reviewed
        return [_render_entry(e, self._speaker_names()) for e in fresh], fresh[-1].seq

    def _read_chat_new(self, scope: MemoryScope) -> tuple[list[str], int]:
        items = self.read_pending(scope)
        limit = self._config.review_read_limit
        return items[:limit], min(len(items), limit)

    def _commit(self, scope: MemoryScope, mark: int) -> None:
        if scope.is_group:
            self._write_progress(scope, mark)
            return
        items = self.read_pending(scope)
        self._rewrite_pending(scope, items[mark:])

    # ------------------------------------------------------------------
    # 写回
    # ------------------------------------------------------------------

    async def _apply(self, memory: PersistentMemory, change: MemoryChange) -> None:
        if change.action == REMOVE_ACTION:
            memory.archive(change.name, change.reason or "memory review")
            return
        if change.action not in WRITE_ACTIONS:
            logger.warning("未知的记忆变更动作 %r，已跳过", change.action)
            return
        judge = self._judge
        if judge is not None:
            incoming = f"{change.name}: {change.description}\n{change.body}"
            candidates = memory.recall_similar(incoming)
            if candidates:
                judgment = await judge.judge(incoming, candidates)
                memory.apply_judgment(
                    type=change.type,
                    name=change.name,
                    description=change.description,
                    body=change.body,
                    importance=change.importance,
                    judgment=judgment,
                )
                return
        memory.save(
            type=change.type,
            name=change.name,
            description=change.description,
            body=change.body,
            importance=change.importance,
        )

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _memory_for(self, scope: MemoryScope) -> PersistentMemory:
        return PersistentMemory(
            self._project_root,
            memory_dir=scope.memory_dir,
            scope=scope.scope,
            label=scope.label,
        )

    def memory_for(self, scope: MemoryScope) -> PersistentMemory:
        """公开入口：web 层构建人设会话的工具注册表时要用同一个实例。"""
        return self._memory_for(scope)

    def _existing_summaries(self, scope: MemoryScope) -> list[str]:
        entries = self._memory_for(scope).load_entries()
        return [f"{e.name} ({e.type}): {e.description}" for e in entries]

    def _speaker_names(self) -> dict[str, str]:
        return {p.id: (p.name or p.id) for p in self._store.list_personas()}

    def _progress_path(self, scope: MemoryScope) -> Path:
        return scope.memory_dir / PROGRESS_FILENAME

    def _read_progress(self, scope: MemoryScope) -> int | None:
        path = self._progress_path(scope)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None
        value = data.get("reviewed") if isinstance(data, dict) else None
        return int(value) if isinstance(value, int) else None

    def _write_progress(self, scope: MemoryScope, reviewed: int) -> None:
        scope.memory_dir.mkdir(parents=True, exist_ok=True)
        self._progress_path(scope).write_text(
            json.dumps({"reviewed": int(reviewed)}, ensure_ascii=False),
            encoding="utf-8",
        )


@dataclass(frozen=True)
class _ZeroUsage:
    """占位用量：注入替身 reviewer 时用于记账调用次数（token 记 0）。"""

    input_tokens: int = 0
    output_tokens: int = 0


def _render_entry(entry: RoomEntry, names: dict[str, str]) -> str:
    if entry.kind == "system":
        return f"[system] {entry.text}"
    if entry.kind == "user":
        return f"User: {entry.text}"
    return f"{names.get(entry.speaker or '', entry.speaker or '')}: {entry.text}"


# ---------------------------------------------------------------------------
# 缺省 reviewer：一次独立小模型调用
# ---------------------------------------------------------------------------

_REVIEW_SYSTEM_PROMPT = (
    "You maintain the long-term memory of a single AI agent persona, scoped to "
    "one conversation surface. You are given the persona's current memory index "
    "and the new transcript since the last review. Return ONLY a JSON array of "
    "change objects with keys: action (\"add\" | \"update\" | \"supplement\" | "
    "\"conflict\" | \"remove\"), name (kebab-case slug), type (\"user\" | "
    "\"feedback\" | \"project\" | \"reference\"), description (one line), body "
    "(Markdown), importance (1-5), reason (short). Use \"add\" for genuinely new "
    "durable facts, \"update\" when new content supersedes an existing memory, "
    "\"supplement\" when it only adds detail, \"remove\" when an existing memory "
    "is no longer true. Return [] when nothing durable is worth remembering."
)


class LLMMemoryReviewer:
    """缺省 review 实现：一次 ``llm.chat`` 调用（可指定小模型）。"""

    def __init__(self, llm, model: str | None = None, on_usage=None) -> None:
        self._llm = llm
        self._model = model
        self._on_usage = on_usage

    async def review(
        self, *, scope_label: str, new_content: list[str], existing: list[str]
    ) -> list[MemoryChange]:
        from agent.message import Message

        user = (
            f"Memory scope: {scope_label}\n\n"
            f"Current memory index:\n"
            + ("\n".join(existing) if existing else "(empty)")
            + "\n\nNew transcript since the last review:\n"
            + "\n".join(new_content)
        )
        response = await self._llm.chat(
            messages=[
                Message(role="system", content=_REVIEW_SYSTEM_PROMPT),
                Message(role="user", content=user),
            ],
            tools=None,
            model=self._model,
        )
        if self._on_usage is not None:
            usage = getattr(response, "usage", None)
            if usage is not None:
                self._on_usage(self._model, usage)
        return parse_changes(response.content or "")


def parse_changes(text: str) -> list[MemoryChange]:
    """解析 review 的 JSON 数组，容忍 markdown 围栏与尾随文本。"""
    import re

    cleaned = (text or "").strip()
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match is None:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    changes: list[MemoryChange] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        action = str(item.get("action") or "").strip().lower()
        if not name or action not in (*WRITE_ACTIONS, REMOVE_ACTION):
            continue
        importance = item.get("importance")
        changes.append(MemoryChange(
            action=action,
            name=name,
            type=str(item.get("type") or "project"),
            description=str(item.get("description") or ""),
            body=str(item.get("body") or ""),
            importance=int(importance) if isinstance(importance, (int, float)) else None,
            reason=str(item.get("reason") or ""),
        ))
    return changes
