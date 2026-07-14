## 1. 实现前设计确认

- [x] 1.1 使用 `grill-with-docs` 逐项确认事件 schema、phase template、capability transport、requirements artifact 和签名 Workflow Receipt
- [x] 1.2 将设计追问结论回写 `design.md`，清理或明确阻塞所有 Open Questions
- [x] 1.3 如最终方案偏离 ADR-0001，新增或更新 ADR 并记录重访条件
- [x] 1.4 复核 Reference Implementation Research；如参考实现结论变化，先更新 proposal/design
- [x] 1.5 创建并验证 change 专属分支；planning 文档在该分支完成，building 前再按 workflow worktree 规则创建或切换专属 worktree

## 2. 独立领域模型

- [x] 2.0 为 managed roots、Git common dir 归属、symlink、sticky Workflow Bypass 和显式 attach 编写失败测试并实现零 token 激活门禁
- [x] 2.0a 实现受管 session 自动 Exploration、可配置 aging TTL、Workflow Output 判定和 abandon 事件
- [x] 2.0c 实现 chat/status/enter/manage 前的幂等 lazy aging scan，不引入 daemon/cron
- [x] 2.0b 实现 draft/proposed/durable output 生命周期、retain mini-gate 和 requirements/phase gate 批量 acceptance
- [x] 2.1 为 Workflow、Event、Snapshot、WorkItem、WorkResult、Gate、Approval、Evidence、WorkspaceBinding 和 Lease 编写失败的模型测试
- [x] 2.2 创建不依赖 `agent/` 的 `workflow_control` package 结构和公开类型
- [x] 2.3 实现版本化 phase template、executor lane、review lane、runner_profiles 与 Asterwynd `coding-agent-openspec` 默认模板
- [x] 2.3a 实现 phase commit_policy 配置，默认要求 human gate 前 clean worktree、HEAD commit 和 gate summary 绑定
- [x] 2.4 实现 event reducer 和合法 transition 判定，使模型测试通过
- [x] 2.5 增加依赖边界测试，阻止 `workflow_control` core 导入 AgentLoop 类型

## 3. SQLite Event Store

- [x] 3.1 为项目 fingerprint、数据库初始化、event append、version CAS 和 snapshot rebuild 编写失败测试
- [x] 3.2 实现项目外 SQLite 路径解析、schema migration、WAL 和事务边界
- [x] 3.3 实现 append-only event repository 与派生 snapshot repository
- [x] 3.3a 实现结构化 requirements draft、Markdown projection、版本化更新和 approved snapshot 冻结
- [x] 3.4 实现 history replay、一致性检查和损坏数据库错误处理
- [x] 3.5 增加并发 session 的 CAS 冲突与 stale version 回归测试

## 4. Orchestrator 与执行协议

- [x] 4.1 为 `enter`、`status`、`report` 和多 workflow 选择行为编写失败测试
- [x] 4.1a 实现显式 workflow、worktree cwd、唯一 active、多 active 用户选择和无 active 新建 exploration 的确定性恢复顺序
- [x] 4.1b 实现 User Session sticky workflow binding、跨 Session 恢复、单写 lease 和 done 后新事项要求新 Session
- [x] 4.2 实现 WorkItem 生成、allowed actions、required evidence 和 next action 计算
- [x] 4.2a 实现 exploring goal candidate 驱动的自动 requirements transition，并验证不创建 worktree或隐式批准需求
- [x] 4.3 实现 WorkResult 验证，禁止 executor 指定任意目标状态
- [x] 4.4 实现 blocker、rollback、允许的 skip 和 stale WorkItem 处理
- [x] 4.5 实现 workflow claim/lease 的领取、续期、释放、冲突和超时回收
- [x] 4.6 实现 human gate 前 automated review lane 调度、review_result 处理和 changes_requested 回退

## 5. 可信 Gate 与 Capability

- [x] 5.1 为 agent 伪造批准、过期批准、错误 gate 和错误用户 capability 编写失败测试
- [x] 5.1a 为 Gate Approval Token 精确匹配、非白名单保持 gate、原始 user message 绑定和白名单配置编写 contract tests
- [x] 5.1b 增加 `OK`、大小写变化、前后空白、换行和 Unicode 变体不得批准的回归测试
- [x] 5.2 实现并验证 V1 Host Wrapper 进程内 approval capability，确保 agent 环境不暴露 approve 命令或 secret
- [x] 5.3 实现 agent 与 human client 的分离 capability policy
- [x] 5.4 实现 gate reached、approved、rejected、revision 和 stale approval 事件
- [x] 5.4a 在 host adapter 中实现模型调用前的 Gate Approval Token 精确匹配器，V1 默认仅允许完整消息 `ok`
- [x] 5.4b 实现 approval token 消费、同 turn transition/re-enter/dispatch 和失败时 blocked 的原子编排测试
- [x] 5.4c 实现可信 CLI 批准命令 `workflow gate approve --workflow <id>`，并验证 Prompt Adapter 无法代替用户调用 approval capability
- [x] 5.5 实现 gate 后 lease 释放和 workspace write fail-closed contract

## 6. Worktree Coordinator

