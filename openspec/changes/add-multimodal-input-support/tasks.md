## 1. 规格

- [ ] 1.1 更新 `agent-runtime` spec delta：定义多模态 Message content 协议。
- [ ] 1.2 更新 `coding-tools` spec delta：定义 Read 工具的图片处理行为。
- [ ] 1.3 开发前使用 `grill-with-docs` 审视 `design.md`。
- [ ] 1.4 维护 `## Impact Analysis`。
- [ ] 1.5 维护 `## Reference Implementation Research`。

- [ ] 1.7 同步 spec delta 到 `openspec/specs/<capability>/spec.md`（当前规格）。

## 2. 测试

- [ ] 2.1 Message 序列化测试：纯文本 content 序列化/反序列化不变。
- [ ] 2.2 Message 序列化测试：多模态 content blocks 序列化/反序列化正确。
- [ ] 2.3 Read 工具测试：读取 PNG/JPG 返回 ImageBlock。
- [ ] 2.4 Read 工具测试：读取 .py 文件仍返回 TextBlock。
- [ ] 2.5 Read 工具测试：超大图片（>20MB）返回错误。
- [ ] 2.6 OpenAI adapter 测试：content list → OpenAI 多模态请求格式。
- [ ] 2.7 Anthropic adapter 测试：content list → Anthropic 多模态请求格式。
- [ ] 2.8 非视觉模型降级测试：图片转换为占位文本。
- [ ] 2.9 MemoryManager compact 测试：图片 content 降级为文本占位。
- [ ] 2.10 TraceRecorder 测试：trace 中图片 base64 被替换为引用。

## 3. 实现

- [ ] 3.1 定义 `ContentBlock`、`TextBlock`、`ImageBlock`、`ImageUrl` 数据类（`agent/message.py`）。
- [ ] 3.2 `Message.content` 类型扩展为 `str | list[ContentBlock]`。
- [ ] 3.3 `ToolResult` 新增 `content_blocks: list[ContentBlock] | None`。
- [ ] 3.4 `Read` 工具：图片检测 + base64 编码 + 填充 content_blocks。
- [ ] 3.5 `AgentLoop` ：构建消息时使用 `content_blocks`。
- [ ] 3.6 OpenAI adapter：`_build_messages()` 支持 content list。
- [ ] 3.7 Anthropic adapter：`_build_messages()` 支持 content list + image source 映射。
- [ ] 3.8 MemoryManager：compact 时图片降级。
- [ ] 3.9 TraceRecorder：图片 base64 替换为引用。
- [ ] 3.10 Subagent message passing：图片原样传递。

## 4. 验证

- [ ] 4.1 运行相关单元/集成测试。
- [ ] 4.2 运行全量测试 `uv run pytest -q`。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行 artifact checker。
- [ ] 4.5 手动验证：用支持视觉的模型读取一个测试图片。

- [ ] 4.5 跑通至少一个 benchmark smoke，验证变更不影响 agent 执行正确性。

## 5. PR 收尾

- [ ] 5.1 归档到 `openspec/changes/archive/YYYY-MM-DD-add-multimodal-input-support/`。
- [ ] 5.2 从 backlog 移除。
- [ ] 5.3 确认 Impact Analysis 无残留未知项。
- [ ] 5.4 运行全量校验。
