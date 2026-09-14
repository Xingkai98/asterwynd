# Tasks: Workflow 结果聚合

## 0. 设计追问（实现前门禁）

- [ ] 0.1 跑 `batch-grill-me`（或等价设计追问）审视 design.md D1–D6，产出 `reviews/grill-design.md`（≥3 Confirmed Decisions + Open Questions 停轮确认）。

## 1. workflow store + result_ref 落盘

- [ ] 1.1 `agent/subagent/workflow_store.py`：result_ref 落盘（每 run 独立文件 + 原子写）+ 事件日志。
- [ ] 1.2 `SubagentRunRecord.to_result_dict` 增 `summary_ref`/`transcript_ref`/`artifact_refs`，默认返回 bounded summary + refs。

## 2. 分层汇聚

- [ ] 2.1 显式 aggregate 树（模型声明）+ 调度器自动兜底（单 aggregate 直接上游 >10 或总叶子数 >10 时自动插分层）。
- [ ] 2.2 分层 token 预算（leaf 300 / shard 800 / domain 1500 / root 3000，可配置）。
- [ ] 2.3 复用 MemoryManager 的 L1/L2 summarizer + 新增 workflow 级汇聚器。

## 3. bounded envelope + bus 降级

- [ ] 3.1 父 agent 永远 bounded envelope（workflow_id/status/completed/failed/pending/root_result_ref）。
- [ ] 3.2 GetWorkflow 带 detail 参数（按需读取子级结果）。
- [ ] 3.3 bus 降级为非权威（权威状态/重放进 workflow store/事件日志）。

## 4. 配置

- [ ] 4.1 自动兜底阈值 + 四档 token 预算入 `SubagentsConfig`（`subagents.workflow.*`），`_parse_subagents_config` 逐字段解析。

## 5. 测试与收尾

- [ ] 5.1 新增 result_ref 落盘/读取、分层汇聚自动兜底、bounded envelope、四档预算、bus 降级测试。
- [ ] 5.2 100 leaf 不撑爆父上下文 + bus 丢消息不影响完成 + checkpoint/resume 恢复结果 ref。
- [ ] 5.3 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 冒烟通过。
- [ ] 5.4 同步 current spec：把 spec delta 合入 `openspec/specs/multi-agent-collaboration/spec.md`（当前规格 sync 任务）。
- [ ] 5.5 `uv run pytest -q` 全绿；OpenSpec validate + artifact checker 通过。
