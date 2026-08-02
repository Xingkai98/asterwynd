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

## 第二批设计（Batch 2）

> 第二批 = 第 4 节（CI 回归门禁）+ 第 5 节（Session timeline 看板）+ 收尾量化（6.3/7.x）。第一批合入（PR #87）后，本批在既有 TraceRecorder/CostLedger/ErrorClassifier 与 benchmark report/statistics 能力上扩展，不改动第一批已合入的事件 schema。

### 4. CI 回归门禁

**Context**：`asterwynd benchmark` 已能运行任务并输出 `runs_dir/<run_id>/tasks/*/result.json`；`benchmarks/report.py` 复用 `benchmarks/statistics.py` 计算 P50/P95/P99、Pass@k、成功率与成本。缺：基线持久化、运行对比、劣化拦截。

#### Decision 5: 门禁为纯逻辑模块 + CLI 薄封装

- **方案**：新增 `benchmarks/gate.py`，提供纯逻辑函数与数据类：`load_baseline(path)`、`compute_run_metrics(run_dir)`、`compare(baseline, current, *, success_rate_drop=0.05, p95_regression_frac=0.05) -> GateVerdict`；`agent/main.py` 新增 `benchmark-gate` CLI 子命令做参数解析与基准运行的薄封装。
- **理由**：门禁判定（阈值、退出码、报告文本）与 IO（跑 benchmark、读 JSON）分离，集成测试直接测纯逻辑，不依赖真实 benchmark 运行。
- **备选**：全逻辑放 CLI。被拒：不可单测，`agent/main.py` 参数已膨胀（benchmark 命令约 130 行参数）。

#### Decision 6: 基线格式 = 提交仓库的 JSON

- **方案**：`benchmarks/baseline.json`：
  ```json
  {
    "schema_version": 1,
    "agent": "fake",
    "model": "",
    "task_set": "<tasks 目录名>",
    "created_at": "2026-08-03T00:00:00Z",
    "metrics": {"success_rate": 1.0, "p95_latency_s": 0.8},
    "per_task": {"<task-id>": {"status": "passed", "duration_seconds": 0.7}}
  }
  ```
  - `success_rate` 口径与 `report.py` 的 `PASS_STATUSES` 一致（`passed`/`passed_with_warnings` 算通过）。
  - `p95_latency_s` 口径与 `report.py._percentile(durations, 0.95)` 一致（nearest-rank，按任务 `duration_seconds`）。
  - `task_set` = tasks 目录名，防止跨任务集误比较（不同任务集 metrics 不可比）。
- **理由**：JSON 可读可 diff；提交进仓库即基线可审计、可随代码评审 review。

#### Decision 7: 阈值语义 = 成功率绝对 5pp / P95 相对 5%

- **方案**：
  - 成功率劣化（拦截）：`baseline.success_rate - current.success_rate > 0.05`（绝对 5 个百分点）。
  - P95 延迟劣化（拦截）：`current.p95_latency_s > baseline.p95_latency_s * 1.05`（相对 +5%）。
  - 无基线：`--require-baseline` 时退出非零并报错；否则输出跳过信息、退出 0。
  - 当前跑无任务（metrics 无法计算）：退出非零并报错。
  - 阈值可配：`--success-rate-drop`（默认 0.05）、`--p95-regression-frac`（默认 0.05）。
- **理由**：成功率用绝对百分点（0.90→0.85 即 5pp 下降）、延迟用相对百分比，是两类指标最直觉的"劣化 >5%"读法。
- **备选**：bootstrap CI 重叠判定。被拒：CI 样本小、环境抖动大时重叠判定几乎必然误报；bootstrap CI 只进报告输出（Decision 8），不进阈值判定。

#### Decision 8: 复用 report.py / statistics.py

- **方案**：gate 用 `report.collect_run_results` 读结果，用与 `report._percentile` 相同口径算 P95；`statistics.bootstrap_ci` 在输出中报告当前跑与基线的 95% CI，供人工判断；`metrics` 计算与 evaluation-report 共用同一来源，避免两套统计漂移。
- **理由**：把"复用 PR #80 statistics（bootstrap CI）"落在确定位置：统计口径复用 + bootstrap CI 作为报告信息。

#### Decision 9: `--update-baseline` 固化基线

- **方案**：`benchmark-gate --update-baseline` 在跑完后把当前 `metrics`/`per_task` 写入 `--baseline` 路径（默认 `benchmarks/baseline.json`）。显式指定表示用户确认覆盖；若已有基线且劣化超阈值，输出警告但允许覆盖（`--update-baseline` 即确认信号）。
- **理由**：信任跑之后固化基线，是门禁可持续的前提；显式标志避免误覆盖。

#### Decision 10: CI 集成 = fake agent 确定性门禁 job

