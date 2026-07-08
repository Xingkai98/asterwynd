## Context

Message 协议的 core 数据类型是 `content: str`，所有上下游——LLM adapter、memory compaction、trace、subagent 传递——都假设纯文本。支持图片输入需要把这个假设升级为"content 可以是文本或 image_url blocks 的列表"，同时保持对纯文本路径的完全兼容。

这项改造触及整个系统的消息传递链，是 6 个 change 中改动面最大的一个。

## Decisions

### 1. Content 协议设计

```python
from typing import Literal

type ContentBlock = TextBlock | ImageBlock

class TextBlock:
    type: Literal["text"] = "text"
    text: str

class ImageBlock:
    type: Literal["image_url"] = "image_url"
    image_url: ImageUrl

class ImageUrl:
    url: str         # base64 data URL 或 HTTP URL
    detail: str | None = None  # "auto" | "low" | "high" (OpenAI)
```

`Message.content` 类型变为 `str | list[ContentBlock]`。

**向后兼容规则**：
- 如果 `isinstance(content, str)` → 纯文本路径，所有现有代码不受影响。
- 如果 `isinstance(content, list)` → 多模态路径。
- 序列化时：`str` → `{"type": "text", "content": "..."}`；`list` → `[{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {...}}]`.

### 2. Read 工具改动

`Read` 工具执行流程：

1. 检测文件扩展名：`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` → 图片路径。
2. 读取文件字节，base64 编码。
3. 返回 `[ImageBlock(url="data:image/png;base64,...")]` 而非文本字符串。
4. 非图片文件保持现有文本返回行为。

`Read` 工具的 `execute() -> str` 签名不变——图片的 content blocks 在 AgentLoop 层面转换为多模态消息格式，而非在工具返回值中直接编码。

实际上：工具 `execute()` 仍然返回 `str`（对图片返回描述性文本如 `[image: screenshot.png, 1024x768]`），但 AgentLoop 在构建消息时检测到上一轮 Read 返回了图片标记，并使用对应的 content blocks 构建多模态消息。

**替代方案**：在 `ToolResult` 中新增 `content_blocks: list[ContentBlock] | None` 字段，允许工具返回结构化的多模态内容。AgentLoop 在构建消息时使用 `content_blocks` 替代 `output` 字符串。这个方案改动更小，不需要 AgentLoop 去"猜测"哪些工具返回了图片。

**采用替代方案**：`ToolResult` 新增 `content_blocks: list[ContentBlock] | None = None`。图片读取时 Read 工具填充 `content_blocks`，AgentLoop 使用它构建多模态消息。

### 3. LLM Provider Adapter 改动

**OpenAI API 格式**：
```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "这个截图显示什么错误？"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
  ]
}
```

**Anthropic API 格式**：
```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "这个截图显示什么错误？"},
    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}}
  ]
}
```

Adapter 的 `_build_messages()` 方法需要：
1. 检查 message 的 content 类型
2. 如果是 `str` → 现有路径
3. 如果是 `list[ContentBlock]` → 转换为 provider 专有的多模态格式
4. 非视觉模型（如非 `gpt-4o`、非 Claude 3+）→ 对图片 block 降级为占位文本 `[image: <描述>]`

### 4. 消息序列化影响

所有序列化/反序列化 Message 的地方都需要处理 `content: str | list[ContentBlock]`：

- **MemoryManager compact**：compact 时如遇到图片 content blocks，降级为文本占位符再传给 LLM 摘要（摘要 LLM 可能不支持视觉）。
- **TraceRecorder**：图片 base64 数据不完整写入 trace（太大），替换为 `[image: <file_name>]` 引用。
- **Subagent message passing**：图片 content blocks 原样传递（子 agent 使用相同的 LLM provider，支持多模态）。

### 5. 图片大小限制

- 单张图片最大 20MB（对齐 Claude API 限制）。
- base64 编码后完整传递（不做压缩），由 LLM provider 侧处理尺寸优化。
- 如果 Read 工具检测到超大图片，返回错误提示而不是静默截断。

## Goals / Non-Goals

- 不支持视频/音频输入。
- 不支持图片生成或编辑。
- 不支持 Web UI 中的图片粘贴/拖拽上传（后续 change）。
- 不支持 prompt caching 对图片内容的优化（后续优化）。

## Reference Implementation Research

- status: enabled
- reason: 与主流 coding agent 对比后识别的基础能力差距，需调研行业参考实现以指导设计方案。

- research questions:

1. Claude Code 的 Read 工具如何处理图片？
2. Anthropic API 和 OpenAI API 的多模态 content 格式差异？
3. 非视觉模型的降级策略？

- findings:

- Claude Code 的 Read 工具检测图片文件扩展名，返回 `image_url` content block。Claude API 支持 `image` content block 类型（使用 `source.type: base64` + `media_type` + `data`）。
- OpenAI API 使用 `image_url` content block，支持 `url`（HTTP 或 data URL）和可选 `detail` 参数（auto/low/high）。Anthropic API 使用 `image` type + `source` 对象。
- 两个 API 的多模态格式差异较大，需要在 adapter 层做 provider-specific 转换。
- 非视觉模型（如 `gpt-4`、`claude-3-haiku` 早期版本）不支持图片输入，需要降级处理。

- design impact:

- Message 协议层定义中立的 `ContentBlock` 格式（`text` + `image_url`），各 adapter 负责转换为 provider 格式。
- Anthropic adapter 需要 `image_url` → `image` + `source` 的格式映射。
- 降级策略使用占位文本而非直接报错，让 agent 至少知道"这里有一张图片"。

## Impact Analysis

| 影响面 | 状态 |
|--------|------|
| Message 数据模型 | content 类型扩展，向后兼容 |
| Read 工具 | 新增图片识别路径 |
| OpenAI adapter | 新增 content list → OpenAI 多模态格式转换 |
| Anthropic adapter | 新增 content list → Anthropic 多模态格式转换 |
| MemoryManager | compact 时图片降级为文本占位 |
| TraceRecorder | 图片 base64 替换为引用 |
| Subagent | 图片原样传递 |
| Web UI | 前端不需要改动（图片由 model 理解，UI 只展示文本） |
| Benchmark | 不影响（benchmark 任务不涉及图片） |
| 审批链路 | 审批请求中图片降级为文件名引用 |


## Risks / Trade-offs

- [Risk] Message.content 类型从 str 扩展到 union type 影响所有消息处理路径。Mitigation: 充分测试向后兼容性，所有现有测试必须无改动通过。
- [Risk] 图片 base64 数据可能使 trace 文件膨胀。Mitigation: trace 中替换为引用，不存储完整 base64。
- [Risk] 非视觉模型降级的占位文本可能让 agent 困惑。Mitigation: 占位文本明确说明"此处是一张图片"，并提示使用支持视觉的模型。

## Testing Strategy

- Message 序列化/反序列化：纯文本不变、多模态 content blocks 正确。
- Read 工具：PNG/JPG 返回 ImageBlock、.py 文件仍返回文本、超大图片报错。
- OpenAI/Anthropic adapter：content list → provider 格式转换正确。
- 非视觉模型降级：图片转占位文本。
- MemoryManager compact：图片降级为文本。
- TraceRecorder：图片 base64 替换为引用。
## Pre-Implementation Review

待 `grill-with-docs` 执行后填写。
