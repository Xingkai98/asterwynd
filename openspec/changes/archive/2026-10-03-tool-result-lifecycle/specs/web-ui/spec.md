# web-ui spec delta: 工具结果展开改为按需回读

## MODIFIED Requirements

### Requirement: Chat 视图按 display metadata 展示工具结果

Web Chat SHALL 使用服务端 tool_result 事件中的 display metadata 展示工具结果。长结果 SHALL 默认展示 preview；工具结果 SHALL 作为纯文本展示，不按 Markdown 或 HTML 渲染。

**全文 SHALL NOT 随初始 tool_result 事件无条件下发**：服务端 SHALL 在事件中携带该工具结果的稳定标识（`tool_call_id`）与 preview，SHALL NOT 默认下发完整正文。用户展开某条长结果时，前端 SHALL 按该标识**按需向服务端取回全文**；服务端 SHALL 返回该工具结果的最新全文（若其消息已被替换为 preview + ref，则按 ref 从落盘件读回全文）。用户收起时，前端 SHALL 释放已取回的全文缓存。

当按标识无法取回全文（消息已被压缩驱逐、ref 不可解析、或结果不再可用）时，服务端 SHALL 明确表示「全文不可用」，前端 SHALL 如实展示该状态，SHALL NOT 展示错误或空内容冒充全文。

#### Scenario: 工具结果过长

- **GIVEN** tool_result 事件包含 collapsed display metadata 与 `tool_call_id`
- **WHEN** Chat 页面展示工具结果
- **THEN** 页面 SHALL 展示 preview、字符数和行数
- **AND** SHALL NOT 在该事件中携带完整正文

#### Scenario: 用户展开长结果

- **GIVEN** Chat 页面已展示一条长工具结果的 preview
- **WHEN** 用户展开该结果
- **THEN** 前端 SHALL 按该结果的标识向服务端取回全文
- **AND** 页面 SHALL 展示取回的完整结果
- **AND** 用户收起后前端 SHALL 释放该全文缓存

#### Scenario: 展开时全文不可用

- **GIVEN** 一条长工具结果的消息已被压缩驱逐或其 ref 不可解析
- **WHEN** 用户展开该结果
- **THEN** 服务端 SHALL 明确返回「全文不可用」
- **AND** 前端 SHALL 如实展示该状态

#### Scenario: 工具结果包含 HTML

- **GIVEN** 工具结果包含 HTML 字符串
- **WHEN** Chat 页面展示工具结果（preview 或取回的全文）
- **THEN** 页面 SHALL 以纯文本展示该字符串
- **AND** SHALL NOT 执行或解析为 HTML