- [x] 6.1 为 canonical repo 识别、branch naming、worktree 创建、绑定漂移和安全清理编写失败测试
- [x] 6.1a 为 base branch fetch/fast-forward、dirty/diverged blocked、远端不可用和 local-base override 编写集成测试
- [x] 6.1b 实现 change id 提议、gate 展示、approval 冻结和 active/archive/branch/worktree 冲突校验
- [x] 6.2 实现 requirements gate 后原子 branch/worktree promotion
- [x] 6.3 实现 approved requirements 向 proposal、spec delta 和去敏 workflow manifest 的 materialization
- [x] 6.3a 验证 requirements 阶段不修改 canonical main repository，materialization 只使用 gate 绑定的 approved snapshot
- [x] 6.3b 验证 design.md、ADR 和 tasks.md 仅在 design phase 的绑定 worktree 中生成
- [x] 6.4 实现 design 到 closing 的 workspace 复用和 cwd 路由
- [x] 6.4a 实现 phase commit 创建/发现、dirty worktree 阻断、gate summary 绑定 branch/HEAD commit/`state_version`/evidence hash/`gate_summary_hash` 和 stale approval 检测
- [x] 6.5 实现 worktree 缺失、branch 漂移、重复绑定和 dirty cleanup 的 blocked 行为
- [x] 6.6 实现 merge/归档确认后的 worktree 清理

## 7. CLI、Skill、模板与 Executor Adapter

- [ ] 7.0 实现 `workflow manage add/remove/list`、`workflow attach` 和 host adapter 的 sticky session bypass
- [ ] 7.0a 实现 `workflow chat --executor <adapter>` Host Wrapper，作为支持可信 gate 和强 enforcement 的 CLI 入口
- [x] 7.1 为稳定 JSON 输出编写 `workflow enter/status/report` CLI contract tests
- [x] 7.2 实现本地 CLI 和人读状态渲染
- [ ] 7.3 实现 fake executor adapter，完成 requirements→design→gate tracer bullet
- [ ] 7.3a 验证单一 User Session 跨 phase 复用以及 fresh executor 结果回传同一 Session
- [ ] 7.3b 实现 runner profile 与 automated reviewer adapter，支持 subagent、fresh Codex CLI/Claude Code runner、command runner 的最小审查上下文；inline checker 通过 command runner 建模，并禁止 self reviewer
- [ ] 7.4 实现 Asterwynd adapter，并确保 session snapshot 不覆盖 workflow 状态
- [ ] 7.5 实现 Prompt Adapter：可复用 workflow skill + 短版 `AGENTS.md` 模板，要求原生客户端每个 run 前调用 `enter`、结束调用 `report`
- [ ] 7.5a 验证 Happy Coder 等非侵入客户端走 Prompt Adapter 时可派发 automated review，但不拦截用户消息、不拥有 approval capability，并在 WorkResult evidence/Receipt 中记录 `prompt_adapter` 或 `audit_only` enforcement level
- [ ] 7.6 新增可复用项目流程模板和短版 `AGENTS.md` 接入模板，但暂不替换当前 `AGENTS.md`
- [ ] 7.7 增加 executor capability/enforcement level 展示，区分 `strict_host`、`prompt_adapter` 和 `audit_only`

## 8. Workspace Policy 与兼容迁移

- [ ] 8.1 为 requirements 代码写入、错误 worktree、gate、blocked 和 stale version 编写安全回归测试
- [ ] 8.1a 验证 unmanaged main/普通 worktree 允许操作、active workflow worktree 要求 binding，以及不支持硬隔离时的 audit-only 降级
- [ ] 8.2 将 workflow workspace binding 接入 WorkspacePolicy 和命令执行入口
- [ ] 8.3 实现旧 `handoff.json` 的只读导入与兼容导出
- [ ] 8.4 将 `scripts/workflow_state.py` 降级为调用正式领域服务或只读兼容入口
- [ ] 8.5 选择一个试点 change 进行影子记录，对比旧状态与新事件派生结果

## 9. Workflow Receipt 与 CI

- [ ] 9.1 为 Host 完整 history validation、Receipt 去敏、签名、artifact/evidence hash、human gate binding tuple 和 archive 审计编写失败测试
- [ ] 9.1a 为专用 Ed25519 key 初始化、文件权限、canonical JSON、多个 signer、active/retired/compromised 状态、轮换和 agent 不可见性编写测试
- [ ] 9.2 实现最小 workflow-receipt.json 生成、event-chain root、key id 和签名
- [ ] 9.3 扩展 artifact checker，验证 active 与 archived workflow Receipt
- [ ] 9.4 更新 CI，验证 Receipt 签名、必需 Gate、gate binding tuple、artifact/evidence hash、base commit 和 archive 引用
- [ ] 9.5 增加 tampered Receipt、无效 key、绝对路径泄漏、完整事件泄漏和 secret 泄漏回归测试

## 10. Spec、文档与验证收尾

- [ ] 10.1 将本 change 的五个 spec delta 同步到当前规格 `openspec/specs/<capability>/spec.md`
- [ ] 10.2 更新架构、需求流程、开发指南、测试指南和 backlog 中受影响的事实
- [ ] 10.3 评估是否已满足精简 `AGENTS.md` 的迁移条件；未满足则保留现状并记录后续任务
- [ ] 10.4 如 README 入口或开发流程事实变化，同步更新 `README.md` 和 `README_EN.md`
- [ ] 10.5 运行 workflow control 单元、集成、安全和 adapter contract tests
- [ ] 10.6 运行全量 `uv run pytest -q`
- [ ] 10.7 运行 benchmark fake-agent smoke，验证核心 coding-agent 路径无回归
- [ ] 10.8 运行 OpenSpec strict validate、artifact checker 和 signed workflow Receipt audit
- [ ] 10.9 完成 code review、归档 change、清理 backlog、准备 PR 并记录验证结果
