## ADDED Requirements

### Requirement: Web session 恢复历史的只读配对展示

当 Web 会话从持久化快照恢复、且尚未发起新 run（`session.messages` 为空）时，`session_history` SHALL 基于 `resume_snapshot.messages` 的**副本**调用与 run 起点相同的 tool-call 配对修复后再投影，使悬空 `tool_use` 在首次连接的历史中即显示为明确标记的合成 `tool` 结果。该展示层修复 SHALL 只读：SHALL NOT 修改持久化文件、SHALL NOT 发 `tool_pairing_repaired` 事件、SHALL NOT 改变 `resume_snapshot` 本身；run 起点仍是权威修复点，且合成内容 SHALL 与 run 起点生成的确定性内容一致（不因先展示后落盘而跳变）。

#### Scenario: 重启后首次连接即看到合成结果

- **GIVEN** 会话快照包含悬空 assistant `tool_calls`，Web 重新连接且尚未发新消息
- **WHEN** 服务端发送 `session_history`
- **THEN** 历史中 SHALL 含对应 id 的合成 `tool` 结果（带固定前缀）
- **AND** 磁盘快照与 `resume_snapshot` SHALL NOT 被该投影修改
- **AND** SHALL NOT 因此发出 `tool_pairing_repaired` 事件

### Requirement: Web UI 展示 LLM HTTP 错误详情

当一次 run 因 LLM provider 返回 HTTP 错误而失败，且服务端已保留可读响应体时，Web 错误事件 SHALL 在既有 `message` 之外携带**有界** `detail`（响应体文本）与 `status_code`。前端 SHALL 在基础错误文案之后展示该 `detail`，并使用纯文本渲染（`textContent` 或等价方式），SHALL NOT 将其作为 HTML/Markdown 注入。

- `message` 的既有内容与 `code` 映射 SHALL 保持不变；`detail` / `status_code` 是附加字段，仅在响应体可用时出现；
- `detail` SHALL 有界（超出截断并标记），SHALL NOT 拼接请求 payload 或凭据；
- 非 HTTP 错误、无响应体的 HTTP 错误、既有 `ERROR_MESSAGES` 友好码 SHALL 保持当前事件/展示行为；
- 群聊成员 run 因 HTTP 错误失败时，失败原因 SHALL 进入房间系统日志（经 `TurnOutcome.message`），但该共享日志 SHALL 使用**保守固定摘要**：`HTTP <status>` + **已知错误类型枚举**中的值（如 `invalid_request_error` / `authentication_error` / `permission_error` / `not_found_error` / `request_too_large` / `rate_limit_error` / `api_error` / `overloaded_error` / `billing_error`；不在枚举内写 `unknown`）；SHALL NOT 包含 `error.message`、首行正文、任意 provider 字符串、原始 provider body、请求 payload、system prompt、工具参数或凭据。成员自己的连接仍可收到 bounded 原始 `detail`。

#### Scenario: 普通 Chat 展示 400 响应体

- **GIVEN** 普通 Web 会话的一次 run 收到 LLM provider HTTP 400，响应体可读
- **WHEN** 服务端广播 error 事件
- **THEN** 事件 SHALL 含既有 `message` 与附加 `detail` / `status_code`
- **AND** 前端错误消息 SHALL 以纯文本展示 `message` 后跟 `detail`
- **AND** SHALL NOT 因 `detail` 中的尖括号/HTML 片段执行脚本

#### Scenario: 无响应体或非 HTTP 错误保持不变

- **GIVEN** 一次 run 因非 HTTP 异常失败，或 HTTP 错误没有可读响应体
- **WHEN** 服务端广播 error 事件
- **THEN** 事件 SHALL 与当前形状一致（不新增 `detail` / `status_code`）
- **AND** 前端 SHALL 继续只展示既有 `message` / `ERROR_MESSAGES` 文案

#### Scenario: 群聊成员失败原因可见且不泄漏原始 body

- **GIVEN** 群聊成员的 run 因 LLM provider HTTP 400 失败，且响应体可读
- **WHEN** 编排器记录成员失败
- **THEN** 房间系统日志 SHALL 包含 `HTTP <status>` + 已知错误类型枚举值（未知写 `unknown`）的固定摘要
- **AND** SHALL NOT 包含 `error.message`、首行正文、任意 provider 字符串、原始 provider body、请求 payload、system prompt、工具参数或凭据
- **AND** 既有成员状态、envelope 字段与失败计数语义 SHALL 不变

#### Scenario: 超长响应体截断

- **GIVEN** provider 返回的 HTTP 错误响应体超过展示上限
- **WHEN** 服务端放入 error 事件或群聊失败原因
- **THEN** Web error 事件的 `detail` SHALL 被截断并带明确的截断标记
- **AND** 群聊共享日志的 `error.type` 枚举值 SHALL 属于已知集合（未知写 `unknown`），不需要自由文本截断
- **AND** 事件/日志 SHALL NOT 因无界 body 而失去可读性
