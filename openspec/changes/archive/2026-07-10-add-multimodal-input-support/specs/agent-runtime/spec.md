## MODIFIED Requirements

### Requirement: 多模态 Message 内容

Message 的 `content` 字段 SHALL 支持 `str`（纯文本）和 `list[ContentBlock]`（多模态）两种类型。`ContentBlock` SHALL 支持 `text` 和 `image_url` 两种类型。`ImageBlock` SHALL 包含 `file_path` 字段用于 compact/trace 引用。`str` 类型 SHALL 保持完全向后兼容（序列化后仍为字符串）。

#### Scenario: 纯文本内容不变

- **GIVEN** Message 的 content 为 `str` 类型
- **WHEN** 任意现有代码路径处理该 Message
- **THEN** 行为 SHALL 与改动前完全一致

#### Scenario: 多模态 content 序列化

- **GIVEN** Message 的 content 为 `[TextBlock("解读这张图"), ImageBlock(url="data:image/png;base64,...", file_path="/path/to/file.png")]`
- **WHEN** 序列化为 JSON
- **THEN** content SHALL 序列化为 content blocks 数组
- **AND** TextBlock 序列化为 `{"type": "text", "text": "..."}`
- **AND** ImageBlock 序列化为 `{"type": "image_url", "image_url": {"url": "data:...", "detail": "auto"}, "file_path": "/path/to/file"}`
- **AND** deserialize 后 SHALL 还原为相同的 content blocks 数组

### Requirement: 工具多模态返回值

`Tool.execute()` SHALL 返回 `str | list[ContentBlock]`。当工具返回了图片内容时，返回值 SHALL 为包含 ImageBlock 的列表。AgentLoop 在构建消息时 SHALL 直接将返回值赋给 `Message.content`。

#### Scenario: Read 工具读取图片

- **GIVEN** Read 工具读取了一个 PNG 文件
- **WHEN** 工具执行完成
- **THEN** `execute()` 返回值 SHALL 为 `[TextBlock, ImageBlock]`
- **AND** AgentLoop 在构建消息时 SHALL 将该列表赋给 `Message.content`

#### Scenario: 普通文本工具结果

- **GIVEN** Read 工具读取了一个 .py 文件
- **WHEN** 工具执行完成
- **THEN** `execute()` 返回值 SHALL 为 `str` 类型
- **AND** AgentLoop 在构建消息时 SHALL 照常使用该字符串
