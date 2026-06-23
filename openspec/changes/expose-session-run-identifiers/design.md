## Context

当前 Web session id 主要存在于 WebSocket 路径和 session_created 事件中。CLI、日志、trace 和 benchmark 没有统一展示同一个排查标识。

## Goals / Non-Goals

**Goals:**

- 用户能在 Web UI / CLI / TUI 看到可复制的标识。
- 日志和 trace 能用该标识关联一次运行。
- benchmark artifact 能记录该标识。

**Non-Goals:**

- 不实现分布式 tracing 系统。
- 不改变 benchmark run_id / task_id 的既有含义。
- 不引入数据库。

## Decisions

### Decision 1: 区分 session id、run id 和 correlation id

Web 长会话保留 session id；CLI 单次运行可以生成 run id；底层事件和日志使用 correlation id 关联。

### Decision 2: 标识先用于排查，不作为权限边界

这些 id 不承担鉴权或安全边界职责，只用于可观察性。

## Risks / Trade-offs

- [Risk] id 术语混乱。Mitigation: 在 CONTEXT 或规格中明确 session/run/correlation 的边界。
- [Risk] 日志泄漏过多上下文。Mitigation: 只记录随机 id，不记录敏感 prompt。

## Testing Strategy

- Web session 测试确认 session_created 和页面展示 id。
- CLI 测试确认输出 run id。
- Trace / benchmark 测试确认 artifact 包含 correlation id。
- benchmark smoke 覆盖 artifact 写入链路。
