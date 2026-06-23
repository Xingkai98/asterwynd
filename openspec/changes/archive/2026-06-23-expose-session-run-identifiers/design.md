## Context

当前 Web session id 主要存在于 WebSocket 路径和 session_created 事件中。CLI、日志、trace 和 benchmark 没有统一展示 session id / run id。

## Goals / Non-Goals

**Goals:**

- 用户能在 Web UI / CLI / TUI 看到可复制的标识。
- 日志和 trace 能用 run id 关联一次 Agent 运行。
- benchmark artifact 能记录 Agent 运行标识，同时不改变 benchmark 批次 run id 的既有含义。

**Non-Goals:**

- 不实现分布式 tracing 系统。
- 不改变 benchmark run_id / task_id 的既有含义。
- 不引入数据库。

## Decisions

### Decision 1: 只区分 session id 和 run id

session id 表示一次交互式会话；run id 表示一次 AgentLoop 运行。同一个 session id 下可以产生多个 run id。CLI 单次运行是只有一个 session id 和一个 run id 的特殊情况。Web、CLI 交互模式和未来 TUI 都复用这组术语。

### Decision 2: 标识先用于排查，不作为权限边界

这些 id 不承担鉴权或安全边界职责，只用于可观察性。

### Decision 3: 不引入独立 correlation id

correlation id 不作为独立概念或第三套生命周期存在。需要通用关联字段时，直接使用 session id 和 run id。

## Risks / Trade-offs

- [Risk] id 术语混乱。Mitigation: 在 CONTEXT 或规格中明确 session/run 的边界。
- [Risk] 日志泄漏过多上下文。Mitigation: 只记录随机 id，不记录敏感 prompt。

## Testing Strategy

- Web session 测试确认 session_created 和页面展示 id。
- CLI 测试确认输出 run id。
- Trace / benchmark 测试确认 artifact 包含 session id / run id。
- benchmark smoke 覆盖 artifact 写入链路。
