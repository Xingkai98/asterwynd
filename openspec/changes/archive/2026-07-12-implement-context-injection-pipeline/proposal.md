## Why

当前 Asterwynd 的上下文注入管线有三个问题：

1. **无结构化分层**：`AgentLoop._messages_with_run_context()` 以 ad-hoc 方式拼接多层上下文（memory index → skill index → active skill context → plan mode → plan → todos），每新增一个上下文来源就要修改同一个方法，缺乏统一的优先级、预算分配和截断策略。

2. **无项目指令注入**：没有 ASTER.md（类比 CLAUDE.md / AGENTS.md）的发现和加载机制。agent 在工作目录中无法感知项目专属的指令和约束。

3. **System Prompt 过于通用**：CLI 和 Web 入口使用一句通用助手 prompt（"你是一个有用、诚实的人工智能助手"），缺少 coding agent 专属的约束前置和工具使用约定。

4. **上下文压缩策略单一**：`MemoryManager.compact()` 只有 LLM 摘要一种策略，无 LLM 时直接丢弃中间消息。缺少滑动窗口、优先级丢弃和硬上限保障。

本 change 建立统一的 **ContextBuilder 分层注入管线**，将 System Prompt、ASTER.md、记忆索引、Skill 上下文、Plan/Todo 状态、对话历史纳入 P0-P6 七层优先级模型，并配备多策略上下文压缩。

## What Changes

### ContextBuilder 分层架构（核心）

- 新增 `agent/context/builder.py`：ContextBuilder 类，注册 ContextSource → 优先级排序 → 预算分配 → 渲染
- 新增 `agent/context/protocol.py`：ContextSource 协议（priority / name / budget / critical / render）
- 新增 `agent/context/sources.py`：内置 ContextSource 实现（SystemPrompt / AsterMd / MemoryIndex / Skill / PlanTodo）
- 重构 `AgentLoop._messages_with_run_context()` 委托给 ContextBuilder
- P0-P6 七层优先级模型，P0 永不被截断，层间用 `---` 分隔
- 注入层总预算 20K tokens（`min(20_000, int(context_window * 0.20))`），超出时从低优先级层尾部逐层砍

### System Prompt 优化（P0 层）

- 重写为 coding agent 专用三段式结构：身份 → 约束（NEVER）→ 工具使用约定
- 中文为主（代码/工具名保留英文）
- 从 `pyproject.toml` 自动读取版本信息注入身份段
- CLI（`agent/main.py`）和 Web（`web/session.py`）统一使用同一套 prompt 构建逻辑

### ASTER.md 注入（P1 层）

- 定义 ASTER.md 文件规范（命名、格式、与 ASTER.local.md 的关系）
- 实现加载策略：向上遍历 + 最近匹配优先 + Git 根/home 边界
- 实现 `/init` 命令：非交互，自动检测项目类型 + 导入已有 AGENTS.md/CLAUDE.md
- 同时支持 `/init`（agent 会话内）和 `asterwynd init`（CLI）

### 上下文压缩多策略（P6 层）

- `Summarizer` 抽象协议：P0 实现 `LLMSummarizer` / `TruncationSummarizer`（`ToolOutputCompressor` 留 P1）
- 90% 阈值触发压缩，P6 对话历史压到原大小的 20-30%
- 保留最近 ~20K tokens 用户消息，旧对话轮次 LLM 结构化手交摘要
- 最小间隔 5 轮防抖，摘要采用 user message 角色
- 优先级保留策略：system > tool chain 完整 > 关键决策 > 最近消息 > 历史

## Capabilities

### New Capabilities

- `context-injection`: ContextBuilder 分层注入管线，P0-P6 优先级模型，token 预算管理

### Modified Capabilities

- `agent-runtime`: AgentLoop 上下文组装重构为委托 ContextBuilder
- `memory-context`: 新增上下文压缩多策略（Summarizer 协议），关键决策检测

## Impact

- 影响代码：
  - `agent/context/builder.py`（新增）
  - `agent/context/protocol.py`（新增）
  - `agent/context/sources.py`（新增）
  - `agent/context/summarizer.py`（新增，压缩策略）
  - `agent/loop.py`（重构 `_messages_with_run_context`，接入 ContextBuilder）
  - `agent/main.py`（CLI system prompt 统一）
  - `web/session.py`（Web system prompt 统一）
  - `agent/tools/builtin/init.py`（新增，`/init` 命令）
  - `agent/memory/manager.py`（`compact()` 委托给 Summarizer）
- 影响测试：
  - `tests/agent/context/test_builder.py`
  - `tests/agent/context/test_sources.py`
  - `tests/agent/context/test_summarizer.py`
  - `tests/agent/test_loop.py`（重构回归）
  - `tests/agent/tools/test_init.py`
- 不影响：LLM provider 协议、MCP 集成、SubAgent 管理、工具注册表、benchmark runner

## Change Type

- primary: feature
- secondary: refactor
