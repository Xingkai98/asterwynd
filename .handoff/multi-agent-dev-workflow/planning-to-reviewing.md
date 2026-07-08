# Handoff: Planning → Reviewing

## Change: multi-agent-dev-workflow

## What was done in planning

设计了 Asterwynd 开发流程的多 agent 协作状态机方案，将现有的线性开发流程（explore → propose → grill-with-docs → apply → sync → archive）重构为五阶段状态机模型，支持不同 agent 角色处理不同阶段、结构化 handoff 交接、human-in-the-loop review gate 和完整回退路径。

产出文件：
- `proposal.md` — Why、What Changes、Capabilities、Impact Analysis
- `design.md` — 9 项设计决策、风险缓解、测试策略、Open Questions
- `specs/dev-workflow-state-machine/spec.md` — 新能力域：状态机模型、handoff.json schema、流转规则、角色 agent、路由配置
- `specs/change-documentation/spec.md` — delta：新增 handoff.json artifact、.handoff/ 目录
- `specs/subagents/spec.md` — delta：新增五种角色 agent 类型注册
- `tasks.md` — 6 组 30+ 任务

## Key decisions

1. **五阶段模型**: planning → reviewing（设计评审）→ building → code-review（代码审查）→ closing
2. **grill-with-docs 纳入 planning**: 设计追问是设计过程的一部分（writing_design ⇄ grilling_design），reviewing 是对已完成设计的独立评审
3. **handoff.json** 作为全局状态 source of truth，放 change 目录提交；handoff note 放 .handoff/ 不提交
4. **两级状态机**: phase（路由 agent）+ sub_state（agent 内进度）
5. **Human review gate**: 每个 phase 末端的 ready_for_review，人确认通过/跳过/回退
6. **路由配置**: 每个 phase 可配 executor（inline/subagent/claude-code/codex）和 session_mode（same/new/ask），两层覆盖
7. **五种角色 agent**: Planner/Reviewer/Builder/CodeReviewer/Closer，作为 subagent 运行
8. **默认路由**: planning/building/closing=inline, reviewing/code-review=codex
9. **回退路径**: 人在任意阶段可回退到任意之前阶段

## Alternatives considered and rejected

- 单层 phase 状态机 → 拒绝：太粗，agent 进入后内部进度不可见
- 纯结构化 metadata 不用 handoff note → 拒绝：捕捉不了 nuance
- 自动调度引擎 → 推迟：本次只定义状态机和路由，人触发
- 每个阶段结束都用 ask 模式 → 拒绝：大部分场景默认值够用，少数覆盖

## Open questions for the reviewer

1. 五阶段划分是否合理？code-review 和 reviewing 的职责边界是否清晰？
2. handoff.json schema 字段是否完整？是否有遗漏？
3. 回退路径是否过于灵活（任意→任意）？是否需要限制回退次数或范围？
4. 路由配置中 codex executor 的实际可行性？（Codex CLI 是否支持接收 handoff note 作为 prompt？）
5. 单 agent 全流程场景下，handoff note 的简化策略是否合理？
6. 是否有跨 phase 的并发场景需要考虑（如多个 change 并行开发）？

## Entry point for reviewer

阅读顺序：proposal.md → design.md → specs/dev-workflow-state-machine/spec.md → specs/change-documentation/spec.md → specs/subagents/spec.md → tasks.md

重点审查 design.md 中的 9 项决策和 risks/trade-offs 是否自洽。
