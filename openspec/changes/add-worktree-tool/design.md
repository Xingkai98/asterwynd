# Design: Agent 侧 worktree 隔离工具

## Context

对标 Claude Code 内置的 `EnterWorktree` / `ExitWorktree` 工具：Claude Code 把 worktree 作为 agent 可调用的工具暴露，agent 可以在运行时自行创建隔离工作区、切进切出。

当前 Asterwynd 的 worktree 完全由外部编排层管理，agent 没有工具面：

- `scripts/workflow_state.py` 的 `WORKTREE_REQUIRED_PHASES = {"building"}` 在 building 阶段强制要求先创建 worktree，否则 gate 拦截。
- `agent/main.py` 的 `run` / `benchmark` 命令提供 `--keep-worktrees` 选项，由 CLI 在进程外部创建和清理 worktree。
- `benchmarks/agent_runner.py`、`benchmarks/gate.py` 在 benchmark 运行器层面管理 worktree。

工具面现状：

- `agent/tools/builtin/` 存放 builtin 工具（Read/Write/Edit/Grep/Find/ListFiles/Bash/InspectGitDiff 等），注册进 `agent/tools/registry.py` 的 ToolRegistry；权限元数据由 `agent/tools/governance/`（ModePolicy 等）管理。
- 工作区安全边界由 `agent/workspace_policy.py` 的 WorkspacePolicy 提供，文件类工具通过工具集合注入 workspace policy。
- git 操作目前通过 Bash 工具暴露给 agent，没有独立的 git 工具层。

需求：新增 `EnterWorktree` / `ExitWorktree` 工具，让 agent 在运行时自主创建、进入和退出 git worktree 隔离工作区；进入后所有文件工具的路径边界自动切换到 worktree root（工作区级隔离）。

## Goals / Non-Goals

### Goals

- 提供 `EnterWorktree` / `ExitWorktree` 两个 builtin 工具，注册进 ToolRegistry，schema 可从 `get_all_schemas()` 获取。
- 隔离是工作区级的：进入 worktree 后，所有文件工具（Read/Write/Edit/Grep/Find/ListFiles/Bash 等）的路径边界自动重绑定到 worktree root。
- 工具遵循现有协议：schema 暴露、权限元数据（危险等级、mode 可见性）、结构化结果与 `error_type` 错误码。
- 失败回滚：任何失败路径下会话工作目录与 policy root 保持不变。

### Non-Goals

- 不改动外部编排层现有 worktree 机制（workflow 状态机 building 强制、benchmark runner、`--keep-worktrees`）。
- 不做 worktree 生命周期自动回收策略（如按会话结束统一清理）。
- 不做 TUI / Web UI 的 worktree 展示入口。
- 不引入远程 worktree（bare repo / 多机器场景）支持。

## Decisions

### D1: 工具实现位置与形态

新增 `agent/tools/builtin/worktree.py`，包含 `EnterWorktreeTool` 与 `ExitWorktreeTool` 两个 Tool 子类，在 builtin 注册路径统一注册。采用双工具形态（而非单个带 action 参数的管理工具）：与 Claude Code 工具对齐、schema 暴露直观。

### D2: EnterWorktree 语义

- 参数：`name`（必填，worktree 名，用于派生目录与分支）、`base_branch`（可选，缺省当前分支）。
- 前置校验：
  - 当前工作区是 git 仓库（`git rev-parse --is-inside-work-tree`）；
  - 当前不在任何 worktree 中（`git worktree list` 中 cwd 位于主工作区）——禁止嵌套。
- 执行：`git worktree add -b <branch> <path> <base_branch>`；目录与分支命名约定待 grill 收敛（候选目录 `.claude/worktrees/<name>`，分支 `<name>` 或 `<change-id>/<YYYY-MM-DD>` 风格）。
- 切换：会话工作目录切换到新 worktree；WorkspacePolicy root 重绑定到 worktree 路径。
- 输出：`{"worktree": "<path>", "branch": "<branch>"}`。
- 失败回滚：已创建的 worktree 删除，cwd 与 policy root 保持不变。

### D3: ExitWorktree 语义

- 参数：`keep`（布尔，缺省 true）。
- 前置校验：当前 cwd 位于某个 worktree 中。
- 执行：会话工作目录切回主工作区；WorkspacePolicy root 重绑定回主工作区；`keep=false` 时先检查 worktree 内无未提交改动，再 `git worktree remove`（含未提交改动时拒绝，不使用 `--force` 静默丢弃）。
- 输出：`{"workspace": "<主工作区路径>", "removed": bool}`。
- 失败：不在 worktree 中、删除被拒（未提交改动）返回结构化错误，状态不变。

