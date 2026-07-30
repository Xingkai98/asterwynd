# Design: add-workspace-param

## 模型

```
--workspace /home/project-a    →  主 workspace_root
                                    ├── ASTER.md, .asterwynd/, config, sessions
                                    └── 所有工具默认边界

/session-workspace add /tmp/data  →  additional_roots += /tmp/data
                                    →  工具多一张读写通行证
                                    →  不参与任何管理逻辑
```

## 改动清单

### 1. WorkspacePolicy 扩展 (`agent/workspace_policy.py`)

```python
class WorkspacePolicy:
    workspace_root: Path
    additional_roots: set[Path]      # NEW

    def add_root(self, path: str):   # NEW — 带安全校验
        # realpath → 拒绝名单 → 祖先检查 → 去重
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise WorkspaceError("路径不存在，创建失败: ...") if not create else os.makedirs
        if self._is_within(resolved, self.workspace_root):
            raise WorkspaceError("已在主 workspace 范围内")
        if self._is_within(self.workspace_root, resolved):
            raise WorkspaceError("不能添加主 workspace 祖先目录")
        deny = {Path("/etc"), Path("/proc"), Path("/sys"), Path("/dev"),
                Path("/root"), Path("/boot")}
        for d in deny:
            if resolved == d or self._is_within(d, resolved):
                raise WorkspaceError("禁止添加系统敏感目录")
        self.additional_roots.add(resolved)

    def remove_root(self, path: str):
        self.additional_roots.discard(Path(path).expanduser().resolve())

    def is_within_workspace(self, path: Path) -> bool:
        # 原来只检查 workspace_root → 现在也检查 additional_roots
        return (self._is_within(self.workspace_root, path) or
                any(self._is_within(r, path) for r in self.additional_roots))
```

### 2. CLI --workspace (`agent/main.py`)

```python
@app.callback(invoke_without_command=True)
def callback(..., workspace: str = typer.Option(None, "--workspace", help="主工作目录")):
    ...

# _build_agent_core 加参数
def _build_agent_core(..., workspace_root: Path | None = None):
    wp = WorkspacePolicy(workspace_root=workspace_root or Path.cwd())
    ...

# web 命令
@app.command()
def web(..., workspace: str = None):
    app = create_app(..., workspace_root=resolve_path(workspace))
```

### 3. Web 传递链 (`web/server.py` + `web/session.py`)

```
web command → create_app(workspace_root=...) → SessionManager(workspace_root=...) → _create_session() → WorkspacePolicy(workspace_root=...)
```

### 4. Slash Command (`/session-workspace`)

新增工具 `agent/tools/builtin/session_workspace.py`：

```
/session-workspace add <path>    →  policy.add_root(path, create=True)
/session-workspace remove <path> →  policy.remove_root(path)
/session-workspace list          →  [workspace_root, *additional_roots]
```

### 5. Path.cwd() 替换

| 位置 | 替换为 |
|------|--------|
| `_load_cli_config()` config search | `start_dir=workspace_root` |
| `_sessions_root()` caller | `workspace_root` (已有参数) |
| `PersistentMemory(project_root=)` | `workspace_root` (已有参数) |
| `BuildContext(cwd=)` | `workspace_root` |
| `RuntimeFingerprint.cwd` | `workspace_root` |
| `SkillRuntime.from_roots()` | `workspace_root / "skills"` |
| `uploads.py` base dir | `workspace_root / ".asterwynd" / "uploads"` |

## ADR

### ADR-1: 附加 workspace 不参与管理

**决策**: 附加 workspace 只扩展 `WorkspacePolicy` 的读写边界，不触发 config 加载、ASTER.md 读取、session 创建等管理行为。

**备选**: 完整多 workspace（每个加载自己的 ASTER.md + config）。

**拒绝原因**: 复杂度远超收益。真正的"项目切换"通过重启 `asterwynd --workspace /other` 实现更合理。

### ADR-2: add 时做安全校验，不在运行时每次检查

**决策**: 敏感目录拒绝在 `add_root()` 时执行一次，不在工具调用时每文件检查。

**拒绝理由**: 运行时每文件检查性能开销大，且 add 时已用 `realpath` 消除 symlink 绕过。

## Context
当前 `asterwynd` CLI 和 Web 启动时工作目录固定为进程 cwd，无法指定。`WorkspacePolicy` 已支持 `workspace_root` 参数但未被使用（10+ 处硬编码 `Path.cwd()`）。

## Goals / Non-Goals
**Goals**: CLI `--workspace` 参数指定主工作目录；session 中动态增删附加 workspace；安全防护。
**Non-Goals**: 多 ASTER.md 加载；跨 session 持久化；细粒度权限控制。

## Decisions
- ADR-1: 附加 workspace 不参与管理（只扩展读写边界）
- ADR-2: add 时做安全校验，运行时复用现有 assert_within_workspace
- D1-D6: 见 wayfinding-map.md

## Pre-Implementation Review
子 Agent 审阅通过（verdict: CHANGES_REQUESTED, 0 BLOCKED）。阻塞项已修复。

## Risks / Trade-offs
- 改动点分散（10+ 处），回归风险中等 → T6 全量测试覆盖
- Bash 绕过 guard（python3 script.py 写文件）→ Layer 3 Gate 兜底

## Testing Strategy
- T1 单元测试: WorkspacePolicy add_root 安全校验
- T4 集成测试: /session-workspace slash command
- T2 端到端: CLI --workspace 参数
- T6 全量回归
