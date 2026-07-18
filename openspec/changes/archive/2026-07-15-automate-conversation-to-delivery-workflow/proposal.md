## Why

当前开发工作流只在 OpenSpec change 已创建后追踪部分 planning/building 状态，闲聊探索、需求收敛、设计启动、worktree 创建和人工批准仍依赖 agent 遵循提示词与聊天记忆。结果是新会话无法可靠恢复全局进度，agent 可以跳过步骤、在错误工作区修改文件，或自行写入看似由人批准的状态。

本 change 建立从探索性对话、需求确认、设计、开发、审查到合入完成的统一工作流控制平面，使人和 agent 都能从持久状态直接知道当前阶段、进度、工作区、阻塞项和下一步，并由运行时机械阻止非法跳转与 gate 后继续执行。

## Change Type

- Primary: feature
- Secondary: [process]

## What Changes

- 新增覆盖 `exploring`、`requirements`、`design`、`building`、`code-review`、`closing` 和 `done` 的端到端生命周期。
- 闲聊探索和需求定义在主仓库进行，不要求创建分支或 worktree；需求人工批准后，进入设计前自动创建 change 专属分支和 worktree。
- 设计、开发、修复和 closing 全程复用同一个 worktree，PR 合入并完成 post-merge 确认后清理。
- 新增独立于 AgentLoop 的 workflow control plane package 与 CLI；Asterwynd、Codex、Claude Code、Happy Coder 和人工操作通过强弱不同的 executor/client adapter 接入。
- 新增 Managed Workspace Root 路径列表；只有命中显式受管路径或其 Git worktree 的 session 才启用 workflow，其余路径在模型调用前直接旁路。
- 受管项目中新 session 在无恢复目标时自动创建轻量 Exploration Workflow；未产出且未进入 requirements 的 exploration 按可配置老化时间自动 abandon。
- 新增仓库级 workflow registry，使从主仓库启动的新会话可以发现探索事项、需求事项和所有 worktree 中的 active changes。
- 将状态变更收口到 workflow orchestrator；agent 只能请求迁移，不能直接写入当前状态或伪造人工批准。
- 所有 transition 使用可重放事件记录；验证器检查状态邻接、历史连续性、证据、gate approval 和最终派生状态。
- 每个阶段的 `ready_for_review` 成为强制停止点；未收到可信用户事件前拒绝状态推进和写操作。
- 用户可以在当前 session 通过配置的 Gate Approval Token 批准 gate；V1 仅对完整消息精确匹配 `ok`，host 在消息进入 agent 前绑定当前 gate/version，禁止模糊匹配。
- 新增统一状态查询输出，展示 change、phase、sub-state、进度、worktree、分支、阻塞项、gate 和下一步。
- Host 在 closing 前验证完整本地 workflow history 并签发最小 `workflow-receipt.json`；CI 验证签名、关键 Gate、artifact hash、base commit 和 event-chain root，不提交完整事件流水。
- 提供两种 V1 入口：`workflow chat --executor ...` CLI Host Wrapper 作为强约束入口；可复用 workflow skill + 短版 `AGENTS.md` 作为 Happy Coder 等客户端的非侵入 Prompt Adapter，明确降级为软约束/audit-only。
- **BREAKING**：废弃 agent 直接编辑 `handoff.json` 和通过 `--who human` 自报人工身份的状态更新方式。

## Capabilities

### New Capabilities

- `conversation-delivery-workflow`: 定义从探索性对话到 PR 合入的统一控制平面、阶段模型、状态发现、可信 gate、worktree 生命周期和可重放事件语义。

### Modified Capabilities

- `dev-workflow-state-machine`: 扩展生命周期边界，改为 orchestrator 独占状态写入，并增加合法迁移重放、可信批准和设计阶段 worktree 约束。
- `agent-runtime`: 新会话自动恢复 workflow 上下文，在 gate 状态阻止继续执行，并发布可观察的 workflow 状态事件。
- `change-documentation`: 调整 `handoff.json`、handoff note 和 approval record 的 source-of-truth 与归档要求。
- `workspace-safety`: 根据 workflow phase 和绑定 worktree 强制限制写操作，防止设计开始后修改主仓库或错误 change 的工作区。

## Impact Analysis

### 能力域

