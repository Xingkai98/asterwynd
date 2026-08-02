# Proposal: 可观测性做深 — 结构化 Metrics + 成本归属 + 异常自动分类

## Change Type

primary: feature
secondary:
  - agent-runtime
  - cli
  - web

## 需求

1. 结构化 Metrics：每步 tool call 的耗时/成功率/token 消耗 → 可输出时间序列
2. 成本归属：每个 session 的 token 消耗按 phase/agent/tool 分组，可出账单
3. 异常自动分类：自动聚类错误类型（权限拒绝/网络超时/模型幻觉/参数错误），不同类别不同告警策略
4. 性能回归检测：CI 跑 benchmark → 对比基线 → P95 延迟/成功率劣化 >5% 自动拦截
5. Session 分析面板：单个 session 的 timeline 可视化，一眼看到哪些 tool call 耗时最长

## 背景

当前可观测性是"结构化步骤日志 + 内存内 hook 统计 + run 级汇总"：`TraceRecorder` 记录 run_started/llm_iteration/tool_call/tool_result 等，但 **llm_iteration 与 tool_result 均不记录 token**；`TracingHook` 只存内存；`cost_tracker.compute_cost` 只在 compare.py 做 run 级总估算，无按 tool/phase 归属；错误以 `[Error: ...]` 字符串流转，无结构化分类；无 CI 回归门禁；无 timeline 看板。

面试表现：被问"怎么保证改进不导致衰退"时，只能说"跑一下测试看通过没"，没有监控数据。

## 非目标

- 不默认引入 Prometheus + Grafana 外部监控栈（与本地可复现定位张力，作为可选项而非必交付）。
- 不重做 TraceRecorder 既有事件结构（在其上扩展结构化事件 schema）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/trace_recorder.py` | llm_iteration/tool_result 记录 token；结构化事件 schema |
| `agent/cost_tracker.py` | 按 session/phase/tool 成本归属 |
| `agent/hooks/` | 指标埋点 |
| `agent/run_config.py` | phase 语义定义（当前无 phase 概念，只有 mode） |
| `web/server.py` + `web/session.py` | timeline 看板 |
| `.github/workflows/ci.yml` | benchmark 回归门禁（P95/成功率 >5% 拦截） |
| `benchmarks/` | 复用 PR #80 statistics（bootstrap CI）做基线对比 |

## Reference Implementation Research

- status: enabled
- reason: 可观测性（结构化 metrics、成本归属、异常分类、回归门禁、timeline）是生产级 agent 系统的核心能力，应参考主流 LLM 观测工具与 coding agent 的实现。
- research questions:
  - LangSmith/Langfuse/OpenTelemetry GenAI 的 metrics schema 与成本归属模型？
  - 异常自动分类（权限拒绝/网络超时/模型幻觉/参数错误）的聚类方法？
  - CI benchmark 回归门禁的基线对比与阈值设定？
- findings:
  - 待 planning 阶段补充（本 proposal 阶段完成 status/reason/questions 登记；实质调研在本 change planning 阶段完成）。
- design impact:
  - 待 planning 阶段补充；先决条件：metrics schema 是否并入 TraceRecorder 需与 #73/#77 约定事件 schema。

## Dependencies

- 依赖 PR #80（已合入）：benchmark statistics（bootstrap CI）做回归门禁基线。
- 依赖 #77 工具治理：质量事件 schema（成本归属/回归门禁的数据源）。
- 与 add-minimal-tui-runtime-view 共享事件流（timeline 看板与其对齐事件粒度）。

## 验收

- 能输出单个 session 的耗时与 token 账单，并对性能退化设置自动拦截。
- 面试可引用 CI 中 benchmark P95 延迟对比、异常分类和自动告警规则。
