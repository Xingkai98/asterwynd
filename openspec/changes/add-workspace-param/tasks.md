# Tasks: add-workspace-param

## 依赖顺序

```
1. WorkspacePolicy 扩展 + 安全校验
         ↓
2. CLI --workspace 参数 + 传递链
         ↓
3. Web 传递链
         ↓
4. /session-workspace slash command
         ↓
5. Path.cwd() 替换
         ↓
6. 测试
```

## 任务

### T1: WorkspacePolicy 扩展 ✅
- [x] `additional_roots: set[Path]` 字段
- [x] `add_root(path, create=False)` — 安全校验 + 添加
- [x] `remove_root(path)` — 删除（保护主 workspace_root）
- [x] `is_within_workspace()` — 扩展为多路径检查
- [x] `_validate_root(path)` — 拒绝名单/祖先检查/symlink 消除

### T2: CLI --workspace 参数 ✅
- [x] typer callback 加 `--workspace` 选项
- [x] 路径解析: `expanduser().resolve()`
- [x] 路径不存在 → 报错退出
- [x] 传递到 `_build_agent_core(workspace_root=...)`

### T3: Web 传递链 ✅
- [x] `create_app(workspace_root=...)` — web/server.py
- [x] `SessionManager.__init__(workspace_root=...)` — web/session.py
- [x] `_create_session()` 传入 `WorkspacePolicy(workspace_root=...)`

### T4: /session-workspace slash command ✅
- [x] 注册到 registry.py (handler 闭包)
- [x] `/session-workspace add <path>` — 调用 `policy.add_root(path, create=True)`
- [x] `/session-workspace remove <path>` — 调用 `policy.remove_root(path)`
- [x] `/session-workspace list` — 展示所有 workspace 及状态

### T5: Path.cwd() 替换 ✅
- [x] `_get_session_store(workspace_root=...)` 替代 `Path.cwd()`
- [x] `_build_agent_core(workspace_root=...)`
- [x] session 命令均加 `--workspace` 支持
- [x] 其他硬编码点

### T6: 测试 ✅
- [x] `test_workspace_policy.py` (60 tests, 21 new) — add_root 安全校验（正常/敏感/祖先/symlink）
- [x] import 验证通过 — CLI --workspace 参数解析
- [x] import 验证通过 — slash command 增删列
- [x] 全量回归 (189 passed)

### T0: 设计追问 (已完成)
- [x] /grill-with-docs 追问需求边界
- [x] 安全防护设计确认

### T6.1: Benchmark smoke
- [x] `uv run asterwynd benchmark (CI 已通过) benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`

### T7: Spec sync (closing phase)
- [x] 将 delta spec 同步到 `openspec/specs/cli/spec.md`, `openspec/specs/web-ui/spec.md`, `openspec/specs/workspace-safety/spec.md`
