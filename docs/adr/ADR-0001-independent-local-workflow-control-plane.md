# ADR-0001: 独立本地 Workflow Control Plane

- **Status**: accepted
- **Date**: 2026-07-14
- **Deciders**: 项目维护者、Codex

## Context

当前开发流程规则主要位于 `AGENTS.md`、OpenSpec 文档和 `agent/workflow/` 中，状态更新依赖 agent 主动读取提示、直接修改 `handoff.json` 并在 gate 前自行停止。这种方式无法覆盖闲聊探索和需求收敛，也不能可靠防止非法跳步、错误 worktree 写入或 agent 自报人工批准。

新能力需要独立于任何具体 coding agent，能够调度 Asterwynd、Codex、Claude Code 或人工执行者；同时 V1 应保持本地优先，不引入必须常驻的服务和云端依赖。

## Decision

建立独立的 `workflow_control` bounded context，核心不依赖 `agent/`。V1 提供本地 Python library 与 `workflow` CLI，使用项目外 SQLite event store 保存 append-only workflow events 和派生 snapshot，通过 executor/client adapter 接入不同 agent 与人工客户端。

控制平面负责状态机、worktree、gate、approval、lease、证据和恢复；agent 只接收 `WorkItem`、提交 `WorkResult`，不能直接修改状态或批准 gate。设计开始前自动创建专属 worktree，设计、开发、修复和 closing 复用该 worktree，合入后清理。

V1 同时提供两种接入形态：`workflow chat --executor ...` CLI Host Wrapper 作为强约束入口，持有 approval capability 并能在调用 executor 前处理 gate；`skill + AGENTS.md` 作为轻量 Prompt Adapter，要求 agent 在每轮前后调用 `workflow enter/report/status`，用于 Happy Coder 等不侵入宿主客户端的场景。Prompt Adapter 只能提供状态恢复、提示约束和审计，不能宣称具备可信 gate 或进程级写权限强制。

## Alternatives Considered

| 备选方案 | 描述 | 拒绝原因 |
|----------|------|---------|
| 继续强化 `AGENTS.md` 和脚本 | 增加更多启动说明、检查器和 JSON 字段 | 仍依赖 agent 遵从提示，无法形成可信批准、写权限边界和统一恢复控制面 |
| 将能力直接集成进 AgentLoop | 由 Asterwynd runtime 内部管理 change 生命周期 | 与单一 agent 强耦合，Codex、Claude Code 和人工执行无法复用，也混淆任务执行与开发流程编排职责 |
| 侵入 Happy Coder 实现专用 adapter | 在 Happy server/daemon/app 消息链中拦截用户输入和调度 executor | 可行性依赖第三方实现细节，维护成本高；V1 先用 Prompt Adapter 保持非侵入，后续只在需求明确时再评估原生集成 |
| V1 建立常驻 daemon | 使用本地 HTTP/gRPC 服务统一处理状态和实时通知 | 增加安装、生命周期、端口、安全和故障恢复复杂度；SQLite 事务与短生命周期 CLI 已能满足本地多 session MVP |
| 每个 worktree 保存独立可变 JSON | 继续以 `handoff.json` 作为唯一实时状态 | 主仓库无法稳定发现 sibling worktree，跨 session 并发容易覆盖，且无法可靠重放和审计历史 |
| 一开始拆为独立仓库 | 单独发布 workflow 产品和 adapter SDK | 协议尚未稳定，跨仓库版本和测试成本过高；先在当前仓库保持架构隔离更利于迭代，之后可无损拆分 |

## Consequences

- 正面影响：
  - 开发流程不再依赖 agent 聊天记忆或特定模型。
  - 人和 agent 可通过统一状态恢复当前阶段、工作区、阻塞项和下一步。
  - worktree、gate、approval 和状态迁移可以机械校验。
  - executor adapter 协议允许接入其他 coding agent。
- 负面影响：
  - 引入新的领域模型、SQLite schema、capability 边界和迁移成本。
  - 真正可信的人工批准要求 host 将控制面数据与 approval capability 隔离在 agent 可写范围之外。
  - 本地 V1 不自动解决跨机器同步和远程团队协作。
- 需要的相关变更：
  - 将现有 `agent/workflow/` 能力迁移或适配到 `workflow_control/`。
  - 为 CLI Host Wrapper、Prompt Adapter、Asterwynd 和 CI 提供不同信任级别的 adapter。
  - 最终从机器规则生成简短的 `AGENTS.md` 接入说明和可复用 skill，但迁移完成前保留当前文档规则。

## Revisit Conditions

- [ ] Web/TUI 需要实时订阅 workflow 状态，短生命周期 CLI 无法满足通知延迟和连接管理要求。
- [ ] workflow 需要跨机器、跨用户协作或远程审批，必须引入服务端存储和身份系统。
- [ ] 独立协议稳定且出现第二个外部项目消费者，适合拆为独立仓库和发布包。
- [ ] SQLite 单写事务成为可测量的并发瓶颈。
