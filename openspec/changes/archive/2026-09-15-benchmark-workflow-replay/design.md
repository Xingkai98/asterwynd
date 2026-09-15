# Design: benchmark 三模式与 workflow 可重放

## Context

C1–C4 已交付 subagent 编排的完整产品能力，但 benchmark 只能测「单个 agent 解决单个任务」，测不到编排本身的质量，也没有「可重放」的验收路径。本 change 落地 G6 #177 决议：benchmark 三模式（template / dynamic-record / dynamic-replay）+ 报告字段 + 编排指标，并补齐之前推迟的端到端真实 LLM fan-out 验证。依赖 C2 的 spec 可哈希（`WorkflowSpec.spec_hash`）+ C4 的预算归因数据（`workflow_cost_usd` / 拒绝计数）。

## Goals / Non-Goals

**Goals**

1. benchmark 三模式：`template` / `dynamic-record` / `dynamic-replay`。
2. dynamic-record 保存规范化 workflow 记录（spec + spec_hash + scheduler_version + budget_config + seed/model/temperature）；dynamic-replay 不重跑规划模型。
3. 报告新增 workflow 字段：workflow_mode / workflow_spec_hash / scheduler_version / node_count / run_count / peak_active / queue_wait_s / critical_path_s / workflow_cost_usd。
4. 新增编排指标：冗余度（有用产出 / spawn）、图级步数、拒绝降级计数。
5. 比较口径扩展（不只比 pass rate）+ 对照臂「小 k 高质量 vs 大 N 暴力」。
6. 端到端真实 LLM fan-out 验证（record → replay 可比性）。

**Non-Goals**

- 不做 benchmark 任务集新增（三模式是运行机制，不新造任务）。
- 不做 web 端编排可视化（前序已排除）。
- 不做「模型选了哪条路径」当主观 judge 分（G6 明确判分仍用确定性 verifier）。
- 不做跨机器分布式 replay（单机 asyncio，前序同口径）。

## Decisions

### D1 — 三模式的运行模型

- **`template`**：固定 Pattern/DSL 模板，回归 baseline。用 C2 已落地的 4 个 DSL 模板（`agent/subagent/patterns.py` 编译路径），不涉及模型自由生成。
- **`dynamic-record`**：模型自由生成 workflow（走 `StartWorkflow` 工具原语或 `DeclareWorkflow`），**运行的同时**记录规范化 workflow_record.json。记录内容：`{spec, spec_hash, scheduler_version, budget_config, seed, model, temperature}`。规划阶段与执行阶段同一次 run 完成。
- **`dynamic-replay`**：读已保存的 workflow_record.json，**不重跑规划模型**，离线重放 spec（直接 `StartWorkflow(spec)`）。

**关键区分**：`dynamic-record` 的「记录」是在**执行时旁路采集**（不打断模型自由生成），`dynamic-replay` 是**离线重放**（无规划模型参与）。两者的 `spec_hash` 必须一致（`WorkflowSpec.spec_hash` 是 replay 锚点，`agent/subagent/workflow.py:287-291`）。replay 侧解析必须走 `parse_spec_for_manager`（`agent/tools/builtin/subagents.py:415-417`，注入 `_spec_bounds`），否则三闸默认值退回模块常量（`agent/subagent/workflow.py:35-37`）而非 record 时的配置，同一份 spec dict 会算出不同运行期上限。另注：replay 只是**不重跑规划模型**，各 subagent/aggregate 节点仍会真实调用 LLM（`scheduler._launch_run` → `manager.run_subagent`，`scheduler.py:1537-1546`）。

### D2 — workflow 记录格式（`workflow_record.json`）

`dynamic-record` 每个任务落一份 `workflow_record.json`。**一个任务可能起 0 张、1 张或多张 workflow**（`manager.list_workflows()` 返回的是列表），所以顶层是**记录列表**而不是单个 spec（grill Q1 写法 B）：

```json
{
  "workflow_mode": "dynamic-record",
  "collection_status": "ok",
  "workflows": [
    {
      "workflow_id": "wf_1a2b3c4d",
      "workflow_spec_hash": "...",
      "scheduler_version": "workflow.v1",
      "spec": { ... WorkflowSpec.to_dict() ... },
      "budget_config": { "max_total_tokens": ..., "max_total_cost_usd": ..., ... },
      "seed": 42,
      "model": "deepseek-v4-flash",
      "temperature": 0.0
    }
  ]
}
```

- `spec` 用 `WorkflowSpec.to_dict()`（`agent/subagent/workflow.py:270-285`），replay 时 `parse_workflow_spec` 还原。
- `scheduler_version` = `SCHEMA_VERSION`（`agent/subagent/workflow.py:25`）。
- `budget_config` 来自 C4 的 `WorkflowBudgetConfig`（`agent/config.py:282-296`）。
- `collection_status`：`ok` / `no_workflow`（任务没起图，`workflows: []`）/ `failed`（采集异常，附 `collection_error` + 已采到的部分列表）。
- 采集时**只记真正 `run()` 过的图**：`DeclareWorkflow` 只注册不执行（`agent/tools/builtin/subagents.py:480-484`），未启动的 `declared` 态图不会进 `workflows` 列表（否则 replay 会重放出 record 时并不存在的行为）。
- replay 按列表顺序重放全部；`--workflow-record <run-dir>` 按 `task_id` 定位本文件（见 grill Q8 推荐）。

