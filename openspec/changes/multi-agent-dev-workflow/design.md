## Context

当前开发流程定义为线性步骤序列（explore → propose → grill-with-docs → apply → sync → archive），没有正式状态机模型，每次 agent 启动需要人描述上下文或让其自读文档冷启动。本次设计将该流程建模为四阶段状态机，支持不同专门化 agent 分别处理各阶段、结构化 handoff 交接、human-in-the-loop review gate 和完整回退路径。

现有基础设施中：
- `agent/subagent/` 已提供子 session runtime，支持子 agent 创建、并发控制和 transcript inspect
- `openspec/changes/<change-id>/` 已有 proposal / design / tasks / specs 目录结构
- `handoff` skill 已在可用 skill 列表中，描述为"Compact the current conversation into a handoff document for another agent to pick up"

## Goals / Non-Goals

**Goals:**
- 将开发流程建模为可校验的状态机，每个 change 维护全局状态文件 `handoff.json`
- 定义 Planner / Reviewer / Builder / Closer 四个角色 agent，作为 subagent 运行
- 实现 agent 间结构化 handoff（`handoff.json` + 自然语言 handoff note）
- 每个 phase 末端设 human review gate，人可确认通过、跳过或回退
- 允许单 agent 完成全流程，不强制切换 agent
- 回退路径支持从任意阶段回到之前的任何阶段
- handoff skill 不可用时，内置等价 prompt 作为 fallback
- 每个 phase 可独立配置 executor（inline / subagent / claude-code）和 session 模式（same / new / ask），两层覆盖（全局默认 + per-change）

**Non-Goals:**
- 不改变现有 OpenSpec change 文档结构（proposal / design / tasks / specs）
- 不改动 AgentLoop 核心逻辑
- 不实现自动调度/编排引擎（本次只定义状态机和路由规则，实际路由由人触发或 CLI 命令触发）
- 不改变现有 subagent runtime 的核心语义
- 不做 benchmark 任务来评测多 agent 协作效果

## Decisions

### Decision 1: 两级状态机（phase + sub_state）

选择 phase 级别用于 agent 路由（决定启动哪种角色 agent），sub_state 级别用于同一 agent 内部进度追踪。

**替代方案**: 单层 phase 状态机 —— 拒绝原因：phase 颗粒度太粗，agent 进入 phase 后内部进度对外部不可见，工具链无法细粒度感知。

### Decision 2: handoff.json 作为唯一 source of truth

所有状态信息集中在 `handoff.json`，agent 和工具链都读这一份文件。不拆分到多个文件（如 `state.json` + `history.json`），避免状态不一致。

### Decision 3: handoff.json 放在 change 目录，交接笔记放在 .handoff/

`handoff.json` 是结构化数据，体积小，与 change 生命周期绑定，适合随 change 一起提交。handoff note 是自然语言对话摘要，可能包含中间讨论细节，放在 gitignored `.handoff/` 目录，不进入版本控制。

### Decision 4: Handoff note 优先使用 handoff skill，fallback 内置 prompt

- `handoff` skill 可用时：调用 skill 生成交接笔记
- 不可用时：内置等价 prompt 作为 fallback，确保无论环境如何都能产出合格的 handoff note

Fallback prompt 逻辑：

```
You are completing the "{current_phase}" phase of change "{change_id}".

Read all documents in openspec/changes/{change_id}/, including handoff.json
for current state, then produce a handoff note at
.handoff/{change_id}/{current_phase}-to-{next_phase}.md that covers:

1. What was done in this phase (summary)
2. Key decisions made and why
3. Alternatives considered and rejected
4. Open questions or risks for the next phase
5. Specific entry point and priority hints for the next agent

Keep the note concise — aim for 200-400 words. Then update handoff.json:
append to transitions, update current state, and set next hints.
```

### Decision 5: trigger 四种类型

| trigger | 含义 | 谁发起 |
|---------|------|-------|
| `auto` | phase 内 sub_state 间流转 | agent |
| `handoff` | agent 间交接 | agent（完成工作后） |
| `human_review` | 人在 gate 点确认放行 | 人 |
| `human_rollback` | 人在任意节点回退 | 人 |

