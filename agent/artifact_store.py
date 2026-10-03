"""Agent 通用 artifact 存储（change ``tool-result-lifecycle``，D4）。

工具结果全文的「无损失落 + 按 ref 回读」落点。复用 ``WorkflowStore`` 的实现基因
（ref 格式族 / 原子写 / 分页读），作用域从 workflow 提升为 **agent 通用**。

身份寻址（design D4，对抗验证修正）：

- **根 agent 用 ``session_id``**——resume 时 ``session_id`` 不变、``run_id`` 新起，
  按 ``run_id`` 存会让 ref 在 resume 后悬空；
- **子 agent 用 ``run_id``**——``subagent_id`` 是 ``uuid4().hex[:8]`` 的进程内标识、
  不落盘；durable 身份是 ``run_id``（checkpoint 以 ``run_id`` 落盘、``resume_subagent``
  也按 ``run_id`` 取）。

落点 ``<workspace_root>/.asterwynd/artifacts/<scope_id>/``，**在 ``sessions/<id>/``
之外**：``SessionStore.remove()`` 是 ``shutil.rmtree(session_dir)``，artifacts 若在会话
目录内，一次「清理会话」会把跨进程可解析的 ref 静默销毁（``workflow_store.py`` 头注释
已记录同款坑）。

清理**显式实现**：``SessionStore.remove`` 追加删除 ``artifacts/<session_id>``。仓库当前
没有任何子 agent 归档清理路径，故子 agent 的 artifacts 清理同样由调用方显式触发
（``remove_results``）；不能依赖 ``_sessions`` 的清理，它永不清理。
"""
from __future__ import annotations

import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

ARTIFACT_SCHEME = "artifact://"
WORKFLOW_KIND = "workflow"
AGENT_KIND = "agent"

#: ``artifact://workflow/<workflow_id>/<key>``（既有）与 ``artifact://agent/<scope_id>/<key>``。
RESULT_REF_PREFIX = f"{ARTIFACT_SCHEME}{WORKFLOW_KIND}/"
AGENT_REF_PREFIX = f"{ARTIFACT_SCHEME}{AGENT_KIND}/"

#: 一次 ``read`` 默认/最大返回的字符数（分页读，避免把 artifact 正文整段灌进上下文）。
DEFAULT_READ_LIMIT = 4000
MAX_READ_LIMIT = 20000

ALLOWED_REF_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
)

#: 被禁止的路径段：``.`` / ``..`` 会让 ``<ws>/.asterwynd/<kind>/<id>`` 跳出 subtree。
#: 必须在**段级**拒绝——字符白名单允许 ``.``（``run_a.summary`` 这类键依赖它），
#: 只靠「段数」校验会漏掉 ``artifact://workflow/../leak``。
FORBIDDEN_SEGMENTS = frozenset({".", ".."})


def validate_segment(value: str, label: str) -> str:
    """校验一个 ref 路径段：非空、字符集受限、且不是 ``.`` / ``..``。"""
    if not value or set(value) - ALLOWED_REF_CHARS or value in FORBIDDEN_SEGMENTS:
        raise ValueError(f"invalid {label}: {value!r}")
    return value


