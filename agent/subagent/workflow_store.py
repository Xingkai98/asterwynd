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
from pathlib import Path

from agent.artifact_store import (
    DEFAULT_READ_LIMIT,
    MAX_READ_LIMIT,
    RESULT_REF_PREFIX,
    WORKFLOW_KIND,
    ArtifactReader,
    ArtifactRef,
    atomic_write,
)
from agent.artifact_store import validate_segment as _validate_segment

# 兼容别名：既有读者（``workflow_assets``、测试）按这些旧名导入。
__all__ = [
    "RESULT_REF_PREFIX",
    "DEFAULT_READ_LIMIT",
    "MAX_READ_LIMIT",
    "WorkflowStore",
]


class WorkflowStore(ArtifactReader):
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

        委托共享的 ``ArtifactRef.parse``（单一前缀解析源，D4），因此**同时**拒绝
        ``artifact://agent/...``——workflow store 的 ``path_for`` 只认自己的作用域。
        严格白名单 + **段级**校验：只接受单段 ``workflow_id`` + 单段 ``key``，字符集
        受限，且 ``.`` / ``..`` 这类路径段被显式拒绝。
        """
        parsed = ArtifactRef.parse(ref)
        if parsed.kind != WORKFLOW_KIND:
            raise ValueError(f"not a workflow result ref: {ref!r}")
        return parsed.scope_id, parsed.key

    def ref(self, key: str) -> str:
        _validate_segment(key, "result key")
        return f"{RESULT_REF_PREFIX}{self.workflow_id}/{key}"

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, ref: str) -> Path:
        """ref -> 磁盘路径；拒绝任何逃出本地 subtree 的解析结果。"""
        parsed = ArtifactRef.parse(ref)
        if parsed.kind != WORKFLOW_KIND or parsed.scope_id != self.workflow_id:
            raise ValueError(
                f"ref {ref!r} belongs to {parsed.kind} {parsed.scope_id!r}, "
                f"not workflow {self.workflow_id!r}"
            )
        base = (self._root / "results").resolve()
        candidate = (base / f"{parsed.key}.txt").resolve()
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

    def save_attribution(self, key: str, payload: dict) -> str:
        """落盘四维成本归因快照（change ``workflow-budget-attribution``，D7/Q15）。

        ``key`` 约定传 ``workflow_id``（与 ``save_result`` 的 key 命名空间同层，但
        文件名带 ``.attribution`` 后缀避免撞 ``attribution`` 槽名）。父 agent 通过
        ``GetWorkflow(detail="attribution")`` 拿 ref、再用 ``ReadWorkflowResult`` 读回。
        """
        ref = self.ref(f"{key}.attribution")
        self._atomic_write(
            self.path_for(ref), json.dumps(payload, ensure_ascii=False, indent=2)
        )
        return ref

    def append_event(self, event: dict) -> None:
        """追加一条权威事件（``events.jsonl``，每行一个 JSON 对象）。"""
        path = self._root / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line)

    # -- 读取（``load`` / ``read`` 由 ``ArtifactReader`` 提供）------------------

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
        """兼容别名（``workflow_assets`` 等既有读者）——实现见 ``artifact_store``。"""
        atomic_write(path, text)
