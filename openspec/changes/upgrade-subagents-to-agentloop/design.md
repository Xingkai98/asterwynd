## Context

当前 SubAgentManager 只是后台调用一次 `llm.chat`，不能执行工具循环，也不能产出与主 agent 一致的 trace。它适合轻量问答，但不能承担并行调查代码、读取文件或运行受限工具的 coding-agent 子任务。

在 mode policy 和 planning state 稳定后，可以把 subagent 升级为受限 AgentLoop。

## Goals / Non-Goals

**Goals:**

- 子任务可创建受限 AgentLoop。
- 子 agent 使用独立 messages、工具集合、mode 和 trace。
- ParentChannel 回传完成、失败、取消和摘要信息。
- 主 AgentLoop 安全接收子 agent 结果。

**Non-Goals:**

- 不实现跨进程 worker。
- 不实现分布式任务队列。
- 不让子 agent 绕过父 agent 权限。
- 不破坏 LLM tool-call 链。

## Decisions

### Decision 1: 子 agent 复用 AgentLoop

SubAgentManager 为子任务构造受限 AgentLoop，而不是维护第二套简化循环。

理由：工具调用、trace、hooks 和 memory 行为应与主 agent 一致。

### Decision 2: ParentChannel 只传结构化结果

子 agent 通过 ParentChannel 回传状态、摘要、错误和必要 artifact 引用，不直接修改父 messages。

理由：保持父子运行时边界，避免破坏 tool-call 协议链。

### Decision 3: 子 agent mode 默认更保守

子 agent 工具权限由父任务和 AgentMode 决定，默认不高于父 agent。

理由：委托不应扩大权限。

## Risks / Trade-offs

- [Risk] 并发子任务增加复杂度。Mitigation: 初版限制并发和超时，trace 记录每个子任务。
- [Risk] 父子消息链混乱。Mitigation: 子 agent 使用独立 messages，只传摘要结果。
- [Risk] 子 agent 消耗过多 token。Mitigation: 为子任务设置预算和取消机制。

## Testing Strategy

- SubAgentManager 测试覆盖创建、完成、失败和取消。
- AgentLoop 集成测试覆盖子 agent 工具调用。
- ParentChannel 测试覆盖结果注入不破坏父 tool-call 链。
- trace 测试覆盖父子任务关联。
