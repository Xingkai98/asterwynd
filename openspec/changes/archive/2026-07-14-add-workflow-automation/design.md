# Design: 开发流程自动化

## Context

`agent/workflow/` 已有完整的状态机模型（models.py、state_machine.py、manager.py、dispatcher.py），定义了五阶段生命周期。但 agent 运行时不会主动读取这些状态，导致每次会话需要人工传递上下文。

设计方案核心约束：
- AGENTS.md 作为 agent 冷启动的 pre-flight checklist
- 不引入新的后台服务或守护进程
- 不修改现有 workflow 模块的内部逻辑
- 向后兼容：无 handoff.json 的旧 change 不受影响

## Goals / Non-Goals

见 proposal.md。

## Decisions

### D1: 会话启动协议 — AGENTS.md 驱动

每个新会话开始前，agent 必须先运行 `python3 scripts/workflow_state.py discover`，根据输出决定行为：
- 1 个 change 处于 ready_for_review → 运行机械验证 → 呈现结果 → 停止等批准
- 1 个 change 处于执行中（非 gate）→ 读取 handoff.json → 继续执行
- 多个活跃 change → 列出所有 → 让用户选

选择理由：AGENTS.md 是 agent 冷启动时必然读取的文件，不需要新基础设施。业界参考：Claude Code 的 CLAUDE.md pre-flight 模式。

### D2: 状态与验证分离

`workflow_state.py`（状态 CRUD、推进、批准）和 `check_phase_done.py`（只读验证）是两个独立脚本。

选择理由：Codex 审阅指出的关键架构问题。分离后：
- 阶段内自动推进时只调用 workflow_state.py advance（轻量）
- Gate 停止时才调用 check_phase_done.py（全量验证）
- check_phase_done.py 是纯只读的，不会意外修改状态

### D3: Gate 机制 — ready_for_review 强制停止

每个 phase 的最终 sub_state 是 `ready_for_review`。到达时必须：
1. 停止执行（不得修改代码、创建文件或推进状态）
2. 运行 `check_phase_done.py --phase <phase> --change <id>`
3. 呈现结果 → 等待人工批准
4. 批准后运行 `workflow_state.py approve`，再推进到下一 phase

### D4: Worktree 隔离 — building phase

building phase 必须在独立 git worktree 中进行。分支命名 `<change-id>/<YYYY-MM-DD>`，禁止多个 change 共用，closing 完成后清理。

选择理由：building phase 涉及代码修改（最高风险），与 planning/reviewing/code-review/closing（只读或文档操作）的隔离需求不同。worktree 保证了：
- 主仓库在开发过程中保持干净
- 实验性修改不影响其他 change
- 出问题时可以快速丢弃

### D5: ADR 嵌入 handoff note

handoff note 的 Key Decisions 章节中，对有 ≥2 备选方案的决策必须使用 ADR 格式。如果决策尚无独立 ADR 文件，在 handoff note 内联完整 ADR；已存在的则引用文件名。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| pytest 全量跑太重（building gate） | 只在 `ready_for_review` gate 跑全量；阶段内 sub_state 只跑相关测试 |
| TODO 扫描误报 | `docs/known-debt.md` 白名单，已在 check_phase_done.py 中实现 |
| review-report 格式不可解析 | 同时支持 `.md` 和 `.json`；JSON schema 在 code-review handoff 中约定 |
| benchmark smoke 不可用 | 检测不可用时跳过 + warning，不 fail |
| 已有 active change 没有 handoff.json | discover 只扫描有 handoff.json 的目录，不受影响 |

## Testing Strategy

- `tests/test_check_phase_done.py`：15 个测试覆盖 planning/building/code-review/closing 四个 checker
- 已有测试 `tests/test_openspec_artifact_checker.py`：22 个测试继续通过
- 手动验证 `workflow_state.py discover` 正确报告"无活跃 change"
- benchmark smoke 在 CI 中可选运行

## Pre-Implementation Review

- Questions resolved: 五阶段流程与 agent 行为的桥接方式（AGENTS.md 驱动）
- Options considered: plan file vs OpenSpec change vs 直接改代码 — 本次采用"先实现后补 change 文档"（因为 workflow 机制本身尚未就位）
- Rejected alternatives: (a) 修改 workflow manager 在运行时注入状态 — 侵入性强且耦合；(b) 外部 cron/daemon 定期检查 — 过度设计
- Final confirmations: 状态/验证分离、worktree 隔离、ADR 嵌入 handoff note、向后兼容
- Remaining risks: 已有 active change 缺少 handoff.json 的问题需后续单独处理