### D4: 会话工作目录切换的承载点（开放，grill 收敛）

- 会话 cwd 状态存放层（AgentLoop 会话状态 / ToolContext / WorkspacePolicy 内部）待确认——需先读 `agent/tools/base.py` 与 AgentLoop 的 tool 调用链确认现有机制。
- WorkspacePolicy root 重绑定 API（重建实例 vs 原地更新 root）待确认——取决于 policy 注入方式。
- 切换作用域（会话级 vs 全局）待确认——需避免与并发/子 agent 隔离冲突。

### D5: 权限元数据

- 危险等级：写入型 + git 操作，倾向 dangerous 或独立等级（待 grill 与 `tool-governance` 能力域对齐）。
- mode 可见性：是否所有模式可用待确认。

### D6: 错误处理

所有错误路径返回结构化 ToolResult，`error_type` 打标（候选：`not_a_git_repo` / `already_in_worktree` / `worktree_create_failed` / `not_in_worktree` / `worktree_remove_failed`，取值与现有约定对齐），text 为中文说明。错误后 cwd 与 policy root 保持不变。

### D7: 与现有机制的关系

- workflow 状态机 building 阶段的强制 worktree 是编排层纪律；工具化后 agent 自主创建的 worktree 与其并行共存（worktree 列表以 git 为准），互不干扰。
- benchmark runner 保持现状，不改为调用工具。
- 目录约定考虑前缀隔离，避免与编排层 worktree 命名冲突。

## Pre-Implementation Review

开发前必须完成 `batch-grill-me` 设计追问并在此记录结果。立项阶段已解决/已记录的要点：

- 已确定：双工具形态、工作区级隔离（cwd 切换 + policy root 重绑定）、keep/remove 退出语义、失败回滚原则、结构化错误码方向。
- 已否决：Bash 包装（无结构化状态、无 policy 重绑定）、外部编排层扩展（不解决 agent 自主性）。
- 待确认（见 Open Questions）：cwd 切换承载点与作用域、policy 重绑定 API、目录/分支命名约定、权限元数据与 mode 可见性、错误码枚举取值、删除未提交改动 worktree 的边界。
- 剩余风险：切换状态作用域与并发/子 agent 的冲突、回滚路径残留污染、与编排层 worktree 命名冲突、跨平台路径（当前以 linux 为准）。

## Open Questions

1. 会话 cwd 切换的承载点与作用域（AgentLoop 会话状态 / ToolContext / WorkspacePolicy 内部）。
2. WorkspacePolicy root 重绑定 API 形状（重建 vs 原地更新）。
3. worktree 目录与分支命名约定（`.claude/worktrees/<name>` 等候选）。
4. 权限元数据：危险等级与 mode 可见性。
5. 失败回滚的原子性边界（worktree add 成功后 cwd 切换失败的处理）。
6. 错误码枚举与现有 `error_type` 约定对齐。

## Risks / Trade-offs

- **切换状态作用域风险**：工作目录切换若承载在易变状态上，可能与并发/子 agent 隔离冲突——设计时确认作用域（会话级 vs 全局）。
- **残留污染风险**：worktree 创建失败时残留目录——回滚路径必须有测试覆盖。
- **命名冲突风险**：与外部编排层 worktree 命名冲突——目录约定确认时考虑前缀隔离。
- **跨平台**：当前平台 linux，代码避免硬编码路径分隔符，测试以 linux 为准。
- **替代方案权衡**：
  - Bash 包装（agent 用 Bash 执行 `git worktree add` 并自行 cd）：无结构化状态、无 policy 重绑定、无法保证边界安全——否决。
  - 外部编排层扩展（继续由 runner/CLI 创建并注入 worktree）：不解决 agent 自主性需求，工具对齐缺失——否决。
  - 单一 Worktree 管理工具（一个工具带 action 参数）：协议上可行，但与 Claude Code 双工具对齐差——备选，倾向双工具。

## Testing Strategy

- 单元测试：参数校验、错误路径、keep 语义、分支名派生。
- 集成测试：`tmp_path` 下初始化真实 git 仓库，跑创建→进入→（文件工具路径边界验证）→退出→删除全流程；嵌套/非仓库/未提交改动删除拒绝等负向路径。
- AgentLoop 层：工具调用后会话 cwd 与 policy root 状态断言；失败回滚断言。
- Benchmark：涉及工具协议与 workspace safety 核心路径，至少一个 benchmark smoke。
