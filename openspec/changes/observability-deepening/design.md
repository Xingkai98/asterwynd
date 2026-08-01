# Design: 可观测性做深 — 结构化 Metrics + 成本归属 + 异常自动分类

## Context

当前可观测性是"结构化步骤日志 + 内存内 hook 统计 + run 级汇总"：`TraceRecorder` 记录 run_started/llm_iteration/tool_call/tool_result 等，但 llm_iteration 与 tool_result 均不记录 token；`TracingHook` 只存内存；`cost_tracker.compute_cost` 只在 compare.py 做 run 级总估算，无按 tool/phase 归属；错误以 `[Error: ...]` 字符串流转，无结构化分类；无 CI 回归门禁；无 timeline 看板。面试表现"跑一下测试看通过没"没有监控数据。

## Goals / Non-Goals

**Goals:**

- TraceRecorder 记录每步 token（llm_iteration 与 tool_result）。
- 按 session/phase/tool 的成本归属账单。
- 异常自动分类（权限拒绝/网络超时/模型幻觉/参数错误）+ 不同告警策略。
- CI benchmark 回归门禁（P95 延迟/成功率劣化 >5% 自动拦截）。
- Session timeline 看板。

**Non-Goals:**

- 不默认引入 Prometheus + Grafana 外部监控栈（作为可选项而非必交付）。
- 不重做 TraceRecorder 既有事件结构（在其上扩展）。

## Decisions

### Decision 1: metrics schema 并入 TraceRecorder，不引入外部监控栈

**方案**：在 TraceRecorder 既有事件结构上扩展结构化事件 schema（含 token/phase/tool 维度），输出时间序列；Prometheus/Grafana 作为可选项而非必交付。

**备选**：引入 Prometheus+Grafana。被拒：与本地可复现定位张力，且引入外部监控栈。

**理由**：先落结构化 schema + 回归门禁（复用 TraceRecorder 与 #73 报告输出），外部栈可后接。

### Decision 2: phase 语义映射 mode，成本按 session/phase/tool 分组

**方案**：定义 phase 语义（映射既有 AgentMode：build/read_only/plan），成本归属按 session/phase/tool 分组记账，可出账单。cost_tracker.compute_cost 扩展为按维度分组。

**备选**：仅 run 级总估算。被拒：无法回答"哪个 tool 最贵"。

**理由**：按维度的成本归属是可观测性的核心价值。

### Decision 3: 异常自动分类四类 + 差异化告警

**方案**：错误以结构化分类器聚类为四类（权限拒绝/网络超时/模型幻觉/参数错误），不同类别不同告警策略（如权限拒绝立即告警、模型幻觉记录样本）。

**备选**：错误字符串流转。被拒：无法自动分类与差异化告警。

**理由**：结构化分类是可观测性的必备能力。

### Decision 4: CI 回归门禁用 #73 statistics 基线

**方案**：CI 跑 benchmark → 对比基线（P95 延迟/成功率）→ 劣化 >5% 自动拦截（门禁命令返回非零）。基线持久化，复用 PR #80 statistics（bootstrap CI）。

**备选**：无门禁。被拒：无法自动拦截性能退化。

**理由**：回归门禁是"改进不衰退"的可验证证据链。

## Pre-Implementation Review

- 待 planning 阶段（grill-with-docs）确认本设计，并补齐 Reference Implementation Research 实质 findings 与 design impact。

## Reference Implementation Research

- status: enabled
- reason: 可观测性是生产级 agent 系统核心能力，需参考 LangSmith/Langfuse/OpenTelemetry GenAI 的 metrics schema、成本归属、异常分类与回归门禁实现。
- research questions:
  - LangSmith/Langfuse/OTel GenAI 的 metrics schema 与成本归属模型？
  - 异常自动分类的聚类方法？
  - CI benchmark 回归门禁的基线对比与阈值？
- findings: 待 planning 阶段补充（proposal 阶段已登记；实质调研在本 change planning 阶段完成）。
- design impact: 待 planning 阶段补充；先决条件是与 #73/#77 约定事件 schema。

## Risks / Trade-offs

- **[metrics schema 与既有 TraceRecorder 事件兼容] → 向后兼容扩展，不破坏既有 to_json 结构。**
- **[Prometheus+Grafana 与本地可复现定位张力] → 外部监控栈作可选项，先落结构化 schema + 回归门禁。**
- **[回归门禁基线漂移] → 基线持久化 + 固定 seed，避免环境抖动误拦截。**
- **[成本归属 phase 语义不明确] → phase 映射既有 AgentMode，避免引入新概念。**
- **[与 TUI 事件协议重叠] → 与 add-minimal-tui-runtime-view 对齐事件粒度，避免两套事件模型。**

## Testing Strategy

- 单元测试：token 记录、成本归属分组、异常分类器、回归门禁阈值判定。
- 集成测试：CI 门禁命令返回非零、timeline 渲染。
- 回归测试：既有 TraceRecorder/cost_tracker 测试不回归。
- benchmark 层级：回归门禁复用 PR #80 statistics。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/trace_recorder.py` | token 记录 + 结构化 schema |
| `agent/cost_tracker.py` | 按维度成本归属 |
| `agent/hooks/` | 指标埋点 |
| `agent/run_config.py` | phase 语义 |
| `web/server.py` + `web/session.py` | timeline 看板 |
| `.github/workflows/ci.yml` | 回归门禁 |
| `benchmarks/` | statistics 基线 |
