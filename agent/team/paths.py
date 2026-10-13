"""群聊板块的落点计算：workspace 级 team 目录 + 人设记忆 scope 目录。

两类落点的作用域**故意不同**（design Decision 14 / 7）：

- roster / 房间记录 / 房间日志落在 **workspace 级** ``<workspace>/.asterwynd/team/``
  ——与会话同域。若落在仓库哈希目录，用户切到另一个 allowlist workspace 时
  roster 里的会话 id 全部悬空。
- 人设记忆落在**项目哈希目录下的同级子树** ``<BASE>/<project-hash>/personas/...``
  ——与项目记忆**同级**而非嵌套。嵌在 ``<...>/memory/`` 内会与项目记忆目录的
  git 可逆写保护形成嵌套仓库（``_git_commit`` 的 ``git add -A`` 递归）。
"""
from __future__ import annotations

from pathlib import Path

from agent.memory import persistent as _persistent
from agent.memory.persistent import _compute_project_hash, _find_scope_root

#: workspace 级群聊数据的目录名（``<workspace>/.asterwynd/team``）。
TEAM_DIRNAME = "team"
#: 人设子树在项目哈希目录下的目录名（``<BASE>/<hash>/personas``）。
PERSONAS_DIRNAME = "personas"


# ---------------------------------------------------------------------------
# workspace 级落点
# ---------------------------------------------------------------------------

def team_dir(workspace_root: Path) -> Path:
    return Path(workspace_root) / ".asterwynd" / TEAM_DIRNAME


def roster_path(workspace_root: Path) -> Path:
    return team_dir(workspace_root) / "roster.json"


def rooms_dir(workspace_root: Path) -> Path:
    return team_dir(workspace_root) / "rooms"


def room_record_path(workspace_root: Path, room_id: str) -> Path:
    return rooms_dir(workspace_root) / f"{room_id}.json"


def room_log_path(workspace_root: Path, room_id: str) -> Path:
    return rooms_dir(workspace_root) / f"{room_id}.jsonl"


# ---------------------------------------------------------------------------
# 人设记忆 scope 落点
# ---------------------------------------------------------------------------

def project_scope_base(project_root: Path) -> Path:
    """项目记忆的**父目录**：``<BASE>/<project-hash>``。

    与 ``PersistentMemory`` 的 ``memory_dir`` 同源（同一个 scope-root 解析与
    同一个 hash），因此 ``personas/`` 与 ``memory/`` 是同级目录。

    ``_MEMORY_DIR_BASE`` 通过**模块属性**读取（不在导入期快照）——测试用
    ``monkeypatch.setattr("agent.memory.persistent._MEMORY_DIR_BASE", ...)`` 隔离
    家目录时，导入期快照会让这里继续写真实家目录。
    """
    scope_root = _find_scope_root(Path(project_root))
    root = scope_root or Path(project_root).resolve()
    return _persistent._MEMORY_DIR_BASE / _compute_project_hash(root)


def project_scope_string(project_root: Path) -> str:
    """项目级 ``scope`` 取值（与 ``PersistentMemory.scope`` 的项目取值一致）。"""
    scope_root = _find_scope_root(Path(project_root))
    root = scope_root or Path(project_root).resolve()
    return str(root.resolve())


def persona_subtree(project_root: Path, persona_id: str) -> Path:
    """该人设的**整棵**记忆子树（删除人设时级联删除的对象）。"""
    return project_scope_base(project_root) / PERSONAS_DIRNAME / persona_id


def persona_memory_dir(
    project_root: Path, persona_id: str, room_id: str | None = None
) -> Path:
    """人设某个会话面的记忆目录。

    ``room_id is None`` → 单聊 scope ``personas/<pid>/chat/memory``；
    否则 → 群 scope ``personas/<pid>/rooms/<rid>/memory``。单聊与各群互不可见。
    """
    base = persona_subtree(project_root, persona_id)
    if room_id is None:
        return base / "chat" / "memory"
    return base / "rooms" / room_id / "memory"


def persona_room_subtree(project_root: Path, persona_id: str, room_id: str) -> Path:
    """该 (人设, 房间) 的记忆子树（删除房间时级联删除的对象）。"""
    return persona_subtree(project_root, persona_id) / "rooms" / room_id


def persona_scope_string(
    project_root: Path, persona_id: str, room_id: str | None = None
) -> str:
    """写入记忆 frontmatter 的 scope 取值。

    形如 ``<project-scope>:persona:<pid>``（单聊）/
    ``<project-scope>:persona:<pid>:room:<rid>``（群）。既有 ``scope`` 语义是不透明
    字符串（等值比较），冒号拼接不改变跨 scope 拒绝的判定。
    """
    base = project_scope_string(project_root)
    if room_id is None:
        return f"{base}:persona:{persona_id}"
    return f"{base}:persona:{persona_id}:room:{room_id}"
