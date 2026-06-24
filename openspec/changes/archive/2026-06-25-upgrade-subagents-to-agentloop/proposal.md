## Why

当前 `SubAgentManager` 只是后台调用一次 `llm.chat`，不能执行工具循环，也不能像主 agent 一样读文件、搜索、产出 trace 或承载多轮编排。它适合轻量问答，但不能承担“并行调查某个子问题”或“维护多个长期存在的子 worker”这类 coding-agent 子任务。

在 mode policy 和 planning state 稳定后，subagent 不应继续停留在一次性 helper 形态，而应升级为 **受限的子 session runtime**：子 agent 拥有自己的 session identity、transcript、mode、run 历史和 trace，父 agent 通过显式运行时接口管理它们。

## Change Type

- primary: feature
- secondary: []

## What Changes

- `SubAgentManager` SHALL 从轻量 LLM 委托升级为子 session runtime manager。
- 子 agent SHALL 具备独立 transcript、mode、run 历史、trace 和工具集合。
- 系统 SHALL 支持多个子 session 并发存在，并允许同一子 session 承载多次 run。
- 父 agent SHALL 通过显式运行时接口创建、运行、查询、等待、取消和检查子 session。
- 子 session 默认 SHALL 使用 `isolated` 上下文，且其 mode / 工具权限 SHALL 不得高于父 agent。
- 子结果、摘要、usage 和 transcript inspect SHALL 以结构化接口暴露，不直接破坏父 AgentLoop 的 tool-call 链。

## Capabilities

### Modified Capabilities

- `subagents`: 从轻量 LLM 委托升级为完整子 session runtime。
- `agent-runtime`: 支持父 run 与子 session / 子 run 的显式运行时协作。
- `tool-system`: 子 session 工具权限、mode 继承和 inspect 接口受 runtime policy 约束。

## Dependencies

- 建议依赖 `introduce-agent-mode-policy`。
- 建议依赖 `implement-structured-planning-state`。
- 建议依赖 `expose-session-run-identifiers`。

## Impact

- 影响代码：
  - `agent/subagent/`
  - `agent/loop.py`
  - `agent/trace_recorder.py`
  - `web/session.py`
  - `cli.py`
- 影响测试：
  - `tests/agent/subagent/`
  - `tests/agent/test_loop.py`
  - `tests/web_tests/`
  - `tests/test_cli.py`
- 不实现跨进程 worker，不实现分布式任务队列，不实现用户直接切换到子 session 聊天。
