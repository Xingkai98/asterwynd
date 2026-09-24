# Grill: add-worktree-tool 设计追问

## Reviewer

- run id: fc8263e9-38ca-4ba0-bd51-e895d7694f39
- 时间: 2026-08-07

## Confirmed Decisions

- **决策**: 会话 cwd 与文件工具路径边界的承载点收敛为「共享 WorkspacePolicy 实例原地重绑定 `workspace_root`」，否决"重建实例并重新接线"方案（D4 收敛）；理由: `agent/tools/factory.py` 的 `get_default_tools`/`get_coding_tools` 把同一个 WorkspacePolicy 实例注入所有文件工具（Read/Write/Edit/Grep/Find/ListFiles/InspectGitDiff/Bash/LSP/RepoMap 等），Bash 子进程以 `self.policy.workspace_root` 为 cwd（`bash.py:90`），loop 的 BuildContext 也读 `workspace_policy.workspace_root`（`loop.py:1302`），`workspace_root` 是普通可变属性——原地更新即可让全部工具自动跟随；重建方案需同步 registry、LspClientManager、PersistentMemory、CommandGuard 等所有捕获构造时 root 的组件，易漏且改动面大；来源: fc8263e9-38ca-4ba0-bd51-e895d7694f39
- **决策**: worktree 目录约定采用 `.claude/worktrees/<name>`（与 Claude Code / 本 harness 一致），并经真实 git 验证可行；理由: 实测 `git worktree add -b <branch> <repo>/.claude/worktrees/<name> <base>` 在主工作区目录内成功（exit 0），`git rev-parse --show-toplevel` 在 linked worktree 内返回 worktree 根，本仓库 `.gitignore` 已忽略 `.claude/`；仓库外目录备选方案引入跨文件系统与父目录权限问题。两个必须处理的伴随项：目标仓库未忽略 `.claude/` 时主工作区会出现 `?? .claude/` 未跟踪目录（污染 `git status`/InspectGitDiff 输出），且主模式 policy root 下 `.claude/worktrees/**` 不在 DEFAULT_DENIED_PATTERNS 中（主模式工具可读写 worktree 内文件，隔离并非绝对）；来源: fc8263e9-38ca-4ba0-bd51-e895d7694f39
- **决策**: 嵌套 worktree 禁止判定算法收敛为「`git rev-parse --show-toplevel` 与 `git worktree list --porcelain` 首条目路径（resolve 归一化后）比对」，并确认该算法在编排层 worktree（building 阶段强制）内也正确拒绝 EnterWorktree；理由: 实测 porcelain 首条目恒为主工作区、toplevel 返回当前 worktree 根；实测 git 本身不阻止在 linked worktree 目录内再 `worktree add`（嵌套 add 成功），工具级 pre-check 是唯一防线，必须可靠；该判定对"主 checkout 运行"与"编排层 worktree 运行"两种场景给出正确结果，D7"与编排层并行共存"成立；来源: fc8263e9-38ca-4ba0-bd51-e895d7694f39
- **决策**: ExitWorktree 执行顺序必须写死为「预检未提交改动 → 切 cwd/policy 回主工作区 → 重新验证已不在 worktree → `git worktree remove`」，且不使用 `--force`；理由: 实测删除进程 cwd 所在目录后后续 `os.getcwd()` 抛 "Unable to read current working directory"（全部 cwd 依赖操作崩溃），故必须先切出再删；实测 `git worktree remove` 对 tracked 修改与 untracked 文件均拒绝（exit 128，提示 use --force），设计"拒绝+结构化错误、不用 --force 静默丢弃"正确，与 D3 描述一致；来源: fc8263e9-38ca-4ba0-bd51-e895d7694f39
- **决策**: EnterWorktree 失败回滚依赖「git 自清理 + 工具显式兜底」，并在 add 成功后任何后续步骤失败时执行 `git worktree remove`（新 checkout 干净，无需 --force）；理由: 实测 branch 冲突时 `git worktree add` exit 255 且 `git worktree list` 无残留注册（git 自清理，无需 prune），但失败后仍需工具显式 verify（list 中无该 worktree）并保证 cwd 与 policy root 未变；add 成功后的回滚对象是干净 checkout，remove 不会被 dirty 拒绝；来源: fc8263e9-38ca-4ba0-bd51-e895d7694f39
- **决策**: 权限元数据推荐定级为 `dangerous=False` + 默认 WORKSPACE_WRITE（MEDIUM），EnterWorktree/ExitWorktree 在 build 模式自动放行、read_only/plan 模式被 profile 拒绝（D5 收敛方向）；理由: 实测 `build_default` profile auto_approve_max_risk=MEDIUM、approval_required_max_risk=HIGH——若按 D5 倾向设 `dangerous=True`（HIGH），build 模式下每次调用都 REQUIRE_APPROVAL，与 proposal 用户故事"agent 自主创建隔离工作区"直接冲突；MEDIUM + WORKSPACE_WRITE 时 build 自动放行，read_only/plan 因 capability 不在 profile 而 DENY，门控语义合理；此为推荐方案，最终定级仍需用户确认（见 Q4）；来源: fc8263e9-38ca-4ba0-bd51-e895d7694f39
- **决策**: 新增错误码 `not_a_git_repo` / `already_in_worktree` / `worktree_create_failed` / `not_in_worktree` / `worktree_remove_failed` 与现有 `error_type` 约定兼容（D6 收敛）；理由: 现有错误码全集为 snake_case（timeout / permission_denied / unavailable / resource_exhausted / parse_error / mcp_error / approval_required），新码风格一致；建议 add 失败时区分 branch 冲突与 path 冲突的 text 说明（git exit 255 两种原因），error_type 可共用 `worktree_create_failed`；来源: fc8263e9-38ca-4ba0-bd51-e895d7694f39

