## Context

Asterwynd 目前通过 OpenSpec change 管理需求、设计、实现和归档。最近的流程治理已经增加了 Impact Analysis、Pre-Implementation Review、baseline CI 和 artifact checker。

这些规则保证了“进入实现前要把设计说清楚”，但还没有描述多角色协作方式。用户希望支持两类流程：

- 单 agent 流程：一个模型从 proposal、design、implementation、review 到 archive 全部完成。
- 多角色流程：A 模型设计，B 模型开发，A 或 C 模型审阅，B 再修改，直到通过。

为了不把流程直接绑定到具体模型，本 change 使用角色语言而不是模型语言。

## Goals / Non-Goals

**Goals:**

- 定义 Designer、Implementer、Reviewer、Closer 四个 change workflow role。
- 允许同一个 agent 扮演多个角色，也允许多个 agent/model 分担角色。
- 定义设计到实现的 handoff artifact 要求。
- 定义实现审阅的结构化记录格式。
- 定义 review findings 到 revision 的闭环规则。
- 保持流程文档化和可追溯，不引入调度系统。

**Non-Goals:**

- 不实现自动模型选择、任务派发或 agent 编排。
- 不实现 GitHub review bot 或自动 PR reviewer 分配。
- 不要求所有 change 必须多 agent 协作。
- 不改变 OpenSpec CLI 的核心行为。
- 不改变 CI 门禁和 branch protection。

## Decisions

### Decision 1: 使用角色而不是模型命名流程

流程定义使用 Designer、Implementer、Reviewer、Closer，而不是 “A 模型 / B 模型”。

理由：同一个模型可以从头做到尾，也可以多个模型分担。角色抽象能表达责任边界，又不把流程绑死到具体供应商或模型能力。

### Decision 2: Handoff 信息写入 change artifact，而不是依赖聊天上下文

设计阶段完成后，`design.md` SHALL 包含可供实现者独立执行的 handoff 信息，例如目标、非目标、接口边界、关键决策、未选方案、测试策略、Impact Analysis、已知风险和开放问题。

理由：跨模型交接时聊天上下文不可靠，仓库内 artifact 才是 source of truth。

### Decision 3: Implementation Review 使用结构化 findings

实现审阅 SHALL 记录在 change artifact 中，建议使用 `## Implementation Review` 或独立 `review.md`，包含：

- Blocking findings
- Non-blocking findings
- Spec mismatches
- Test gaps
- Architecture concerns
- Required changes
- Accepted deviations

理由：结构化 findings 能让 Implementer 明确哪些必须修改，哪些可以后续处理，也便于 Closer 判断是否可以归档。

### Decision 4: Revision loop 以 findings 关闭状态为准

如果 review 产生 blocking findings，Implementer SHALL 修改实现并在 review 记录中标记处理结果。归档前所有 blocking findings 必须关闭，或被 Reviewer/人工明确接受为 deviation。

理由：这比“又改了一版，应该好了”更可追溯，也避免审阅意见丢在聊天里。

### Decision 5: 简单 change 允许单 agent 通过

同一个 agent 可以连续扮演 Designer、Implementer、Reviewer 和 Closer。流程要求的是 artifact 完整和阶段责任清晰，不要求实际参与者不同。

理由：强制多 agent 会拖慢小 change；角色化流程应该是可伸缩治理，而不是固定人力流程。

## Pre-Implementation Review

- Questions resolved:
  - 本 change 当前只是流程提案草案，尚未进入实现。
  - 角色语言优先于模型语言，以兼容单 agent 和多 agent。
- Options considered:
  - 直接定义 A 模型 / B 模型流程。
  - 定义角色化流程，不绑定具体模型。
  - 一次性实现自动模型调度和 review automation。
- Rejected alternatives:
  - 直接定义 A/B 模型。原因：会把流程绑死到具体模型分工，无法自然支持一个 agent 从头做到尾。
  - 一次性实现自动调度。原因：当前需求首先是流程可追溯，自动化会扩大范围到 agent 编排和权限控制。
- Final confirmations:
  - 待正式开发前，需要确认 review artifact 放在 `design.md`、`review.md`，还是两者组合。
  - 待正式开发前，需要确认 artifact checker 是否只检查结构，还是检查 blocking findings 的关闭状态。
- Remaining risks:
  - 流程文档过重可能拖慢小 change，需要保留单 agent 快速路径。

## Risks / Trade-offs

- [Risk] 流程过重。Mitigation: 明确角色可由同一个 agent 承担，小 change 只需保留必要 artifact。
- [Risk] review findings 变成形式主义。Mitigation: 只强制结构和 blocking 状态，不要求冗长文字。
- [Risk] checker 很难判断 review 质量。Mitigation: checker 只做机械检查；review 质量仍由人工或 reviewer agent 负责。
- [Risk] 多 agent 修改同一 change 产生冲突。Mitigation: 本 change 只定义 artifact 和阶段边界，不处理并发锁；并发协作另起 change。

## Testing Strategy

- 如果实现 artifact checker 规则，新增测试覆盖缺少 handoff/review 结构、blocking findings 未关闭和 docs-only 例外。
- 运行 `uv run pytest tests/test_openspec_artifact_checker.py -q`。
- 运行 `uv run pytest -q`。
- 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- 运行 `uv run python scripts/check_openspec_artifacts.py`。
