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

- 参数：`name`（必填，worktree 名，直接用作分支名并派生目录名）、`base_branch`（可选，缺省当前分支）。
- 前置校验：
  - 当前工作区是 git 仓库（`git rev-parse --is-inside-work-tree`）；
  - 当前不在任何 worktree 中：`git rev-parse --show-toplevel` 与 `git worktree list --porcelain` 首条目路径（resolve 归一化后）比对，一致才可进入——禁止嵌套。该判定在编排层 worktree（building 强制、benchmark runner）内也正确拒绝，是唯一防线（git 本身不阻止嵌套 add）。
- 目录与分支命名（grill + 用户确认）：目录 `.asterwynd/worktrees/<name>`（主工作区仓库内，`.gitignore` 已忽略 `.asterwynd/`），分支名 = `name`；执行 `git worktree add -b <name> <path> <base_branch>`。目标仓库应忽略 `.asterwynd/worktrees/`；主模式 DEFAULT_DENIED_PATTERNS 增加 `.asterwynd/worktrees/**`，主模式工具不可直接读写 worktree 内文件。
- 切换：仅重绑定共享 WorkspacePolicy 实例的 `workspace_root` 到 worktree 路径（见 D4），**不做进程级 `os.chdir`**。
- 输出：`{"worktree": "<path>", "branch": "<name>"}`。
- 失败回滚：add 失败时 git 自清理（branch 冲突 exit 255 无残留注册），工具显式 verify `git worktree list` 中无该 worktree，cwd 与 policy root 保持不变；add 成功后任何后续步骤失败，执行 `git worktree remove` 回滚（新 checkout 干净，无需 `--force`）。

### D3: ExitWorktree 语义

- 参数：`keep`（布尔，缺省 true）。
- 前置校验：当前位于某个 worktree 中（与 D2 相同判定：toplevel ≠ 主工作区）。
- 执行顺序（写死，grill 实测约束）：预检未提交改动 → 会话 cwd 与 policy root 切回主工作区 → 重新验证已不在 worktree → 需要删除时 `git worktree remove`。必须先切出再删除（删掉 cwd 所在目录后 `os.getcwd()` 崩溃）。
- `keep=false`：预检 worktree 内无未提交改动（tracked 修改与 untracked 文件均判定）才删除；含未提交改动时**拒绝并保持原状态**（仍在 worktree 内，无部分成功状态），不使用 `--force` 静默丢弃。**不删除分支**（分支保留在主仓库，与 proposal 行为定义同步）。
- 输出：`{"workspace": "<主工作区路径>", "removed": bool}`。
- 失败：不在 worktree 中、删除被拒（未提交改动）返回结构化错误，状态不变。

### D4: 会话工作目录切换的承载点

- 结论（grill 实证 + 用户确认）：所有文件工具共享同一个 WorkspacePolicy 实例（`agent/tools/factory.py` 注入），`workspace_root` 是可变属性，Bash 子进程 cwd 与 loop 的 BuildContext 均读取它——**原地重绑定 `workspace_root`** 即可让全部工具自动跟随，否决"重建实例并重新接线"方案（需同步 registry、LspClientManager、PersistentMemory、CommandGuard 等所有构造时捕获 root 的组件，易漏）。
- **不做进程级 `os.chdir`**（用户确认）：子 agent/后台任务与主 loop 同进程（asyncio.create_task），进程级 cwd 切换互相干扰；会话"当前目录"由 policy root 驱动。
- 已知降级（记录为限制，本 change 不处理）：LSP 客户端与 PersistentMemory 构造时捕获的 workspace_root 在重绑定后过期（worktree 内 LSP 可能查不到符号、memory 仍写主仓库）；CommandGuard 的 workspace 快照同样过期（guardrail 非边界，风险低）。

### D5: 权限元数据

- 定级（用户确认）：`dangerous=False` + WORKSPACE_WRITE（MEDIUM）。build 模式 auto_approve_max_risk=MEDIUM 自动放行（与"agent 自主创建"用户故事一致）；read_only/plan 模式因 capability 不在 profile 被拒。
- 不额外限制 `allowed_modes`；门控由 MEDIUM 风险级与 capability 决定。

### D6: 错误处理

所有错误路径返回结构化 ToolResult，`error_type` 打标（用户确认保留 5 个新码）：`not_a_git_repo` / `already_in_worktree` / `worktree_create_failed` / `not_in_worktree` / `worktree_remove_failed`，风格与现有 snake_case error_type 约定（timeout / permission_denied / unavailable / resource_exhausted / parse_error / mcp_error / approval_required）兼容。add 失败时 text 区分 branch 冲突与 path 冲突（git exit 255 两种原因），error_type 共用 `worktree_create_failed`。错误后 cwd 与 policy root 保持不变。

### D7: 与现有机制的关系

- workflow 状态机 building 阶段的强制 worktree 是编排层纪律；工具化后 agent 自主创建的 worktree 与其并行共存（worktree 列表以 git 为准），互不干扰。
- **工具仅对主 checkout 会话有效**（用户确认）：在编排层 worktree 内（building 强制、benchmark runner）EnterWorktree 前置条件不满足，恒被拒——显式声明此边界；benchmark smoke 只验证注册 + `get_all_schemas()` 暴露 + 被拒错误路径，不改 runner。
- benchmark runner 保持现状，不改为调用工具。
- 目录约定 `.asterwynd/worktrees/` 与编排层 worktree 命名前缀隔离。

