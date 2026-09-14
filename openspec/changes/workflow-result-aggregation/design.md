# Design: Workflow 结果聚合

## Context

C2 交付了 Workflow DSL + 统一调度器，但结果传递是「完整 summary 直传」：没有 result_ref 落盘、没有分层汇聚，父 agent 拿到全量节点结果。当模型自由声明上百个 subagent 时，父上下文被撑爆。本 change 落地 G4 #175 决议：result_ref 落盘 + 分层汇聚 + bounded envelope + 四档预算 + bus 降级。依赖 C2 的 DAG。

## Goals / Non-Goals

**Goals**

1. result_ref 落盘 artifact（完整结果/transcript 落盘，内存只持 bounded summary）。
2. 树状汇聚 = 显式 aggregate + 调度器自动兜底。
3. 父 agent 永远 bounded envelope。
4. 分层 token 预算（leaf 300 / shard 800 / domain 1500 / root 3000）。
5. bus 降级为非权威通道。

**Non-Goals**

- 不做 workflow 级总预算 / 成本归因（C4）。
- 不做 benchmark replay（C5）。
- 不做每个 subagent 单独设模型。
- 不做 web 端编排可视化。

## Decisions

### D1 — result_ref 落盘 artifact（独立 subtree，不复用 checkpoint 命名空间）

完整结果/transcript 落盘到 workflow store（`agent/subagent/workflow_store.py`），`result_ref` 指向文件路径。**独立 subtree** `<workspace_root>/.asterwynd/workflows/<workflow_id>/`，不复用 `SubagentSnapshotStore` 的目录命名空间（`SessionStore.remove()` 是 `shutil.rmtree` 整个 run 目录，复用会让 checkpoint 清理连结果一起删；且 `SessionStore.save()` 有 dedup skip，「写完再读」测试会看到不存在文件）。

`SubagentRunRecord.to_result_dict` 增 `summary_ref` / `transcript_ref` / `artifact_refs`。**正常完成的 run 不写 checkpoint**（`_write_checkpoint` 只在异常/取消分支），所以「完整结果落盘」是**新增写点**，在成功路径显式触发。`artifact_refs` 当前零生产者，本 change 明确定义其填充时机（否则恒为 `[]`）。

### D2 — 树状汇聚 = 显式 + 自动兜底

- 模型在 DSL 里**显式声明 aggregate 节点**组成树（leaf→shard→domain→root）。
- 调度器**自动兜底**：检测到「单 aggregate 直接上游 >10」（max fan-in=10）或「总叶子数 >10」时自动插入分层 aggregate。**声明期 + 展开期都算**（foreach 展开项数声明期不可知）。
- 分层 token 预算（G4 决议）：leaf 300 / shard 800 / domain 1500 / root 3000，可配置。**预算档按「距 leaf 层数」判**（第 1 层 shard 800，再上 domain 1500，根 root 3000）。
- **自动插层按 fan-in 分组**（`shard_count=ceil(leaf/10)`，逐层向上直到 root 输入 ≤10），不按 `ceil(log10(n))` 层数公式（会过度分层）。
- **auto aggregate 默认 `strategy="llm"`**（collect 只是文本拼接、不解决 prompt 膨胀）；auto 节点预算计入 `max_nodes` + `max_runs`。
- **部分显式树也触发兜底**（只补缺失层，已声明层保留）。

### D3 — 父 agent 永远 bounded envelope

父 agent 只拿到：

```json
{
  "workflow_id": "wf-123",
  "status": "running",
  "total": 100,
  "completed": 73,
  "failed": 4,
  "cancelled": 0,
  "budget_exceeded": 0,
  "blocked": 0,
  "pending": 23,
  "latest_events": [...],
  "root_result_ref": "artifact://workflow/wf-123/root"
}
```

