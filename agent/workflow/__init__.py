"""Workflow 子系统（当代）：事件日志投影、受保护写通道校验与投影原语。

四阶段状态机（phase/sub_state 推进、`handoff.json` 驱动、gate 停止）实现已退役
（change `retire-4phase-state-machine`），其 orchestrator / dispatch / role registry /
doc-artifact protocol 与 `flow/` 声明式引擎一并删除。本包保留的是**活**部分：

- `event_log`：`workflow-events.jsonl` 事件日志与投影（checker 与 guard 同源消费）；
- `state_machine`：转移校验与 hints 原语（`event_log` 的活依赖）；
- `models` / `routing` / `resume_audit` / `review_manifest`：投影模型、开关与写通道。

本 `__init__` 刻意**不 re-export** 子模块符号：包 `__init__` 先于任何子模块导入执行，
一旦在此 import 已删除的模块，`from agent.workflow.event_log import ...`
（`check_openspec_artifacts` 与 `workflow_guard` 的活路径）会直接 `ModuleNotFoundError`。
"""
