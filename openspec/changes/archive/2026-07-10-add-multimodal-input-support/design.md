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
    file_path: str | None = None  # 本地文件路径，用于 compact/trace 引用

class ImageUrl:
    url: str         # base64 data URL 或 HTTP URL
    detail: str | None = None  # "auto" | "low" | "high" (OpenAI)
```

`Message.content` 类型变为 `str | list[ContentBlock]`。

**向后兼容规则**：
- 如果 `isinstance(content, str)` → 纯文本路径，所有现有代码不受影响。
- 如果 `isinstance(content, list)` → 多模态路径。
- 序列化时：`str` → 保持原样（向后兼容）；`list` → `[{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {...}, "file_path": "..."}]`.

### 2. Read 工具改动

`Read` 工具执行流程：

1. 检测文件扩展名：`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` → 图片路径。
2. 读取文件字节，base64 编码，获取图片尺寸。
3. 返回 `[TextBlock("[image: screenshot.png, 1024x768]"), ImageBlock(url="data:image/png;base64,...", file_path="/path/to/file.png")]`。
4. 非图片文件保持现有文本返回行为（返回 `str`）。

`Tool.execute()` 签名改为 `async def execute(self, **kwargs) -> str | list[ContentBlock]`。AgentLoop 直接将返回值塞进 `Message.content`，无需 ToolResult 中间层。

用户上传/粘贴的图片写入 `.asterwynd/uploads/sha256_{hash}.{ext}`，获得 `file_path`。Web UI 负责在消息进入 AgentLoop 前完成持久化。

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

Adapter 的 `_build_payload()` / `_message_to_dict()` 方法需要：
1. 检查 message 的 content 类型
2. 如果是 `str` → 现有路径
3. 如果是 `list[ContentBlock]` → 转换为 provider 专有的多模态格式
4. 非视觉模型（前缀不匹配视觉名单）→ 先发送带图消息，API 400 后降级重试（图片 block 替换为 `[image: {file_path}]`）

**OpenAI adapter 特殊处理**：OpenAI Chat Completions 的 tool 消息 content 只能是 string。adapter 在构建消息时扫描 tool 消息中的 ImageBlock，剥离文本留在 tool 消息，图片收集后注入一个合成 user 消息承载：

```
原始: tool(content=[TextBlock("..."), ImageBlock(...)])
OpenAI: tool(content="...") + user(content=[ImageBlock(...)])
```

多个连续 tool 消息的图片批量合并到一个合成 user 消息中。Anthropic adapter 无需此处理——其 tool_result 原生支持 content block 数组。

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
| Message 数据模型 | content 类型扩展为 `str \| list[ContentBlock]`，新增 ContentBlock/TextBlock/ImageBlock/ImageUrl |
| Tool.execute() 签名 | 返回值扩展为 `str \| list[ContentBlock]` |
| Tool / ToolRegistry / hooks / retry | 返回值类型从 `str` 扩展，错误处理和日志适配 |
| tool_result_display | 多模态结果展示摘要需提取纯文本 |
| Read 工具 | 新增图片识别、base64 编码、尺寸检测、file_path 填充 |
| `.asterwynd/uploads/` | 新增上传图片持久化目录，sha256 hash 命名 |
| OpenAI adapter | content list → OpenAI 多模态格式 + tool 消息图片注入合成 user 消息 |
| Anthropic adapter | content list → Anthropic 多模态格式（含 image_url → image source 映射） |
| 非视觉模型降级 | 前缀匹配 + API 报错后重试，两个 adapter 各一份 |
| MemoryManager | compact 时图片降级为文本占位，recent window 保留，token 固定估算 |
| TraceRecorder | 图片 base64 替换为引用 |
| Subagent | 图片原样传递，inspect_transcript 提取纯文本 |
| 审批链路 | 审批请求中图片降级为文件名引用 |
| Web UI | 新增图片粘贴/拖拽上传 + 写入 .asterwynd/uploads/ |
| Benchmark | 不影响（benchmark 任务不涉及图片） |


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

2026-07-10 执行 `grill-with-docs`，结论如下：

### 1. 架构路线：纯 Message 扩展（不使用 ToolResult 中间层）

**决定**：不引入 `ToolResult` 类。`Tool.execute()` 签名改为 `-> str | list[ContentBlock]`，AgentLoop 直接把返回值塞进 `Message.content`。LLM adapter 统一处理 `Message.content` 的两种类型，不需要理解 ToolResult 语义。

**理由**：Anthropic API 原生支持 `tool_result.content` 为 `string | array<ContentBlock>` —— 对 LLM 而言 tool_result 就是 message。新增中间抽象层会增加全链路的认知负担，且当前代码里 `execute()` 返回 `str` 没有 ToolResult 可以顺势扩展。

**影响**：不需要创建 `ToolResult` 类。`ContentBlock`、`TextBlock`、`ImageBlock`、`ImageUrl` 四个新类型即可。

### 2. OpenAI tool 消息不支持图片：adapter 层注入合成 user 消息

**决定**：OpenAI Chat Completions 的 tool 消息 content 只能是 string。OpenAI adapter 在构建消息时扫描 tool 消息中的 ImageBlock，剥离文本留在 tool 消息里，图片收集后注入一个合成 user 消息承载。

**格式示例**：
```
原始: tool(content=[TextBlock("..."), ImageBlock(...)])
OpenAI: tool(content="...") + user(content=[ImageBlock(...)])
```

**理由**：LiteLLM、LangChain、Vercel AI SDK 均采用此模式。OpenAI Responses API 虽然原生支持，但本文不做 API 迁移。

### 3. 所有图片统一有 file_path

**决定**：`ImageBlock` 新增 `file_path: str | None` 字段。Read 工具读本地文件时填充原始路径。用户上传/粘贴的图片写入 `.asterwynd/uploads/sha256_{hash}.{ext}`，同样获得 file_path。

**理由**：参考 Claude Code 做法——所有图片都有路径。compact 时统一替换为 `[image: {file_path}, {尺寸}]`，agent 需要时可 Read 回来。去重用 content hash。不自动清理（resume 需要）。

### 4. MemoryManager compact 图片处理

**决定**：compact 时 middle 消息中的 ImageBlock 统一替换为 `"[image: {file_path}, {尺寸}]"` 文本引用。recent window 内图片完整保留。`_count_tokens()` 对 ImageBlock 按固定 1000 token/张估算。摘要 LLM 收到的是文本引用，不传 base64。

### 5. 非视觉模型降级：前缀匹配 + API 裁决

**决定**：维护视觉模型前缀列表 `("gpt-4o", "gpt-4.1", "gpt-5", "claude-", "gemini-")`。前缀匹配判支持视觉；匹配不上 → 发送带图消息 → API 报错后降级重试（文本占位）。

**理由**：业界 A+B 混合模式（LiteLLM、LangChain）。视觉模型名规律性强，维护成本极低。

### 6. TraceRecorder / Subagent / 审批链路

- **TraceRecorder**：`record_tool_result()` 中 ImageBlock 替换为 `[image: {file_path}]`，trace 文件不存完整 base64。
- **Subagent**：同进程 Message 对象直接传递，图片原样。`inspect_transcript` 摘要抽取纯文本。
- **审批链路**：`redacted_args` 中 ImageBlock 替换为 `[image: {file_path}]`，不展示 base64。

### 7. 序列化/反序列化

`ContentBlock` 序列化规则：
- `str` content 保持原样（向后兼容）
- `TextBlock` → `{"type": "text", "text": "..."}`
- `ImageBlock` → `{"type": "image_url", "image_url": {"url": "data:...", "detail": "auto"}, "file_path": "/path/to/file"}`
