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

经 batch-grill-me（设计树逐轮确认）已定稿以下决策：

**第一轮已确认（根决策）：**
- **第一批范围**：TraceRecorder 记录 token + 结构化事件 schema + 按 session/phase/tool 成本归属账单 + 异常自动分类；**CI 回归门禁和 session timeline 看板拆到第二批**（回归门禁依赖 benchmark 实际跑通、受环境制约；timeline 要改 web + 事件持久化、与 TUI 共享事件协议应错开）。前三块自洽（TraceRecorder 加 token/schema → 成本归属消费 → 异常分类）。
- **TraceRecorder token 记录**：`record_iteration` 增加 token 参数（input_tokens/output_tokens，来自 LLMResponse.usage）；`record_tool_result` 不记 token（工具执行不耗 LLM token）。`TraceStep` 增加时间戳字段（record 时自动打点），顶层加 schema_version。
- **成本归属（CostLedger）**：`agent/cost_tracker.py` 扩展出 `CostLedger`——`record(model, input_tokens, output_tokens, *, session_id, phase, tool_name)` 累加，`bill() -> {by_session, by_phase, by_tool}` 输出分组账单。phase 语义映射 AgentMode（build→building、read_only→review、plan→planning、bypass→bypass）。loop 里每次 LLM 调用后调 ledger.record。
- **异常自动分类（业界调研校准，非关键词规则）**：错误在产生时打结构化属性（`error_type`/`finish_reason`），分类器基于这些字段聚合分类，而非事后文本匹配。四类：permission_denied/network_timeout/model_error/parameter_error。语义错误（幻觉）不自动分类（业界共识需 LLM judge，与 #73 judge 降级一致），本 change 只做系统错误的结构化分类。

**第二轮已确认（细节层）：**
- **`CostLedger` API + JSONL 持久化**：
  ```python
  class CostLedger:
      def record(self, model, input_tokens, output_tokens, *, session_id, phase, tool_name=None) -> None: ...
      def bill(self) -> dict:  # {"by_session": {...}, "by_phase": {...}, "by_tool": {...}}
      def total(self) -> float: ...
      def flush(self, path) -> None: ...   # append 到 ledger.jsonl（每行一次 record）
      def load(self, path) -> None: ...    # 恢复历史账本
  ```
  每次调用 `compute_cost` 算单次成本，累加进三维账本。**持久化到 JSONL**（`~/.asterwynd/ledger.jsonl`），支持跨 session 历史统计（#78 核心验收："输出单个 session 账单" + 历史可查）。与 trace 解耦（ledger 是财务记录，trace 是过程记录）。
- **`ErrorClassifier` 分类规则（结构化字段优先 + 文本兜底）**：
  ```python
  class ErrorClassifier:
      def classify(self, *, error_type=None, finish_reason=None, text=None) -> ErrorCategory: ...
  ```
  - 结构化字段优先：`error_type` 直接映射（permission_denied→PERMISSION_DENIED、timeout→NETWORK_TIMEOUT、parse_error→PARAMETER_ERROR）；`finish_reason == "max_tokens"` → MODEL_ERROR。
  - 文本兜底：无结构化字段时文本含 `[Permission denied`→PERMISSION_DENIED、`timeout`/`rate limit`→NETWORK_TIMEOUT、`[Error:...` 无匹配→PARAMETER_ERROR。
  - 输出 `ErrorCategory` 枚举 + 每类告警策略（alert_level: immediate/warn/record）。
- **TraceRecorder schema 字段（向后兼容扩展）**：`TraceStep` 加 `timestamp: float`（record 时自动打点，默认值兼容）；`record_iteration` 加 `input_tokens`/`output_tokens`/`model`/`finish_reason`（可选默认 None）；`record_tool_result` 加 `error_type`（可选默认 None）；`to_dict()` 顶层加 `schema_version: "1.1"`。全部向后兼容（新参数带默认值，旧解析忽略）。
- **phase 映射表**：`agent/observability.py` 定义 `PHASE_BY_MODE = {build: "building", read_only: "review", plan: "planning", bypass: "bypass"}` + `resolve_phase(mode)`。**不映射 workflow 四阶段**（dev-workflow 的 wayfinding/planning/building/closing 与本 change 的 runtime mode 不同层，避免混淆）。

**第三轮已确认（实现结构）：**
- **模块划分（平铺，不建子文件夹）**：三个文件领域不同（分类/成本/轨迹），非内聚一类；且 cost_tracker/trace_recorder 已是平铺单文件，移动会破坏既有 import。新增 `agent/observability.py`（ErrorClassifier + ErrorCategory + PHASE_BY_MODE/resolve_phase）平铺，与它们平级。若 #78 第二批膨胀到 ~5+ 观测模块再重构为 `agent/observability/` 子文件夹。
- **CostLedger 持久化位置**：`flush(path)` 由调用方传路径（默认 `~/.asterwynd/ledger.jsonl`），AgentLoop/main 在 run 结束时 flush。第一批不引入配置项（硬编码默认路径，后续可配）。ledger 纯逻辑不依赖配置。
- **TDD 实现顺序**：1) `observability.py`（ErrorClassifier + phase）→ 单测 2) `cost_tracker.py` 扩展（CostLedger + flush/load）→ 单测 3) `trace_recorder.py` 扩展（timestamp + token + error_type + schema_version）→ 单测 4) `loop.py` 接线（record_iteration 传 token；ledger.record）→ 集成测试 5) 全量验证 + spec 同步。

## Reference Implementation Research

- status: enabled
- reason: 可观测性是生产级 agent 系统核心能力，需参考 LangSmith/Langfuse/OpenTelemetry GenAI 的 metrics schema、成本归属、异常分类与回归门禁实现。
- research questions:
  - LangSmith/Langfuse/OTel GenAI 的 metrics schema 与成本归属模型？
  - 异常自动分类的聚类方法？
  - CI benchmark 回归门禁的基线对比与阈值？
- findings:
  - **异常分类业界做法（非关键词规则）**：Langfuse/OTel/arXiv 共识是"事件产生时打结构化属性（gen_ai.usage.*/gen_ai.tool.*/finish_reason），基于属性聚合分类"而非事后文本匹配；分类分两轴（系统错误 vs 语义错误）。语义错误（幻觉）需 LLM judge/人工，不轻易自动判。故本 change 的 ErrorClassifier 用"结构化字段优先 + 文本兜底"，只做系统错误四类分类，幻觉留待后续（与 #73 judge 降级一致）。
  - **成本归属模型**：OTel GenAI 规范以 `gen_ai.usage.input_tokens/output_tokens` 为成本计算基础，按维度（session/operation/tool）归属；本 change 的 CostLedger 对齐此模型（session/phase/tool 三维账本 + JSONL 持久化）。
  - **metrics schema**：OTel GenAI 语义约定（v1.37+）定义 `gen_ai.request.model`/`gen_ai.response.finish_reasons` 等属性；本 change 的 TraceRecorder 扩展（token/model/finish_reason/timestamp/schema_version）对齐该约定，向后兼容扩展不破坏既有 to_json。
- design impact:
  - `agent/observability.py` 新模块：ErrorClassifier（结构化字段优先 + 文本兜底）+ ErrorCategory + PHASE_BY_MODE/resolve_phase。
  - `agent/cost_tracker.py` 扩展 CostLedger（三维账本 + JSONL 持久化）。
  - `agent/trace_recorder.py` 扩展（timestamp + token + error_type + schema_version，向后兼容）。
  - 与 #77/#76 约定：后续沙箱 deny/kill/oom 事件、quality 事件可在本 change 的 trace schema 上扩展。

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
