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

### D1 — result_ref 落盘 artifact

完整结果/transcript 落盘到 workflow store（`agent/subagent/workflow_store.py`），`result_ref` 指向文件路径；内存只持 bounded summary。复用 C1/C2 的 checkpoint 机制（`SubagentSnapshotStore.for_workspace` 已落 `<workspace_root>/.asterwynd/subagents/`）。

`SubagentRunRecord.to_result_dict` 增 `summary_ref` / `transcript_ref` / `artifact_refs`，默认返回 bounded summary + refs，完整 transcript 显式 inspect。

### D2 — 树状汇聚 = 显式 + 自动兜底

- 模型在 DSL 里**显式声明 aggregate 节点**组成树（leaf→shard→domain→root）。
- 调度器**自动兜底**：检测到「单 aggregate 直接上游 >10」或「总叶子数 >10」时自动插入分层 aggregate。
- 分层 token 预算（G4 决议）：leaf 300 / shard 800 / domain 1500 / root 3000，可配置。

### D3 — 父 agent 永远 bounded envelope

父 agent 只拿到：

```json
{
  "workflow_id": "wf-123",
  "status": "running",
  "completed": 73,
  "failed": 4,
  "pending": 23,
  "latest_events": 5,
  "root_result_ref": "artifact://workflow/wf-123/root"
}
```

不看子级详细结果；要看再显式 inspect（GetWorkflow 带 detail 参数 / InspectSubagentTranscript）。语义统一、防炸。

### D4 — bus 降级为非权威

MessageBus 只做低延迟广播/非关键提示；权威状态、依赖完成、结果完整性、重试、重放全部进 workflow store/事件日志。bus 丢消息不影响 workflow 完成与结果正确性。

### D5 — 复用 MemoryManager 的 L1/L2 分层摘要能力

复用 `agent/memory/manager.py` 的 L1/L2 分层摘要能力（`_l1_chunks`/`_l2_summary`/`_tiers`）的 summarizer；但新增 workflow 级汇聚器，因为 MemoryManager 压缩的是单个 AgentLoop 的 messages，不能替代 workflow 级分层汇聚。

### D6 — 分层汇聚阈值可配置

「单 aggregate 直接上游 >10」「总叶子数 >10」的自动兜底阈值、四档 token 预算，均作为 `SubagentsConfig` 的可配置项（`subagents.workflow.*`），`_parse_subagents_config` 逐字段解析。

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