`auto` 和 `handoff` 由 agent 写入；`human_review` 和 `human_rollback` 由人触发、agent 写入。

### Decision 6: Gate 点统一命名为 ready_for_review

四个 phase 的 gate sub_state 统一命名为 `ready_for_review`，简化路由判断和 UI 展示逻辑。

### Decision 7: 角色 agent 作为 subagent 运行

Planner / Reviewer / Builder / Closer 都作为现有 subagent runtime 的实例。路由逻辑（哪个 change 的哪个 phase 启动哪个 role）在父 session 中完成，然后创建对应类型子 session，传入 change 目录路径和 `handoff.json` 作为上下文。不引入新的 runtime 层。

### Decision 8: 不强制 agent 切换

通过检查 `handoff.json` 中的 `current_agent.run_id`，如果同一 agent 继续下一 phase，`transitions` 仍逐条记录，但 handoff note 可简化。human gate 不因单 agent 而跳过。

### Decision 9: 路由配置两层覆盖

每个 phase 可配置独立的 executor 和 session 模式，存储在 `handoff.json` 的 `routing` 字段。项目全局默认值放在 `openspec/config.yaml`，per-change 可覆盖。创建 change 时先展示默认配置并询问是否需要调整，不强制人每次手动配。

**Executor 类型:**

| executor | 实现方式 | 适用场景 |
|----------|---------|---------|
| `inline` | 当前 session 直接处理 | 快速讨论、小改动、单 agent 全流程 |
| `subagent` | 创建子 session，角色 agent 类型自动匹配 | 阶段间隔离、并行开发 |
| `claude-code` | 调 `claude` CLI 子进程 | 用外部 Claude Code 实例执行 |

**Session 模式:**

| mode | 行为 |
|------|------|
| `same` | 尽可能复用当前 session（inline 场景） |
| `new` | 每个 phase 创建新 session/进程 |
| `ask` | 每次 gate 点问人 |

**默认值策略:**
- 初始默认: planning=inline/same, reviewing=subagent/new, building=subagent/new, closing=inline/same
- 创建 change 时提示配置，人不改就用默认值
- gate 点 `session_mode: ask` 时再问一次

**替代方案**: 纯对话中每次手动指定 —— 拒绝原因：大部分场景默认值够用，少数覆盖即可，不用每次都问。

## Risks / Trade-offs

- **[风险] handoff.json schema 在开发中发现遗漏字段** → 缓解：schema version 字段预留；state_machine_version 保证向后兼容解析
- **[风险] 回退路径过于灵活导致无限返工** → 缓解：每次回退在 transitions 中记录 rollback_reason，形成审计轨迹；不引入"回退次数限制"但日志可见
- **[风险] handoff note 质量依赖 agent 的判断力** → 缓解：fallback prompt 规定了最低内容和字数范围；后续可加 CI 检查 handoff note 文件存在性
- **[取舍] 不实现自动调度引擎**：本次只定义状态机和路由规则，agent 启动仍由人发起或外部编排触发。自动调度（如 "change 到达 planning.ready_for_review 后自动启动 reviewer"）是后续能力

## Testing Strategy

- **单元测试**: handoff.json schema 校验（合法/非法流转）、transition 日志追加逻辑、trigger 枚举校验
- **集成测试**: 角色 agent 路由（给定 state 创建正确类型子 session）、handoff note 生成、human review gate 流转
- **CLI 测试**: 状态查询命令、手动流转命令
- **Artifact checker 测试**: `handoff.json` 存在性检查、必填字段非空检查

## Open Questions

- `handoff.json` 的 `schema_version` 初始值定为 `"1.0"` 是否合适？后续如调整 schema 如何迁移？
- 是否需要 Web UI 中显示 gate 审批等待列表？
- 是否需要 CLI 子命令（如 `asterwynd change status <id>`）查询 change 状态机状态？
