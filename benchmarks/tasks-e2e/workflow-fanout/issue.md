# Fan-out workflow end-to-end verification task

本任务**不是**主任务集的成员，只服务 change `benchmark-workflow-replay`（C5）的
端到端验证：真实 LLM 自由生成一张 fan-out 图 → record 落盘 → dynamic-replay 重放
→ 断言两次跑的 `workflow_spec_hash` 相等且都无异常完成（grill Q6 乙）。

## Task

调研本仓库的三个模块，然后把调研结论汇聚成一份报告文件 `WORKFLOW_FANOUT.md`。

要求**用 workflow 编排工具**完成，而不是自己顺序读三个文件：

1. 先用 `DeclareWorkflow` 声明一张图，goal 写 `"research three modules and aggregate"`；
2. 图里至少有三个并行调研节点（`subagent`）与一个 `aggregate` 汇聚节点；
3. 用 `StartWorkflow` / `RunWorkflow` 跑它；
4. 把汇聚结果写进 `WORKFLOW_FANOUT.md`。

## Modules to research

- `agent/subagent/scheduler.py`
- `agent/subagent/manager.py`
- `agent/subagent/workflow.py`

## Requirements

- 每个调研节点回答「这个模块负责什么」一句话；
- 汇聚节点把三句话合并；
- 最终 `WORKFLOW_FANOUT.md` 必须包含三个模块名各一次。