- Workflow control plane：独立领域模型、事件存储、orchestrator、approval、handoff、状态查询和历史校验。
- Executor integration：Asterwynd、Codex、Claude Code 与人工执行入口只消费 `WorkItem` 并提交 `WorkResult`。
- Workspace：worktree 创建、绑定、命令工作目录、写入授权和清理。
- OpenSpec：change 初始化、artifact 状态、归档以及 active/archive workflow 审计。
- CLI/Web/TUI/Skill：统一状态查询与人工 gate 交互；首期覆盖 CLI Host Wrapper 和 Prompt Adapter，其他入口复用同一协议。

### 代码

- 预计新增独立的 `workflow_control/` bounded context，包含 domain、event store、orchestrator、gate、worktree、executor adapters 和 CLI。
- `workflow_control/` 核心不得依赖 `agent/`；Asterwynd 通过 adapter 接入，AgentLoop 只接收控制平面生成的 `WorkItem`。
- 预计修改 `agent/workflow/`、`agent/session.py`、入口层、workspace policy 和 workflow 校验脚本，将现有能力迁移或适配到独立控制平面。
- 现有 `scripts/workflow_state.py` 和 `scripts/check_phase_done.py` 需要收口到正式领域服务，不能继续绕过 `WorkflowManager` 直接修改 JSON。

### 测试

- 状态机单元测试：所有合法与非法迁移、回退、skip、gate 和事件重放。
- 集成测试：闲聊到需求、需求批准后创建 worktree、跨 session 恢复、worktree 路由和 PR 后清理。
- 安全回归：agent 伪造批准、直接修改状态、gate 后写文件、错误 worktree 写入均须 fail closed。
- CLI/Web 协议测试：状态展示和用户批准事件正确路由到指定 workflow/version。
- CI artifact 测试：active 与 archive 的 history、approval 和派生状态一致性。

### 文档

- 新增短版 `AGENTS.md` 接入模板和 workflow skill；当前 `AGENTS.md` 暂不替换，迁移验收后再精简。
- 更新架构、需求流程、开发指南、测试指南和 OpenSpec backlog。
- 若 README 对开发流程或入口行为发生事实变化，则同步更新 `README.md` 与 `README_EN.md`。

## Reference Implementation Research

- status: enabled
- reason: 本 change 涉及 coding-agent 会话持久化、worktree 生命周期、权限 gate 和状态恢复，需参考成熟 agent 的控制面实现，避免继续依赖提示词约束。
- research questions:
  - 如何持久化可恢复、可审计且能跨 session 重放的 workflow 状态？
  - 如何将 worktree 身份与 session/change 绑定，并在恢复时从主仓库发现？
  - 如何区分 agent 请求与可信用户批准，使 gate 无法由 agent 自行越过？
  - 如何让任务自动推进，同时对抢占、失败和并发 change 保持一致性？
- findings:
  - 当前环境未提供 codegraph CLI，因此无法按首选方式建立跨仓库调用图；本次改用 `rg`、定点文件阅读和现有测试进行替代调研。
  - Codex 使用 append-only JSONL rollout 持久化 canonical session items，并支持通过既有路径 resume；其事件记录、显式 flush 和重放模型适合作为 workflow event store 的参考。
  - Claude Code 将 worktree path、branch、original cwd/head 和 session id 持久化到 transcript，并在 resume 时验证 worktree 仍存在；其 session 查找还会扫描 sibling worktrees，证明“主仓库发现 worktree 中会话”应由控制面负责。
  - Claude Code tasks mode 使用可持久化 task list、claim owner 和 watcher 自动领取未阻塞任务，说明自动推进需要原子 claim/lease，而不能只依赖 agent 自觉。
  - OpenHands 将 Planning Agent 与 Build 动作分离并要求用户显式切换，但主要依靠系统提示和 UI 行为；本 change 不采用这种软边界，gate 与写权限必须在运行时 fail closed。
- design impact:
  - workflow 状态采用 append-only event log，并由派生 snapshot 加速读取；snapshot 不能脱离事件历史单独成为权威。
  - registry 保存 canonical repo、worktree、branch、session 和 change 绑定，启动发现需要扫描 registry 与实际 `git worktree list` 并处理漂移。
  - 自动执行器需要 workflow claim/lease，避免两个 session 同时推进同一 change。
  - human approval 必须由入口层产生可信事件，并绑定 workflow id、gate phase、state version 和用户身份；领域层不接受自由文本身份声明。
