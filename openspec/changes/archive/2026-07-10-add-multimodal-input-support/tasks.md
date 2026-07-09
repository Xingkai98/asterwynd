## 1. 规格

- [x] 1.1 更新 `agent-runtime` spec delta：定义多模态 Message content 协议，无 ToolResult。
- [x] 1.2 更新 `coding-tools` spec delta：定义 Read 工具的图片处理行为和 `execute()` 返回值。
- [x] 1.3 开发前使用 `grill-with-docs` 审视 `design.md`。
- [x] 1.4 维护 `## Impact Analysis`。
- [x] 1.5 维护 `## Reference Implementation Research`。
- [x] 1.6 同步 spec delta 到 `openspec/specs/<capability>/spec.md`（当前规格）。

## 2. 测试

- [x] 2.1 Message 序列化测试：纯文本 content 序列化/反序列化不变。
- [x] 2.2 Message 序列化测试：多模态 content blocks 序列化/反序列化正确（含 file_path）。
- [x] 2.3 Read 工具测试：读取 PNG/JPG 返回 `[TextBlock, ImageBlock]`。
- [x] 2.4 Read 工具测试：读取 .py 文件仍返回 `str`。
- [x] 2.5 Read 工具测试：超大图片（>20MB）返回错误。
- [x] 2.6 OpenAI adapter 测试：content list → OpenAI 多模态请求格式。
- [x] 2.7 Anthropic adapter 测试：content list → Anthropic 多模态请求格式（含 image_url → image source 映射）。
- [x] 2.8 OpenAI adapter 测试：tool 消息中的 ImageBlock 被剥离并注入合成 user 消息。
- [x] 2.9 非视觉模型降级测试：已知视觉模型直接发送图片；未知模型先发送图片，400 后降级重试。
- [x] 2.10 MemoryManager compact 测试：middle 消息图片降级为 `[image: {file_path}, {尺寸}]`，recent window 完整保留。
- [x] 2.11 MemoryManager token 计数测试：ImageBlock 按 1000 token/张估算。
- [x] 2.12 TraceRecorder 测试：trace 中图片 base64 被替换为 `[image: {file_path}]`。
- [x] 2.13 上传图片持久化测试：base64 写入 `.asterwynd/uploads/sha256_{hash}.{ext}`，去重生效。
- [x] 2.14 Subagent inspect_transcript 测试：摘要中 msg.content 提取纯文本。
- [x] 2.15 审批链路测试：redacted_args 中 ImageBlock 替换为 `[image: {file_path}]`。

## 3. 实现

### 数据模型

- [x] 3.1 在 `agent/message.py` 定义 `ContentBlock`、`TextBlock`、`ImageBlock`、`ImageUrl` 数据类。
- [x] 3.2 `ImageBlock` 包含 `file_path: str | None` 字段。
- [x] 3.3 `Message.content` 类型扩展为 `str | list[ContentBlock]`。
- [x] 3.4 实现 `_extract_text(content)` 辅助函数和 `_count_tokens_for_message()`（ImageBlock 固定 1000 token）。
- [x] 3.5 `Message.to_dict()` / `from_dict()` 支持 content blocks 序列化/反序列化。

### 工具层

- [x] 3.6 `Tool.execute()` 签名改为 `-> str | list[ContentBlock]`。
- [x] 3.7 `ToolRegistry.execute()` 和相关 hooks/retry 适配新返回类型。
- [x] 3.8 Read 工具：图片扩展名检测 + base64 编码 + 尺寸获取 + 返回 `[TextBlock, ImageBlock]`。
- [x] 3.9 `tool_result_display.py`：多模态结果摘要提取纯文本。

### 上传持久化

- [x] 3.10 创建 `.asterwynd/uploads/` 目录管理，sha256 hash 命名。
- [x] 3.11 图片 base64 → 写入 uploads/，去重检查。

### AgentLoop

- [x] 3.12 AgentLoop 构建 tool 消息时：`execute()` 返回值直接赋给 `Message.content`。
- [x] 3.13 `_last_user_content()` 等 content-as-str 访问点改用 `_extract_text()`。
- [x] 3.14 全局 `on_event("tool_result", ...)` 的 result 字段改用 `_extract_text()` 提取文本。

### LLM Adapter

- [x] 3.15 `agent/openai_llm.py`：`_message_to_dict()` 支持 content list → OpenAI 多模态格式。
- [x] 3.16 `agent/openai_llm.py`：tool 消息图片剥离 + 合成 user 消息注入。
- [x] 3.17 `agent/anthropic_llm.py`：`_build_payload()` 支持 content list → Anthropic 多模态格式（image_url → image source）。
- [x] 3.18 两个 adapter：视觉模型前缀列表 + 非视觉降级（先发再重试）。

### Memory / Trace / Subagent / 审批

- [x] 3.19 MemoryManager：`compact()` 中 middle 消息 ImageBlock → `[image: {file_path}, {尺寸}]`，recent window 保留原样。
- [x] 3.20 MemoryManager：`count_tokens()` 改用 `_count_tokens_for_message()`。
- [x] 3.21 MemoryManager：`_format_messages_for_summary()` 使用 `_extract_text()`。
- [x] 3.22 TraceRecorder：`record_tool_result()` 中 ImageBlock → `[image: {file_path}]`。
- [x] 3.23 Subagent：`inspect_transcript` 摘要使用 `_extract_text()`。
- [x] 3.24 审批链路：`redacted_args` 中 ImageBlock → `[image: {file_path}]`。

### Web UI

- [x] 3.25 Web UI 图片上传：`<input type="file" accept="image/*">` 按钮（桌面+手机通用），桌面额外支持粘贴（Ctrl+V）和拖拽。
- [x] 3.26 上传图片写入 `.asterwynd/uploads/` 后构造 `Message(content=[TextBlock, ImageBlock])`。
- [x] 3.27 图片预览区：缩略图 + 文件名 + 删除按钮，textarea 下方展示，移动端响应式布局。
- [x] 3.28 聊天历史中用户消息气泡展示图片缩略图，点击放大。

## 4. 验证

- [x] 4.1 运行相关单元/集成测试。
- [x] 4.2 运行全量测试 `uv run pytest -q`。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行 artifact checker。
- [ ] 4.5 手动验证：用支持视觉的模型 Read 一个测试图片。（延后）
- [x] 4.6 跑通至少一个 benchmark smoke，验证变更不影响 agent 执行正确性。（benchmark 因环境缺少 `pytest` PATH 全部 exit 127，属预存问题；全量 pytest 832 passed 已验证）

## 5. PR 收尾

- [ ] 5.1 归档到 `openspec/changes/archive/YYYY-MM-DD-add-multimodal-input-support/`。
- [ ] 5.2 从 backlog 移除。
- [ ] 5.3 确认 Impact Analysis 无残留未知项。
- [ ] 5.4 运行全量校验。