> 注：本节 schema 已由 meta-review 按 grill Q1 推荐（写法 B）修正；原示例是单对象，与「一任务多图」的代码事实不符。

### D3 — 报告字段收集

`TaskResult`（`benchmarks/models.py:60-108`）与 `AgentRunResult`（`benchmarks/models.py:45-57`）**成对**增 workflow 字段：`workflow_mode` / `workflow_spec_hash` / `scheduler_version` / `node_count` / `run_count` / `peak_active` / `queue_wait_s` / `critical_path_s` / `workflow_cost_usd`（全部默认 `None`，三个不建 manager 的 runner 才不会被构造失败）。

采集点：AsterwyndRunner（`benchmarks/agent_runner.py` 的 `AsterwyndRunner`）在 run 生命周期里，从 subagent manager / scheduler 的 envelope 读取这些字段。C4 的 `status()` envelope 已有 `peak_active`/`critical_path_s`/`total_cost`；`node_count`/`run_count`/`queue_wait_s` 需从 scheduler 补暴露（C4 已暴露部分，queue_wait_s 可零新字段在 scheduler 内算出，见 grill Confirmed Decision 5）。

**取数前提（meta-review 补，grill 新增 Confirmed Decision 14）**：`workflow_cost_usd` / envelope 的 `total_cost` 都读 `manager.cost_ledger`（`agent/subagent/scheduler.py:1945-1952`），而 benchmark 路径今天**从未给 manager 注入 `CostLedger`**（`benchmarks/agent_runner.py:312-318` 构造 manager 时无此参数 → `manager.py:345,358` 默认 `None` → `agent/loop.py:1090` 的 `if self.cost_ledger:` 整段跳过）。实现必须先给 `AsterwyndRunner` 注入一个 ledger 并透传，否则本字段在全 C5 任务里恒为 0（假数据）。

### D4 — 编排指标（冗余度 / 图级步数 / 拒绝降级计数）

- **冗余度** = 有用产出 / spawn 总数。有用产出 = 被下游**实际消费**的 run（`_collect_slots` 合并时打标；terminal 进 root result 也算一次消费，见 grill Q2 推荐）；spawn 总数 = workflow 级 `manager.spawn_count()` **快照**（含 create_subagent + 真实 run，不含 queue_full；必须在 `scheduler.run()` finally 释放桶前取值并新暴露进 envelope，见 grill Q2/Confirmed Decision 7）。spawn 总数为 0 时记 `None` 不记 0。值越低越健康（吸收 #68110 教训）。
- **图级步数** = 调度器的 `steps`（C2 的 superstep 计数，`scheduler._steps`，初始化 `scheduler.py:370`、envelope 暴露 `:2041`）。
- **拒绝降级计数** = 护栏拒绝/降级的累计，**四类**：queue_full + 深度撤工具（spawn tool withdrawn）+ spawn 预算拒绝 + 图级 recursion 超限（对应 C1 护栏、C2 图闸、C4 预算闸三处来源）。这个计数反映「模型撞了几次护栏」，是编排质量的负向信号。拆款：`depth_capped_runs` **并入**本总量；`queue_cancelled_runs`（Q4）**单列、不并入**（它是分母侧量，语义见 Q4 推荐）。

指标采集不侵入执行：从 scheduler/manager 的既有状态字段汇总，**不新增执行路径分支**。注意区分「不新增执行分支」与「新增计数器」：四类拒绝来源里三类今天没有现成信号（queue_full 被 `_apply_run_status` 折成 failed、深度撤工具在 `manager.py:1136-1137` 无回传、spawn 预算拒绝只能字符串匹配 `RuntimeError`），实现要给 manager 加计数器并在既有分支里自增——这是 instrumentation，不是新执行路径（见 grill Confirmed Decision 8 与 Q3/Q4 推荐）。

### D5 — 报告渲染与比较口径

`benchmarks/report.py` 的 `render_report`/`render_html`（`benchmarks/report.py:172`、`:351`，实现同走 `_render` `:191-349`）增 workflow 字段段 + 编排指标段。**渲染粒度待用户拍板（grill Q9）**：推荐独立 section（只统计有 workflow 的记录，主表仅加一列 `workflow_mode`），避免 null 单元格污染主表与 pass@k 聚合口径。比较口径（`benchmarks/compare.py` 已存在，`load_run` `:92-102`、`build_summary` `:105-212`、`build_html` `:282-408`）从「pass rate」扩展为：完成率 + 总 token + $/resolved-task + wall time + 节点数 + 峰值并发 + 关键路径 + 失败原因。新增字段一律照 compare.py 的「raw dict 宽松读」风格（`r.get("workflow_mode")`），否则读旧 artifact 会 KeyError。

