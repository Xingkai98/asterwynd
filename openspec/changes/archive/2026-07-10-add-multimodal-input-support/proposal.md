## Why

当前 Message 协议仅支持文本内容（`role + content: str`），所有 LLM provider adapter 也只处理纯文本。Asterwynd 的 agent 无法理解截图、架构图、UI mockup 等图片输入。

Claude Code 支持通过 `Read` 工具读取图片文件并作为多模态输入传给模型，Copilot、Cursor、Cline 均提供图片理解和粘贴功能。多模态是 coding agent "能看懂 UI 截图定位 bug"的关键基础。

## What Changes

- `Message` 数据模型扩展：`content` 从 `str` 扩展为 `str | list[ContentBlock]`，`ContentBlock` 支持 `text` 和 `image_url` 两种类型。
- `Read` 工具扩展：读取图片文件（PNG/JPG/GIF/WebP）时返回 `[image_url]` content block 而非文本。
- LLM Provider Adapter 改动：
  - OpenAI adapter：支持 `content: list[ContentBlock]` 格式。
  - Anthropic adapter：支持 `content: list[ContentBlock]` 格式（含 `source` 字段映射）。
- 向前兼容：现有 `content: str` 的用法不受影响，仅在涉及图片时使用新格式。
- Message 序列化/反序列化（用于 trace、subagent 传递）支持多模态 content。

不被认为是一个 breaking change——`content: str` 的所有现有路径保持不变。

## Capabilities

### Modified Capabilities

- `agent-runtime`: `Message` 协议扩展为支持多模态 content blocks。
- `coding-tools`: `Read` 工具支持图片文件的识别和 base64 编码返回。

## Impact

- 影响代码：
  - `agent/message.py`
  - `agent/loop.py`（消息序列化/反序列化）
  - `agent/openai_llm.py`
  - `agent/anthropic_llm.py`
  - `agent/tools/builtin/read.py`
  - `agent/memory/manager.py`（compact 中的消息序列化）
  - `agent/trace_recorder.py`（trace 中可能包含图片引用）
  - `agent/subagent/`（父子 agent 消息传递）
- 影响测试：
  - `tests/agent/test_message.py`
  - `tests/agent/llm/test_openai_adapter.py`
  - `tests/agent/llm/test_anthropic_adapter.py`
  - `tests/agent/tools/test_read.py`
  - `tests/agent/test_loop.py`

## Change Type

- primary: feature
- secondary: refactor
