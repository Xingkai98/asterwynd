# Proposal: Workflow 结果聚合（workflow-result-aggregation）

关联跟踪 issue：[#183](https://github.com/Xingkai98/asterwynd/issues/183)。wayfinder 地图：[#170](https://github.com/Xingkai98/asterwynd/issues/170)。决策票：G4 [#175](https://github.com/Xingkai98/asterwynd/issues/175)。依赖 C2 [#181](https://github.com/Xingkai98/asterwynd/issues/181)（已合入）。

## Change Type

- primary: feature
- secondary:
  - agent-runtime
  - subagent

## Why

C2 `workflow-dsl-scheduler`（#181，已合入）交付了 Workflow DSL + 统一调度器，但**结果传递仍是「完整 summary 直接汇给下游」**——没有 `result_ref` 落盘、没有分层汇聚、父 agent 拿到的是全量节点结果。当模型自由声明几十~上百个 subagent 时，这会让父 agent 上下文被 100 个结果直接撑爆。

这是 wayfinder #170 的 Destination 核心——「模型自由构建几十~上百个 subagent 协作流程」。G4 #175 已定稿结果传递与上下文策略：result_ref 落盘 artifact + 分层汇聚（显式 aggregate + 调度器自动兜底）+ 父 agent 永远 bounded envelope + 四档 token 预算 + bus 降级。本 change 落地该决议。

业界依据（R1 #171 调研）：Claude Code 子结果只回 summary、中间输出不回父（隔离）；LangGraph reducer 做无损合并。本 change 借鉴这两者 + 复用本仓既有 checkpoint 机制（`agent/subagent/snapshot.py`）。

## What Changes

- **result_ref 落盘 artifact**：完整结果/transcript 落盘到 workflow store，`result_ref` 指向文件；内存只持 bounded summary。复用 C1/C2 的 checkpoint 机制（`SubagentSnapshotStore`）。`SubagentRunRecord.to_result_dict` 增 `summary_ref`/`transcript_ref`/`artifact_refs`。
- **树状汇聚 = 显式 aggregate + 调度器自动兜底**：模型显式声明 aggregate 树；调度器检测到「单 aggregate 直接上游 >10」或「总叶子数 >10」时自动插入分层 aggregate。
- **父 agent 永远 bounded envelope**：父只拿 workflow_id/status/completed/failed/pending/root_result_ref，不看子级详细结果，要看再显式 inspect（GetWorkflow 带 detail 参数 / InspectSubagentTranscript）。
- **分层 token 预算**：leaf 300 / shard 800 / domain 1500 / root 3000（可配置）。
- **bus 降级**：bus 只做低延迟广播/非关键提示；权威状态、依赖完成、结果完整性、重试、重放全部进 workflow store/事件日志。

## Capabilities

### New Capabilities

无新能力域；在既有 `multi-agent-collaboration` 能力域上深化。

### Modified Capabilities

- `multi-agent-collaboration`: 结果传递从「完整 summary 直传」演进为「result_ref 落盘 + 分层汇聚 + bounded envelope」；bus 降级为非权威通道。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 架构级改造（结果传递语义重构），走 grill 的非平凡 change，命中 `full` 判据。
- research questions:
  1. Claude Code 的子结果隔离（只回 summary、中间输出不回父）怎么借鉴？
  2. LangGraph 的 reducer 无损合并语义？
  3. 分层汇聚的 token 预算分层怎么定？
- findings: 见 wayfinder R1 #171 决议（已关闭）。核心结论——
  - **子结果隔离**（Claude Code）：非 fork 子 agent 全新隔离 context，只把最终 summary 返回给父；嵌套时中间输出不回主会话。但官方 caveat 明说「跑很多子 agent 各自返回详细结果会消耗可观 context」——隔离≠免费，父上下文预算仍要单独管。
  - **reducer 无损合并**（LangGraph）：并行分支写同一槽必须声明 reducer，否则 `InvalidUpdateError`。本 change 的 result_ref 是「引用传递」而非「值合并」，reducer 已由 C2 的 outputs 字段 + 枚举落地。
  - **分层 token 预算**（Codex 架构评审建议值）：leaf 300 / shard 800 / domain 1500 / root 3000，每层固定输出预算、可配置。
- design impact: 见 design.md D1–D6；分层汇聚与 bounded envelope 直接来自 G4 #175 决议。

## Impact Analysis

- **能力域**: `multi-agent-collaboration`（结果传递 + 分层汇聚）。
- **代码**: 新增 `agent/subagent/workflow_store.py`（result_ref 落盘 + 事件日志）；改 `agent/subagent/scheduler.py`（分层汇聚自动兜底 + bounded envelope 返回）、`agent/subagent/manager.py`（`to_result_dict` 增 refs）、`agent/subagent/bus.py`（降级为非权威）、`agent/tools/builtin/subagents.py`（GetWorkflow detail 参数）。
- **测试**: 新增 result_ref 落盘/读取测试、分层汇聚自动兜底测试、bounded envelope 测试、四档 token 预算测试、bus 降级测试；既有 workflow/scheduler 测试兼容。
- **文档**: `docs/openspec-change-backlog.md`（C3 状态）、wayfinder #170（引用）。
- **流程（process）**: 本 change 是 C3；C4 `workflow-budget-attribution` 依赖本 change 的 result_ref 落盘（成本归因按 node/edge 分桶需要结果落盘作锚点）。