- **分母 = 逻辑执行单元**（普通节点=1、foreach=展开项数含容器）；`blocked` 是终态、单独计数；`cancelled`/`budget_exceeded` 单列不混 `failed`。保留旧 `completed`/`failed` run 计数字段兼容（`WorkflowScheduler.run()` 返回值语义不动）。
- 不看子级详细结果；要看再显式 inspect（新增只读工具 `ReadWorkflowResult(ref, offset, limit)` 分页读 artifact 正文；GetWorkflow detail 返回节点级摘要列表）。

### D4 — bus 降级为非权威

MessageBus 只做低延迟广播/非关键提示；权威状态、依赖完成、结果完整性、重试、重放全部进 workflow store/事件日志。bus 丢消息不影响 workflow 完成与结果正确性。

### D5 — 复用 summarizer 抽象（非 MemoryManager 私有字段）

复用 `agent/context/summarizer.py` 的 `Summarizer` Protocol / `compress(tier_summaries, budget)`（`MemoryManager` 的 L1/L2 是实例私有、绑定单 AgentLoop messages，无直接复用入口）；新增 workflow 级汇聚器，输入是「多节点 result_ref / summary 字符串」。

### D6 — 分层汇聚阈值可配置（嵌套 AggregationConfig）

自动兜底阈值 + 四档 token 预算作为**嵌套 `AggregationConfig`**（`thresholds` + `token_budgets` 两个子 dataclass，均 frozen + `field(default_factory)`）挂成 `WorkflowLimitsConfig.aggregation`；`_parse_workflow_limits` 多调 `_parse_aggregation` 显式逐字段解析。四档预算校验**非递减（允许相等）**，拒绝严格递减。

### D7 — 三种结果表示（codex 修正）

拆三种表示，`to_result_dict` 不承担双接口：

1. **artifact**：完整结果，落盘；
2. **scheduler internal**：供下游调度使用的 full formatter（`_node_task_text`/`_aggregate_task_text` 消费 bounded summary/ref，不是 concat 后的全文）；
3. **parent/public envelope**：bounded summary + refs。

层级中间节点必须消费 bounded summaries/ref，否则 100-leaf 的 prompt 膨胀依然发生（`_aggregate_task_text` 拼全文是真正的爆点）。

## Pre-Implementation Review

> 本 change 为架构级改造（结果传递语义重构），实现前需按 AGENTS.md 走 `batch-grill-me`（或等价独立 subagent 设计追问）审视本 design.md 的 D1–D6，逐项确认实现细节、依赖、风险与测试策略，产出结构化决策记录到 `reviews/grill-design.md`，并经停轮确认（grill-confirmation-gate）。本节为占位声明，实际 review 记录以 `reviews/grill-design.md` 为准。

## Risks / Trade-offs

- **风险**:落盘 artifact 的读写竞态（多节点并发写同一 workflow store）→ 每 run 独立文件 + 原子写，result_ref 按 run_id 定位。
- **风险**:自动兜底分层与模型显式 aggregate 树的冲突 → 兜底只在「模型没建树且超阈值」时触发，显式树优先。
- **Trade-off**:result_ref 落盘换上下文安全，代价是 I/O 开销 + 落盘生命周期管理（进程重启后 result_ref 是否可解析）→ 复用 checkpoint 的 for_workspace 纪律，落盘生命周期与 checkpoint 一致。
- **Trade-off**:bounded envelope 让父 agent 看不到细节，代价是父可能需要多次 inspect 才能收敛 → GetWorkflow detail 参数提供按需读取。

## Testing Strategy

- 新增 result_ref 落盘/读取测试、分层汇聚自动兜底测试、bounded envelope 测试、四档 token 预算测试、bus 降级测试。
- 100 个 leaf 不把 100 个完整结果注入父上下文。
- bus 丢消息不影响 workflow 完成与结果正确性。
- checkpoint/resume 后能恢复 workflow 状态 + 结果 ref。
- 全量 pytest 绿 + benchmark smoke + validate + artifact checker。