- **方案**：`.github/workflows/ci.yml` 新增 `benchmark-gate` job：`git config user.name/email` 后，fake agent 跑小型确定性任务集（新增 `benchmarks/tasks/gate-smoke/`，含 2 个极快任务），对比已提交的 `benchmarks/baseline.json`（`--require-baseline`）。
- **理由**：fake agent 确定性 → 结果稳定 → 只拦截 benchmark harness/runner/task 基础设施回归，不引入真实 LLM 成本；守护"改进不衰退"证据链的基础设施本身。
- **风险**：CI 跑 git worktree 需要 git 身份配置（job 里显式设置）；若环境无法跑（如无网络克隆外部仓库），该 job 显式失败而非静默跳过——但 gate-smoke 只用本地任务，无网络依赖。

### 5. Session timeline 看板

**Context**：web session 已挂 `TracingHook`（`agent/hooks/builtin/tracing.py`），按执行序记录每次工具调用的 `(tool_name, arguments, duration_ms, success)`。需求：单个 session 的 tool call 耗时可视化，一眼看到哪些调用耗时最长。

#### Decision 11: 数据源 = 复用 TracingHook.calls

- **方案**：新增 `GET /api/sessions/{session_id}/timeline`，从 session 的 AgentLoop hook 链中找到第一个 `TracingHook`，返回其 `calls` 的整形视图：
  ```json
  {
    "session_id": "...",
    "total_calls": 5,
    "max_duration_ms": 1234.5,
    "calls": [
      {"index": 0, "tool_name": "Bash", "duration_ms": 1234.5, "success": true, "bar_pct": 100.0, "arguments": {}}
    ]
  }
  ```
  - `calls` 按 `duration_ms` **降序**返回（后端整形），保留 `index` 原始执行序；`bar_pct = duration_ms / max_duration_ms * 100` 供前端直接设条宽。
- **理由**：TracingHook 已按执行序记录耗时，零新数据采集；耗时排序/条形宽度等整形逻辑放后端（Python 可单测），前端只做极薄渲染。
- **备选**：改 `on_event("tool_result")` 带 duration_ms 从事件流重建。被拒：涉及 loop 事件协议变更；且事件流是实时推送，会话中途连接断开后无法回放，TracingHook 是更可靠的内存源。
- **边界**：TracingHook 是内存态，session 随 server 进程存活；跨进程/重启的历史 session timeline 不在本批范围（trace 持久化是后续批）。

#### Decision 12: 与 TUI 事件粒度对齐

- **方案**：timeline 条目 = 一次 tool_call→tool_result 对；`tool_name` 用工具注册名（与 `trace_recorder.record_tool_result` 同口径）；`duration_ms` 用工具执行耗时（与 trace `tool_result` 的 `duration_ms` 同源）。与 `add-minimal-tui-runtime-view` 的 AgentLoop 事件消费语义对齐，不引入第二套事件模型。
- **理由**：web timeline 与 TUI 共用"loop 内同一工具执行打点驱动"的粒度，避免两套事件口径；本 change 消费 TracingHook（内存态），TUI 消费 on_event 流（推送态），两者数据同源。

#### Decision 13: 前端渲染 = debug 视图 Timeline 面板

- **方案**：`/debug` 视图（`web/static/debug.js`）新增 Timeline 面板：拉取 `/api/sessions/{id}/timeline`，渲染横向条形图（条长 = `bar_pct`，成功绿/失败红，hover 展示 arguments 摘要），提供"刷新"按钮在 run 结束后手动刷新。
- **理由**：debug 视图本就是可观测性展示面（已渲染 tool_call/tool_result 分阶段视图），加 timeline 面板不触碰 chat 消息流渲染、回归风险小；`ASTERWYND_DEBUG=1` 门槛对 demo 可接受且文档化。
- **测试**：看板渲染集成测试 = API 契约测试（字段完整、按耗时降序、`bar_pct` 正确）+ `/debug` 页面 HTML 含 `timeline-container` 容器；前端为纯 JS 且仓库无 JS 测试设施（无 package.json），渲染正确性由"后端整形 + 前端极薄渲染"这一分工保证。

### 6.3/7 收尾量化与校验

- **6.3 benchmark 量化**：新增 `tests/benchmark/test_observability_quantification.py`，确定性验证：(a) CostLedger 已知记录 → `bill()` 分组与总额正确（session 账单可出）；(b) ErrorClassifier 在标注样本集上分类准确率 = 100%（异常分类可量化）；(c) AgentLoop（ScriptedLLM）跑一个工具错误路径 → trace 记录 token + error_type、ledger 有记录（端到端）。真实 LLM 的 benchmark 量化受环境制约，在归档时记录。
- **7.1 grill**：本批进入 building 前完成（本设计即 grill 对象），产出 `reviews/grill-design.md`。
- **7.2 benchmark smoke**：`uv run asterwynd benchmark benchmarks/tasks/gate-smoke --agent fake --source-repo . --runs-dir /tmp/smoke`。
- **7.3 spec 同步**：把本批 spec delta 合并到 `openspec/specs/observability/spec.md`。

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
