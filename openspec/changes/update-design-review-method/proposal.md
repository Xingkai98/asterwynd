# Proposal: 设计追问工具从 grill-with-docs 切换为 batch-grill-me

## Change Type

primary: process
secondary:
  - change-documentation

## 需求

1. 非平凡 OpenSpec change 开发前的设计追问工具从 `grill-with-docs` 切换为 `batch-grill-me`（设计树逐轮追问，一轮问整个 frontier，效率更高）。
2. 同步所有引用该工具的文档与机械检查逻辑。

## 背景

`grill-with-docs` 是逐条追问（grilling + domain-modeling），`batch-grill-me` 是设计树逐轮追问——把每轮可问的决策全部问完，减少往返轮次，效率更高（benchmark-evaluation-depth 已用 batch-grill 并验证）。

## 变更范围

- `AGENTS.md`：设计追问规则、自然语言路由、worktree 阶段方法表。
- `docs/requirements-process.md`、`docs/agents/domain.md`、`openspec/project.md`、`openspec/templates/tasks.md`。
- `scripts/check_openspec_artifacts.py`：设计审阅任务检查同时接受 `batch-grill` 与 `grill-with-docs`（兼容历史 change）。
- `scripts/workflow_methods.json`：planning exploring 方法映射为 `/batch-grill-me`。
- `openspec/specs/change-documentation/spec.md`、`openspec/specs/dev-workflow-state-machine/spec.md`、`openspec/specs/subagents/spec.md`：流程规格同步。
- 6 个 wayfinder change（tool-governance-deepening 等）的 design.md / tasks.md 引用同步。
- 测试断言文案同步。

## 非目标

- 不改 `docs/research/agent-engineering-best-practices-2026-07.md`（历史调研记录）。
- 不改检查器/测试中的旧关键字兼容（保留向后兼容，历史 change 文档仍可通过检查）。
- 不重做 `batch-grill-me` skill 本身。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `AGENTS.md` | 设计追问规则、路由表、worktree 方法表 |
| `docs/requirements-process.md` | 设计追问流程描述 |
| `docs/agents/domain.md` | ADR 创建触发方式 |
| `openspec/project.md` | 项目规则引用 |
| `openspec/templates/tasks.md` | tasks 模板 |
| `scripts/check_openspec_artifacts.py` | 设计审阅任务检查兼容新旧关键字 |
| `scripts/workflow_methods.json` | planning exploring 方法映射 |
| `openspec/specs/*` | 3 个流程规格同步 |
| 测试 | 断言文案同步，检查逻辑测试通过 |

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 无设计决策——纯工具替换（流程方法名变更），不涉及实现方案选择，无需参考实现调研。
