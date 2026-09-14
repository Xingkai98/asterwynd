"""Workflow 结果落盘 + 事件日志（change ``workflow-result-aggregation``，D1/D4）。

设计口径来自 ``design.md`` D1/D4 与 ``reviews/grill-design.md`` 决策 1/2/3：

- **独立 subtree**：结果是 ``<workspace_root>/.asterwynd/workflows/<workflow_id>/``，
  **不复用** ``SubagentSnapshotStore`` 的 ``.asterwynd/subagents/`` 命名空间。
  ``SubagentSnapshotStore.remove()`` 直接透传 ``SessionStore.remove()``，后者是
  ``shutil.rmtree(session_dir)``（``agent/session.py``）——同一个 ``run_id`` 既放
  checkpoint 又放 result artifact 时，一次「清理 checkpoint」会静默销毁
  ``result_ref`` 指向的文件，而 ``result_ref`` 是**跨进程可解析**的承诺。
- **不做 dedup skip**：``SessionStore.save()`` 内容不变时直接返回 False 不落盘，
  「写完再读」会看到文件不存在。这里每次写都是真实写盘。
- **每 key 独立文件 + 原子写**（design.md Risks）：并发节点各写各的文件，
  ``tmp + os.replace`` 保证读者永远看不到半截文件。
- **事件日志是权威源**（D4）：节点/工作流终态迁移写 ``events.jsonl``，
  MessageBus 只做低延迟广播，丢消息不影响结果正确性。
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

RESULT_REF_PREFIX = "artifact://workflow/"

#: 一次 ``read`` 默认/最大返回的字符数（分页读，避免把 artifact 正文整段灌进上下文）。
DEFAULT_READ_LIMIT = 4000
MAX_READ_LIMIT = 20000

_ALLOWED_REF_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
)

#: 被禁止的路径段：``.`` / ``..`` 会让 ``<ws>/.asterwynd/workflows/<id>`` 跳出 subtree。
#: 必须在**段级**拒绝——字符白名单允许 ``.``（``run_a.summary`` 这类键依赖它），
#: 只靠「两段」校验会漏掉 ``artifact://workflow/../leak``（恰好两段）。
_FORBIDDEN_SEGMENTS = frozenset({".", ".."})


def _validate_segment(value: str, label: str) -> str:
    """校验一个 ref 路径段：非空、字符集受限、且不是 ``.`` / ``..``。"""
    if not value or set(value) - _ALLOWED_REF_CHARS or value in _FORBIDDEN_SEGMENTS:
        raise ValueError(f"invalid {label}: {value!r}")
    return value


class WorkflowStore:
    """一个 workflow run 的结果 artifact + 事件日志（独立于 checkpoint 命名空间）。"""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self.workflow_id = self._root.name

    @classmethod
    def for_workspace(cls, workspace_root: str | Path, workflow_id: str) -> "WorkflowStore":
        # workflow_id 直接拼进路径，所以它必须自己就是合法段（否则 ``..`` 会让 root
        # 跳到 ``<ws>/.asterwynd``）。
        _validate_segment(workflow_id, "workflow_id")
        return cls(Path(workspace_root) / ".asterwynd" / "workflows" / workflow_id)

    # -- ref 编解码 ----------------------------------------------------------

    @staticmethod
    def parse_ref(ref: str) -> tuple[str, str]:
        """把 ``artifact://workflow/<workflow_id>/<key>`` 拆成两段，非法即拒绝。

        严格白名单 + **段级**校验：只接受单段 ``workflow_id`` + 单段 ``key``，字符集
        受限，且 ``.`` / ``..`` 这类路径段被显式拒绝。绝对路径、多余层级同样在解析层
        被拒（不会拼出逃逸路径）。
        """
        if not isinstance(ref, str) or not ref.startswith(RESULT_REF_PREFIX):
            raise ValueError(f"not a workflow result ref: {ref!r}")
        rest = ref[len(RESULT_REF_PREFIX) :]
        parts = rest.split("/")
        if len(parts) != 2:
            raise ValueError(f"malformed workflow result ref: {ref!r}")
        workflow_id, key = parts
        _validate_segment(workflow_id, "workflow_id")
        _validate_segment(key, "key")
        return workflow_id, key

    def ref(self, key: str) -> str:
        _validate_segment(key, "result key")
        return f"{RESULT_REF_PREFIX}{self.workflow_id}/{key}"

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, ref: str) -> Path:
        """ref -> 磁盘路径；拒绝任何逃出本地 subtree 的解析结果。"""
        workflow_id, key = self.parse_ref(ref)
        if workflow_id != self.workflow_id:
            raise ValueError(
                f"ref {ref!r} belongs to workflow {workflow_id!r}, not {self.workflow_id!r}"
            )
        base = (self._root / "results").resolve()
        candidate = (base / f"{key}.txt").resolve()
        if base not in candidate.parents:
            raise ValueError(f"ref {ref!r} escapes the workflow store")
        return candidate

    # -- 写入 ---------------------------------------------------------------

    def save_result(self, key: str, text: str) -> str:
        """落盘完整结果正文，返回 ``result_ref``。"""
        ref = self.ref(key)
        self._atomic_write(self.path_for(ref), text)
        return ref

    def save_summary(self, key: str, text: str) -> str:
        """落盘 bounded summary（本 change 的 token 预算裁剪件）。"""
        ref = self.ref(f"{key}.summary")
        self._atomic_write(self.path_for(ref), text)
        return ref

    def save_transcript(self, key: str, messages: list[dict]) -> str:
        """落盘完整 messages 序列（transcript）。"""
        ref = self.ref(f"{key}.transcript")
        self._atomic_write(
            self.path_for(ref), json.dumps(messages, ensure_ascii=False, indent=2)
        )
        return ref

    def append_event(self, event: dict) -> None:
        """追加一条权威事件（``events.jsonl``，每行一个 JSON 对象）。"""
        path = self._root / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line)

    # -- 读取 ---------------------------------------------------------------

    def load(self, ref: str) -> str | None:
        """按 ref 读回全文；文件不存在或不可读时返回 ``None``。"""
        try:
            return self.path_for(ref).read_text(encoding="utf-8")
        except (OSError, ValueError):
            return None

    def read(
        self,
        ref: str,
        *,
        offset: int = 0,
        limit: int = DEFAULT_READ_LIMIT,
    ) -> dict:
        """分页读正文（字符偏移），返回自描述的页对象。"""
        start = max(int(offset), 0)
        size = max(1, min(int(limit), MAX_READ_LIMIT))
        text = self.load(ref)
        if text is None:
            return {
                "ref": ref,
                "missing": True,
                "offset": start,
                "limit": size,
                "total_chars": 0,
                "truncated": False,
                "content": "",
            }
        content = text[start : start + size]
        return {
            "ref": ref,
            "missing": False,
            "offset": start,
            "limit": size,
            "total_chars": len(text),
            "truncated": start + len(content) < len(text),
            "content": content,
        }

    def read_events(self) -> list[dict]:
        """读回全部事件；半行/损坏行跳过（日志不应因一行损坏整体不可用）。"""
        path = self._root / "events.jsonl"
        if not path.is_file():
            return []
        events: list[dict] = []
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return events
        return events

    # -- 内部 ---------------------------------------------------------------

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        """tmp + os.replace：读者永远看不到半截文件，重复写也一定是真实写。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex[:8]}")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