对照臂：`template`（固定 baseline）vs `dynamic-record`（自由生成）vs `dynamic-replay`（同 spec 重放）。「小 k 高质量 vs 大 N 暴力」用 `max_active`/`max_spawns` 配置差异表达（小 k = 低并发高配额，大 N = 高并发低配额）；两者是 `SubagentsConfig` 字段（`agent/config.py:336-338`），走 config YAML（grill Q5 推荐通道 X），与 Q8 的 CLI 接线正交。「大 N」臂的 `spawn budget exceeded` 是预期压力结果，报告须标注而非当故障。

### D6 — 端到端 fan-out 验证

新增一个 benchmark 验证任务（走 `dynamic-record`），用真实 LLM（本地 `deepseek-v4-flash`，见记忆）跑：模型自由生成一个 fan-out workflow（如「调研 N 个文件 → 汇聚」），record 落盘 → dynamic-replay 重放 → 断言两次跑的关键字段可比。

**可比性口径（grill Q6 推荐：fake 定可比）**：硬断言全部放在 **fake LLM** 场景（同一编排脚本 → `spec_hash`/`node_count`/`run_count`/`status` 全等；fake 下 `cost` 恒 0，属平凡断言）；真实 LLM 场景只硬断言 `spec_hash` 相等 + record/replay 无异常完成，`cost`/`run_count`/`peak_active`/`critical_path_s` **只报不判**（wall-clock 与 token 噪声会 flaky）。原「cost 在误差内」的措辞已按 Q6 收敛，不再设容差。

**降级策略**：真实 LLM 不可用时，降级为 fake round-trip，并在每个任务的 `result.json` 记录「端到端真实 LLM 验证未执行 + 原因 + 替代验证 + 缺口」（grill Q7 推荐落点 A，机器可读字段 `e2e_llm_verified: false` 等），不静默当已验证。

## Pre-Implementation Review

> 本 change 为架构级改造（benchmark 运行模型扩展 + 可重放协议），实现前需按 AGENTS.md 走 `batch-grill-me`（或等价独立 subagent 设计追问）审视本 design.md 的 D1–D6，逐项确认实现细节、依赖、风险与测试策略，产出结构化决策记录到 `reviews/grill-design.md`，并经停轮确认（grill-confirmation-gate）。本节为占位声明，实际 review 记录以 `reviews/grill-design.md` 为准。

## Risks / Trade-offs

- **风险**:dynamic-record 的「记录」若打断模型自由生成会改变行为 → 记录是**旁路采集**（执行时不阻塞、不改 spec），采集失败不影响 run 完成。
- **风险**:replay 的 spec 若依赖动态状态（foreach source 来自上游产出）离线重放会缺上下文 → replay 只支持「spec 完整自包含」的 workflow（`items` 静态声明或 source 指向 replay 时已物化的 slot）；动态 source 缺料时 replay 报错并标 `unsupported`（不静默）。
- **风险**:`queue_wait_s` 若 scheduler 未暴露需新增字段，改动面扩大到 scheduler → **已收敛（grill Confirmed Decision 5）**：排队时长数据今天就在 run record 上（`SubagentRunRecord.created_at` `manager.py:91` / `started_at` `:92`，赋值 `manager.py:817`），scheduler 自持 `self._run_refs`（`scheduler.py:379`），可在 scheduler 内直接算，**零新字段**。本风险前提不成立，保留原始判断记录。
- **Trade-off**:workflow 字段让 `TaskResult` 变宽 → 字段全可选（默认 None 不改变既有 task 语义），旧 artifact 向后兼容（`benchmarks/models.py:93-102` 的 `from_dict` 只保留 `__dataclass_fields__` 里的键、未知键静默忽略）。
- **Trade-off**:端到端真实 LLM 验证依赖本地 LLM 可用性 → 降级策略明确，不静默。

## Testing Strategy

- 三模式 round-trip：template 跑通 baseline；dynamic-record 落 workflow_record.json；dynamic-replay 从 json 重放、spec_hash 一致。
- 报告字段：node_count/run_count/peak_active/queue_wait_s/critical_path_s/workflow_cost_usd 渲染正确。
- 编排指标：冗余度 = 有用产出/spawn；图级步数；拒绝降级计数（queue_full + 深度撤工具 + spawn 拒绝 + 图级超限）。
- replay 确定性：同 spec 两次跑结果可比（字段一致）。
- 端到端：真实 LLM 可用时 fan-out record→replay；不可用时 fake round-trip + 记录未验证事实。
- 兼容：既有 benchmark 任务（无 workflow）TaskResult 字段为 None，报告不崩。
- 全量 pytest 绿 + benchmark smoke + OpenSpec validate + artifact checker。