def atomic_write(path: Path, text: str) -> None:
    """tmp + ``os.replace``：读者永远看不到半截文件，重复写也一定是真实写。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex[:8]}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def new_key(prefix: str = "result") -> str:
    """生成一个合法的 artifact key（segment 白名单内、进程内唯一）。"""
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


@dataclass(frozen=True)
class ArtifactRef:
    """解析后的 artifact ref：``(kind, scope_id, key)``。

    **单一解析入口**（design D4）：``WorkflowStore.parse_ref`` 与工具层路由都委托它，
    避免两套前缀解析各自漂移。
    """

    kind: str
    scope_id: str
    key: str

    @classmethod
    def parse(cls, ref: str) -> "ArtifactRef":
        if not isinstance(ref, str) or not ref.startswith(ARTIFACT_SCHEME):
            raise ValueError(f"not an artifact ref: {ref!r}")
        parts = ref[len(ARTIFACT_SCHEME):].split("/")
        if len(parts) != 3:
            raise ValueError(f"malformed artifact ref: {ref!r}")
        kind, scope_id, key = parts
        if kind not in (WORKFLOW_KIND, AGENT_KIND):
            raise ValueError(f"unknown artifact kind: {kind!r}")
        validate_segment(scope_id, f"{kind} id")
        validate_segment(key, "key")
        return cls(kind=kind, scope_id=scope_id, key=key)

    def to_ref(self) -> str:
        return f"{ARTIFACT_SCHEME}{self.kind}/{self.scope_id}/{self.key}"


#: 预览文本里内嵌的 ref 标记（``tool_result_policy`` 写入，回读侧解析）。
#: 形态与 ``_bounded_summary`` 的 ``[truncated; full result in result_ref]`` 同族，
#: 多带一个可解析的 ref（对抗验证 Q-new4：不加 ``Message`` 字段，ref 内嵌进正文）。
RESULT_REF_MARKER_RE = re.compile(
    r"\[truncated; full result in result_ref: (artifact://[^\s\]]+)\]"
)


def extract_result_ref(text: str) -> str | None:
    """从预览正文里抽回内嵌的 artifact ref；没有则 ``None``。"""
    if not isinstance(text, str):
        return None
    match = RESULT_REF_MARKER_RE.search(text)
    return match.group(1) if match else None


class ArtifactReader:
    """``load``/``read`` 的共同实现；子类只需提供 ``path_for``。

    ``WorkflowStore`` 与 ``AgentArtifactStore`` 的同名方法语义完全一致（分页读、
    缺失自描述），共享一份避免两处漂移。
    """

    def path_for(self, ref: str) -> Path:  # pragma: no cover - 子类实现
        raise NotImplementedError

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


class AgentArtifactStore(ArtifactReader):
    """一个 agent 作用域（根 ``session_id`` / 子 ``run_id``）的工具结果 artifact store。"""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self.scope_id = self._root.name

    @classmethod
    def for_workspace(cls, workspace_root: str | Path, scope_id: str) -> "AgentArtifactStore":
        validate_segment(scope_id, "scope_id")
        return cls(artifacts_root(workspace_root) / scope_id)

    def ref(self, key: str) -> str:
        validate_segment(key, "result key")
        return f"{AGENT_REF_PREFIX}{self.scope_id}/{key}"

    def path_for(self, ref: str) -> Path:
        """ref -> 磁盘路径；拒绝任何逃出本地 subtree 的解析结果。"""
        parsed = ArtifactRef.parse(ref)
        if parsed.kind != AGENT_KIND or parsed.scope_id != self.scope_id:
            raise ValueError(
                f"ref {ref!r} belongs to {parsed.kind} {parsed.scope_id!r}, "
                f"not {AGENT_KIND} {self.scope_id!r}"
            )
        base = (self._root / "results").resolve()
        candidate = (base / f"{parsed.key}.txt").resolve()
        if base not in candidate.parents:
            raise ValueError(f"ref {ref!r} escapes the artifact store")
        return candidate

    def save_result(self, key: str, text: str) -> str:
        """落盘完整结果正文，返回 ref。"""
        ref = self.ref(key)
        atomic_write(self.path_for(ref), text)
        return ref

    @staticmethod
    def remove_results(workspace_root: str | Path, scope_id: str) -> bool:
        """显式清理一个 agent 作用域的 artifacts；目录不存在返回 ``False``。

        ``_sessions`` 永不清理，故这里不能依赖任何后台 GC——调用方（会话删除 /
        子 agent 归档）必须显式调用。
        """
        try:
            validate_segment(scope_id, "scope_id")
        except ValueError:
            return False
        target = artifacts_root(workspace_root) / scope_id
        if not target.is_dir():
            return False
        shutil.rmtree(target)
        return True


def artifacts_root(workspace_root: str | Path) -> Path:
    """``.asterwynd/artifacts/``——与 ``sessions/<id>/`` 隔离（D4）。"""
    return Path(workspace_root) / ".asterwynd" / "artifacts"