## Open Questions

- **Q1**: 会话 cwd 切换是否同时执行 `os.chdir`？仅重绑定 policy root（推荐）还是 policy root + os.chdir 双写？子 agent 与后台任务与主 loop 同进程（`subagent/manager.py`、`background.py` 均用 asyncio.create_task），`os.chdir` 是进程级副作用会互相影响；仅重绑定时 `loop.py:1426` 的 runtime fingerprint 仍记录主工作区（session restore 无 mismatch 告警，但"cwd 概念"变为 policy root 驱动的虚拟 cwd），需确认接受哪种语义。
- **Q2**: worktree 目录约定最终拍板：`.claude/worktrees/<name>`（推荐，需文档化"目标仓库应忽略 `.claude/worktrees/`"，并在主模式 deny patterns 增加 `.claude/worktrees/**`）还是仓库外目录？`.claude/worktrees/**` 是否加入 DEFAULT_DENIED_PATTERNS？
- **Q3**: ExitWorktree keep=false 是否同时删除分支？proposal 行为定义写"删除 worktree 及对应分支"，但 D3 只提 `git worktree remove`（不删分支）；若删，用 `git branch -d`（仅已合并，安全）还是 `-D`（强制）？分支是 EnterWorktree 新建分支，一般可安全删，但需用户拍板语义。
- **Q4**: 权限元数据最终定级（D5）：采纳推荐（dangerous=False + MEDIUM，build 自动放行）还是设 dangerous=True（HIGH，build 每次调用需审批）？两个工具是否限制 `allowed_modes`（如仅 build/bypass）？
- **Q5**: ExitWorktree keep=false 且 worktree 含未提交改动时：拒绝并保持原状态（当前设计）还是拒绝但允许 agent 选择保留？删除失败（dirty 之外的原因）时"cwd 已切回主工作区但删除未完成"的部分成功状态是否可接受？还是要求先删除后切换（无法实现，见 Confirmed Decisions 第 4 条的顺序约束）？
- **Q6**: 新增错误码枚举取值确认：`not_a_git_repo` / `already_in_worktree` / `worktree_create_failed` / `not_in_worktree` / `worktree_remove_failed` 是否全部保留，还是合并精简（如 not_in_worktree 与 already_in_worktree 均可由文本区分）？
- **Q7**: benchmark smoke 的验证形态：benchmark runner 总是把被测 agent 放进任务 worktree（`n add` 隔离），此时 EnterWorktree 前置条件不满足会被拒绝——smoke 如何验证工具可用性？需要新增一个"主 checkout 运行"的 runner 路径/任务，还是 smoke 只验证注册与 schema 暴露（get_all_schemas）+ 被拒错误路径？

