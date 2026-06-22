## Why

当前 SubAgentManager 只是后台调用一次 `llm.chat`，不能执行工具循环，也不能像主 agent 一样读文件、搜索或产出 trace。它适合轻量问答，但不能承担“并行调查某个子问题”的 coding-agent 子任务。

在 mode policy 和 planning state 稳定后，可以把 subagent 升级为受限 AgentLoop，并通过 ParentChannel 回传结构化结果。

## Change Type

- primary: feature
- secondary: []

## What Changes

- SubAgentManager SHALL 能为子任务创建受限 AgentLoop。
- 子 agent SHALL 使用独立 messages、工具集合、mode 和 trace。
- ParentChannel SHALL 回传完成、失败、取消和摘要信息。
- 主 AgentLoop SHALL 能安全接收子 agent 结果，不破坏 tool-call 链。

## Capabilities

### Modified Capabilities

- `subagents`: 从轻量 LLM 委托升级为受限 AgentLoop 委托。
- `agent-runtime`: 支持父子运行时协作事件。
- `tool-system`: 子 agent 工具权限受 mode policy 约束。

## Dependencies

- 建议依赖 `introduce-agent-mode-policy`。
- 建议依赖 `implement-structured-planning-state`。

## Impact

- 影响代码：
  - `agent/subagent/`
  - `agent/loop.py`
  - `agent/trace_recorder.py`
- 影响测试：
  - `tests/agent/subagent/`
  - `tests/agent/test_loop.py`
- 不实现跨进程 worker，不实现分布式任务队列。
