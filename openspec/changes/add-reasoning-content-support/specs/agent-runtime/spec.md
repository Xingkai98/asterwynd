## ADDED Requirements

### Requirement: reasoning 内容的采集、持久化与回传

Agent runtime SHALL 从 provider 响应中采集思维链（reasoning / thinking）内容，按 provider 的原生形态保存，并在后续请求中按该 provider 的规则回传。

具体地：

- runtime SHALL 把 reasoning 表达为**结构化的段**，每段含**可展示文本**与**可选的 opaque 回传载荷**（如 Anthropic 的 `signature`）。
- opaque 载荷 SHALL 在「采集 → 持久化 → 回放」全链路**逐字节不变**：SHALL NOT 解析、SHALL NOT 改写、SHALL NOT 重排。
- 采集 SHALL 覆盖 Anthropic Messages 的 `thinking` block（流式经 `thinking_delta` + `signature_delta`）与 OpenAI 兼容端点的 `reasoning_content`。
- 回传 SHALL 按 provider 规则：Anthropic 系 SHALL 在 assistant 消息中带回 thinking block（含 opaque 载荷）；OpenAI 兼容路径 SHALL 回传 `reasoning_content`。
- provider 未返回 reasoning 时，runtime SHALL NOT 产生该字段，且全链路行为 SHALL NOT 改变。

依据（issue #256）：DeepSeek V4 系列默认开启 thinking，两条协议（Anthropic / OpenAI 兼容）都要求回传、不回传报 400。官方还要求 Anthropic 的 thinking block 顺序不可重排、`signature` 不可解析。

#### Scenario: 采集 Anthropic 流式 thinking

- **GIVEN** provider 的流式响应含 `thinking` block（`thinking_delta` 增量文本 + `signature_delta` 签名）
- **WHEN** runtime 消费该响应
- **THEN** runtime SHALL 产出一个 reasoning 段，其可展示文本为累积的 thinking 文本、opaque 载荷为该签名
- **AND** 该段 SHALL 随 assistant 消息持久化

#### Scenario: 回传 Anthropic thinking block

- **GIVEN** 历史中存在带 reasoning 的 assistant 消息
- **WHEN** runtime 构造下一次 Anthropic 请求
- **THEN** 该 assistant 消息的 content SHALL 包含 thinking block
- **AND** 该 block 的 opaque 载荷 SHALL 与采集时逐字节一致
- **AND** thinking block 的相对顺序 SHALL 与原始响应一致

#### Scenario: 采集与回传 OpenAI 兼容 reasoning_content

- **GIVEN** provider 的响应含 `reasoning_content`
- **WHEN** runtime 消费该响应并构造下一次请求
- **THEN** runtime SHALL 采集该内容为 reasoning 段的可展示文本
- **AND** 后续请求的 assistant 消息 SHALL 回传 `reasoning_content`

#### Scenario: 无 reasoning 的 provider 行为不变

- **GIVEN** provider 的响应不含任何 reasoning 字段
- **WHEN** runtime 消费该响应并构造下一次请求
- **THEN** runtime SHALL NOT 产生 reasoning 段
- **AND** 请求体与响应处理 SHALL 与未引入本能力时逐字段一致

### Requirement: reasoning 的流式事件与正文隔离

Agent runtime SHALL 为思维链的流式增量发布**独立于** `assistant_delta` 的事件，使消费方能区分「思考过程」与「可见回复」。

- 思维链增量 SHALL NOT 混入 `assistant_delta`（后者语义是 assistant 可见回复的增量，消费方会写入正文）。
- 无 reasoning 时 runtime SHALL NOT 发布该事件。

依据（issue #256）：若把 thinking 混入 `assistant_delta`，Web 端会把它渲染进 markdown 正文，既污染正文也违背「思维链与正文分离展示」的需求。

#### Scenario: reasoning 增量走独立事件

- **GIVEN** provider 的流式响应开始产出思维链
- **WHEN** runtime 转发该增量
- **THEN** runtime SHALL 发布 reasoning 增量事件，SHALL NOT 发布 `assistant_delta`
- **AND** 随后产出的可见回复 SHALL 仍通过 `assistant_delta` 发布

### Requirement: 上下文压缩对 reasoning 的处理

上下文压缩（compaction）SHALL 保留**最新 assistant 轮**的 reasoning，使下一轮请求能按其 provider 规则回传；更早轮的 reasoning MAY 被丢弃。

依据（issue #256 / 官方规则）：Anthropic 要求多轮 / tool use 时**最新** assistant 轮的 thinking block 必须原样回传，而更早轮可省略（API 自动过滤）；压缩据此获得「旧轮可丢、新轮必留」的自由度。

#### Scenario: 压缩后最新轮 reasoning 仍在

- **GIVEN** 历史中存在多轮带 reasoning 的 assistant 消息
- **WHEN** compaction 重写历史
- **THEN** 压缩后最新 assistant 消息的 reasoning SHALL 仍存在（若压缩前存在）
- **AND** 更早轮的 reasoning MAY 被移除