## User Confirmation

- **Q1**: 用户答复：仅重绑定 policy root，不做进程级 os.chdir；确认时间: 2026-08-07
- **Q2**: 用户答复：采用推荐的 `.asterwynd/worktrees/<name>` 目录约定（.claude 改为 .asterwynd，项目自有私有目录），并将 `.asterwynd/worktrees/**` 加入主模式 deny patterns；确认时间: 2026-08-07
- **Q3**: 用户答复：keep=false 时不删除分支，只 `git worktree remove`，proposal 行为定义同步修正（去掉"及对应分支"）；确认时间: 2026-08-07
- **Q4**: 用户答复：采纳推荐定级 dangerous=False + MEDIUM（build 自动放行），不额外限制 allowed_modes；确认时间: 2026-08-07
- **Q5**: 用户答复：keep=false 且 worktree 含未提交改动时拒绝删除并保持原状态（仍在 worktree 内），无部分成功状态；确认时间: 2026-08-07
- **Q6**: 用户答复：保留 5 个错误码（not_a_git_repo / already_in_worktree / worktree_create_failed / not_in_worktree / worktree_remove_failed）；确认时间: 2026-08-07
- **Q7**: 用户答复：benchmark smoke 只验证注册 + get_all_schemas() 暴露 + 被拒错误路径，不改 runner；确认时间: 2026-08-07
- **Q8**（分支命名）: 用户答复：分支名 = name（EnterWorktree 的 name 直接作为分支名，目录为 .asterwynd/worktrees/<name>）；确认时间: 2026-08-07

## 风险

- **严重: 进程级 os.chdir 副作用**（若采纳 os.chdir）：子 agent/后台任务/主 loop 共享进程，全局 cwd 切换互相干扰；未决于 Q1，必须先拍板再实现。
- **严重: benchmark/workflow 场景下工具前置条件恒不满足**：编排层 worktree 内（building 强制、benchmark runner）EnterWorktree 必被拒，proposal 用户故事"agent 自主隔离开发"在实际开发主场景不可用——需在文档显式声明工具仅对主 checkout 会话有效，并确认 Q7 的 smoke 形态，否则验收项"至少一个 benchmark smoke 通过"无法落地。
- **中: 主工作区 git status 污染**：目标仓库未忽略 `.claude/` 时，EnterWorktree 后主 checkout 出现未跟踪目录，InspectGitDiff/`git diff` 输出与 benchmark 判定可能误伤。
- **中: 隔离非绝对**：主模式下 `.claude/worktrees/**` 可读写（deny patterns 未覆盖），worktree 内文件可被主模式工具直接访问；另外 LSP 客户端与 PersistentMemory 构造时捕获的 workspace_root 在重绑定后过期（LSP 在 worktree 内可能查不到符号、memory 仍写主仓库），需决定 worktree 模式下是否禁用 LSP 工具或重建。
- **中: 部分成功状态**：ExitWorktree 删除失败时 cwd 已切回主工作区（顺序约束决定），返回错误但状态已变，需明确错误语义与 text 说明，避免 agent 误判"仍处于 worktree 中"。
- **低: CommandGuard workspace 快照过期**：BashTool 构造时 `CommandGuard(workspace=policy.workspace_root)` 捕获 root，重绑定后 guard 的相对路径判定基于旧 root（guard 是 guardrail 非边界，风险低，但需在实现中确认 `_check_argv` 的相对路径分支）。
- **低: symlink 路径归一化**：toplevel 与 porcelain 路径比较需 resolve() 归一化（worktree 经 symlink 注册时路径不一致），实现时需覆盖。
- **低: 嵌套 worktree 目录内再 add 无 git 层防线**：git 实测允许在 linked worktree 目录内嵌套 add，工具 pre-check 是唯一防线；agent 用 Bash 绕过工具直接 add 不受保护（可接受，工具面纪律），但 Bash 工具在 worktree 模式下执行 `git worktree add` 无法被阻止，设计文档应说明此边界。