## Pre-Implementation Review

开发前已完成 `batch-grill-me` 设计追问（`reviews/grill-design.md`，run `fc8263e9-38ca-4ba0-bd51-e895d7694f39`），并停轮逐项获得用户确认（记录于该文件的 `## User Confirmation` 节）。

- 已确定：双工具形态、工作区级隔离（policy root 原地重绑定，不做 os.chdir）、目录约定 `.asterwynd/worktrees/<name>` + 分支名 = name、keep/remove 退出语义（不删分支）、失败回滚原则（git 自清理 + 显式兜底）、dangerous=False + MEDIUM、5 个结构化错误码、ExitWorktree 执行顺序（预检→切出→验证→remove）。
- 已否决：Bash 包装（无结构化状态、无 policy 重绑定）、外部编排层扩展（不解决 agent 自主性）、重建 WorkspacePolicy 实例（需同步所有捕获 root 的组件，易漏）。
- 已确认边界：工具仅对主 checkout 会话有效（编排层 worktree 内恒被拒）；benchmark smoke 只验注册 + schema 暴露 + 被拒路径；dirty worktree 删除拒绝且状态不变。
- 剩余风险：LSP/PersistentMemory/CommandGuard 构造时捕获的 workspace_root 重绑定后过期（记录为已知限制）；Bash 绕过工具直接 `git worktree add` 无法阻止（工具面纪律，可接受）；跨平台路径（当前以 linux 为准）。

## Open Questions

全部已确认（2026-08-07，详见 `reviews/grill-design.md` `## User Confirmation`）：

1. 会话 cwd 切换承载点 → 共享 WorkspacePolicy 实例原地重绑定 `workspace_root`，不做 os.chdir。
2. WorkspacePolicy root 重绑定 API → 原地更新可变属性，否决重建实例。
3. 目录/分支命名 → `.asterwynd/worktrees/<name>`，分支名 = name。
4. 权限元数据 → dangerous=False + WORKSPACE_WRITE（MEDIUM），不限制 allowed_modes。
5. 失败回滚原子性 → add 失败 git 自清理 + verify；add 成功后失败 remove 回滚。
6. 错误码枚举 → 保留 5 个新码。
7. dirty worktree 删除被拒 → 拒绝并保持原状态。
8. benchmark smoke 形态 → 注册 + schema 暴露 + 被拒错误路径，不改 runner。

## Risks / Trade-offs

- **benchmark/workflow 场景工具前置条件恒不满足（严重）**：编排层 worktree 内 EnterWorktree 必被拒——已显式声明"工具仅对主 checkout 会话有效"，smoke 只验注册 + 被拒路径（D7）。
- **主工作区 git status 污染（中）**：目标仓库未忽略 `.asterwynd/` 时出现未跟踪目录——本项目 `.gitignore` 已忽略；文档化"目标仓库应忽略 `.asterwynd/worktrees/"`。
- **隔离非绝对（中）**：deny patterns 加 `.asterwynd/worktrees/**` 后主模式工具不可直读 worktree 内文件；但 Bash 绕过工具直接 `git worktree add` 无法阻止（工具面纪律，文档说明边界）。
- **LSP/PersistentMemory 捕获过期（中）**：构造时捕获的 workspace_root 重绑定后过期，worktree 模式下不保证跟随——记录为已知限制，后续单独处理。
- **CommandGuard workspace 快照过期（低）**：guardrail 非边界，实现时确认 `_check_argv` 相对路径分支。
- **symlink 路径归一化（低）**：toplevel 与 porcelain 路径比较需 resolve() 归一化，实现时覆盖。
- **残留污染风险**：worktree 创建失败时残留目录——回滚路径必须有测试覆盖。
- **命名冲突风险**：分支名 = name 与已有分支冲突时 `git worktree add -b` 失败（exit 255），返回 `worktree_create_failed`，agent 换名重试。
- **跨平台**：当前平台 linux，代码避免硬编码路径分隔符，测试以 linux 为准。
- **替代方案权衡**：
  - Bash 包装（agent 用 Bash 执行 `git worktree add` 并自行 cd）：无结构化状态、无 policy 重绑定、无法保证边界安全——否决。
  - 外部编排层扩展（继续由 runner/CLI 创建并注入 worktree）：不解决 agent 自主性需求，工具对齐缺失——否决。
  - 单一 Worktree 管理工具（一个工具带 action 参数）：协议上可行，但与 Claude Code 双工具对齐差——备选，倾向双工具。

## Testing Strategy

- 单元测试：参数校验、错误路径、keep 语义、分支名派生（分支名 = name）。
- 集成测试：`tmp_path` 下初始化真实 git 仓库，跑创建→进入→（文件工具路径边界验证）→退出→删除全流程；嵌套/非仓库/未提交改动删除拒绝（状态不变）等负向路径。
- AgentLoop 层：工具调用后 policy root 状态断言（不做 os.chdir 断言）；失败回滚断言。
- Benchmark：smoke 验证注册 + `get_all_schemas()` 暴露 + 编排层 worktree 内被拒错误路径（Q7 确认形态）。
