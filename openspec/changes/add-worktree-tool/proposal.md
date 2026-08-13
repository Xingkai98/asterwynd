# Proposal: Agent 侧 worktree 隔离工具（对标 Claude Code EnterWorktree / ExitWorktree）

关联跟踪 issue：[#111](https://github.com/Xingkai98/asterwynd/issues/111)（【feature】Agent 侧 worktree 隔离工具，对标 Claude Code EnterWorktree/ExitWorktree）。

## Change Type

- primary: feature
- secondary: []

## 需求

1. 新增 `EnterWorktree` 工具：agent 在运行时自主创建 git worktree 隔离工作区，并将会话工作目录切换到该 worktree。
2. 新增 `ExitWorktree` 工具：agent 离开当前 worktree 回到主工作区，可选择保留或删除该 worktree。
3. 两个工具注册进 ToolRegistry，遵循现有工具协议（schema 暴露、权限元数据、结构化结果与错误码）。
4. worktree 内所有文件工具（Read/Write/Edit/Grep/Find/ListFiles/Bash 等）的路径边界自动重绑定到 worktree root。

## 背景

对标 Claude Code 内置的 `EnterWorktree` / `ExitWorktree` 工具（Claude Code 把 worktree 作为 agent 可调用的工具暴露，agent 可以在运行时自行创建工作区、切进切出）。

当前 Asterwynd 的 worktree 完全由外部编排层管理，agent 没有工具面：

- `scripts/workflow_state.py` 在 building 阶段强制要求先创建 worktree，否则 gate 拦截（`WORKTREE_REQUIRED_PHASES`）。
- `agent/main.py` 的 `run` / `benchmark` 命令提供 `--keep-worktrees` 选项，由 CLI/runner 在进程外部创建和清理 worktree。
- `benchmarks/agent_runner.py`、`benchmarks/gate.py` 在 benchmark 运行器层面管理 worktree。

这意味着 agent 无法在运行中自主决定"这次修改放在隔离工作区里做"；隔离是编排层的纪律，不是 agent 的能力。作为 coding agent 系统，把 worktree 隔离做成工具面能力，既补齐与主流 coding agent（Claude Code 等）的工具对齐，也让面试叙事中"工具调用 + 工作区安全"的能力线有直接证据。

## 非目标

- 不改动外部编排层现有 worktree 机制（workflow 状态机 building 强制、benchmark runner、`--keep-worktrees` 保持现状）。
- 不做 worktree 生命周期自动回收策略（如按会话结束统一清理）——本次只做 agent 显式创建/退出。
- 不做 TUI / Web UI 的 worktree 展示入口。
- 不引入远程 worktree（bare repo / 多机器场景）支持。

## 用户故事

- 用户让 agent "在隔离 worktree 里改这个 bug 并验证"。agent 调用 `EnterWorktree` 创建隔离工作区，在 worktree 内完成修改、跑测试，然后 `ExitWorktree` 返回主工作区汇报。
- agent 在自主开发流程中判断当前改动有冲突风险，主动切到 worktree 隔离试验，失败时 `ExitWorktree(keep=false)` 丢弃。

## 行为定义

### EnterWorktree

- 输入：`name`（worktree 名，生成分支名与目录名）、可选 `base_branch`（缺省为当前分支）。
- 前置条件：当前工作区是 git 仓库，且当前不在任何 worktree 中（禁止嵌套）。
- 行为：`git worktree add` 创建 worktree；将会话工作目录切换到新 worktree；WorkspacePolicy 的 root 重绑定到新 worktree。
- 输出：worktree 路径、分支名、状态说明。
- 错误：非 git 仓库、已在 worktree 中、worktree 创建失败（分支冲突、路径冲突等），返回结构化错误，工作目录保持不变。

### ExitWorktree

- 输入：`keep: boolean`（缺省 true，保留 worktree；false 时删除 worktree，分支保留）。
- 前置条件：当前处于某个 worktree 中。
- 行为：将会话工作目录切回主工作区；WorkspacePolicy root 重绑定回主工作区；`keep=false` 时执行 worktree 删除清理（含未提交改动时拒绝删除，保持原状态，不使用 `--force`）。
- 输出：主工作区路径、清理结果。
- 错误：不在 worktree 中、删除失败（存在未提交改动且 keep=false），返回结构化错误，状态不变。

## 验收

- `EnterWorktree` / `ExitWorktree` 已注册进 ToolRegistry，schema 可从 `get_all_schemas()` 获取。
- 单测 + 集成测试（真实临时 git 仓库）覆盖：创建进入、退出保留、退出删除、非 git 仓库拒绝、嵌套拒绝、失败回滚（工作目录不变）。
- worktree 内文件工具路径边界正确重绑定（越界读写被拒）。
- 工具调用遵循权限元数据（dangerous=False + MEDIUM）与结构化错误码约定（5 个新码）。
- 至少一个 benchmark smoke 通过（注册 + schema 暴露 + 编排层 worktree 内被拒错误路径）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| Tool system | 新增 2 个 builtin 工具注册进 ToolRegistry；权限元数据已定：dangerous=False + WORKSPACE_WRITE（MEDIUM），不限制 allowed_modes |
| Workspace safety | WorkspacePolicy root 原地重绑定（可变属性更新，不做 os.chdir）；主模式 DEFAULT_DENIED_PATTERNS 增加 `.asterwynd/worktrees/**` |
| AgentLoop | 会话"当前目录"由 policy root 驱动；工具仅对主 checkout 会话有效（编排层 worktree 内被拒） |
| CLI | 不改动现有 `--keep-worktrees` 行为 |
| Benchmark | 运行器现有 worktree 管理保持现状；smoke 验证注册 + schema 暴露 + 被拒错误路径 |
| Specs | `openspec/specs/tool-system/spec.md` 合入 worktree 工具要求 |
| Tests | 工具单测、集成测试、AgentLoop 层测试、benchmark smoke |
| Docs | 架构说明、开发指南、工具文档、面试讲稿（如涉及新能力线） |
| Migration / compatibility | 无现有行为变更，纯新增工具 |
| 明确不受影响 | Web UI、TUI、配置格式、MCP 集成、记忆系统 |

## Reference Implementation Research

- status: enabled
- reason: Claude Code 内置 `EnterWorktree` / `ExitWorktree` 工具是直接参考实现；本地参考仓库不可用（`.dev/reference-repos.txt` 不存在，已确认工作区无可用参考仓库），改为以 Claude Code 工具公开行为（本会话环境中可直接观察）和公开文档作为依据。
- research questions:
  - Claude Code 的 worktree 目录约定、分支命名和退出语义（keep / remove）是什么？
  - 嵌套 worktree、非 git 仓库、已有未提交改动等边界行为如何？
  - 会话工作目录切换如何与文件工具路径边界联动？
- findings:
  - Claude Code 将 worktree 创建在 `.claude/worktrees/<name>`，分支按 worktree 名派生；`EnterWorktree` 创建并切换，`ExitWorktree` 支持 keep / remove；禁止嵌套。
  - worktree 内所有工具（Read/Write/Bash 等）的 cwd 随会话切换，隔离是工作区级的。
- design impact:
  - Asterwynd 采用 `.asterwynd/worktrees/<name>` 目录约定（分支名 = name，2026-08-07 用户确认，见 design.md D2）与 keep/remove 退出语义（keep=false 不删分支）。
  - 隔离通过"WorkspacePolicy root 原地重绑定"实现（不做进程级 os.chdir），不修改单个文件工具。
  - 嵌套限制、非 git 仓库拒绝作为显式错误路径写入 spec。
  - 工具仅对主 checkout 会话有效：编排层 worktree 内（building 强制、benchmark runner）EnterWorktree 前置条件不满足被拒。

## 测试计划

- 单元测试：工具参数校验、错误路径、keep 语义。
- 集成测试：真实临时 git 仓库中的创建/进入/退出/删除全流程；文件工具路径边界重绑定。
- AgentLoop 层：工具调用后 cwd 状态正确、失败回滚。
- Benchmark：涉及 coding tools 核心路径，至少一个 benchmark smoke。
