## ADDED Requirements

### Requirement: Web UI 折叠展示思维链

Web UI SHALL 在 assistant 消息**含 reasoning 时**提供思维链的折叠展示区，且该区 SHALL 满足：**默认关闭**、**单击展开**、**与正文分离**、**跨 provider 统一样式**。

具体地：

- **默认关闭**：初次渲染时该区处于折叠态，正文 SHALL NOT 被思维链挤占。
- **单击展开**：用户单击标题行切换展开/折叠；展开后可见思维链文本。
- **与正文分离**：思维链 SHALL NOT 混入 assistant 的 Markdown 正文。
- **跨 provider 统一**：形态 SHALL NOT 按 provider 分叉（Anthropic / OpenAI 兼容端点呈现同一交互）。
- **无则不渲染**：assistant 消息不含 reasoning 时 SHALL NOT 渲染该区。

依据（issue #256）：思维链 token 已计入 output token（用户已付费）但当前完全不展示；用户拍板展示形态为「通用样式、默认关闭、单击展开」。

#### Scenario: 含 reasoning 的 assistant 消息默认折叠

- **GIVEN** assistant 消息含 reasoning 内容
- **WHEN** Web UI 渲染该消息
- **THEN** UI SHALL 渲染思维链折叠区
- **AND** 该区初始状态 SHALL 为折叠（正文不被思维链占据）
- **AND** 思维链文本 SHALL NOT 出现在 assistant 的 Markdown 正文里

#### Scenario: 单击标题行切换展开

- **GIVEN** 思维链折叠区已渲染且处于折叠态
- **WHEN** 用户单击该区标题行
- **THEN** 该区 SHALL 切换为展开态并显示思维链文本
- **AND** 再次单击 SHALL 切换回折叠态

#### Scenario: 无 reasoning 的消息不渲染该区

- **GIVEN** assistant 消息不含 reasoning 内容
- **WHEN** Web UI 渲染该消息
- **THEN** UI SHALL NOT 渲染思维链折叠区
- **AND** 该消息的展示 SHALL 与未引入本能力时一致

### Requirement: Web UI 流式消费思维链增量

Web UI SHALL 通过 WebSocket 消费思维链的流式增量事件，并在**已展开**的折叠区内实时追加；未展开时 SHALL 静默累积，展开后可看到完整内容。

- 思维链增量 SHALL NOT 混入 assistant 正文的增量渲染。
- 该区 SHALL 对 Anthropic 与 OpenAI 兼容端点的增量使用同一消费路径（跨 provider 统一）。

依据（issue #256）：思维链在生成过程中即应可见（展开态），而非等响应结束才出现；且不能污染正文渲染。

#### Scenario: 展开态下实时追加

- **GIVEN** 思维链折叠区已展开
- **WHEN** 前端收到思维链增量事件
- **THEN** 该区 SHALL 实时追加文本

#### Scenario: 折叠态下静默累积

- **GIVEN** 思维链折叠区处于折叠态且已收到增量
- **WHEN** 用户展开该区
- **THEN** 该区 SHALL 显示此前累积的完整思维链文本

#### Scenario: 思维链增量不污染正文

- **GIVEN** 前端同时接收思维链增量与 assistant 正文增量
- **WHEN** 前端渲染两者
- **THEN** 思维链文本 SHALL 只出现在折叠区内
- **AND** assistant Markdown 正文 SHALL 只包含可见回复内容
