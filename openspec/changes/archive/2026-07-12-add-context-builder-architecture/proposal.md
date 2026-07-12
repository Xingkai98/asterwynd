## Why

当前 `AgentLoop._messages_with_run_context()` 直接拼接 memory index、skill index、active skill、plan mode、plan 和 todos。新增上下文来源时必须继续修改同一个方法，优先级、预算和可观测性也缺少统一模型。

本 change 引入统一 ContextBuilder，作为 system prompt、AGENTS.md、记忆、skill、plan/todo 等上下文来源的注册、排序、预算和渲染中枢。

## Change Type

- primary: feature
- secondary: [refactor]

## What Changes

- 新增 `ContextBuilder` 和 `ContextSource` 抽象。
- 上下文来源 SHALL 声明优先级、默认 token 预算、是否可裁剪、渲染方式和 trace metadata。
- ContextBuilder SHALL 按优先级构建最终 message/context，并在总预算不足时裁剪低优先级来源。
- 初始来源包括 system prompt、AGENTS.md Always 段、持久记忆索引、自动召回记忆、AGENTS.md Auto-Attached 段、活跃 skill、plan/todo。
- 构建结果 SHALL 暴露来源清单、token 估算和裁剪原因。

## Capabilities

### Modified Capabilities

- `agent-runtime`: AgentLoop 使用统一上下文构建路径。
- `memory-context`: 记忆索引和召回结果成为 ContextSource。
- `skills`: skill index 和 active skill context 成为 ContextSource。
- `planning`: plan/todo 状态成为低优先级运行上下文来源。

## Dependencies

- 承接 `add-agents-runtime-instruction-injection` 和 `improve-system-prompt-architecture` 的输出。
- 后续 `add-automatic-memory-recall` 依赖本 change 提供可控注入位置。
- 后续 `add-context-compression-strategies` 复用 token 预算和裁剪信息。

## Impact Analysis

- 影响代码：
  - 新增 `agent/context/`。
  - `agent/loop.py` 将 ad-hoc 拼接迁移为 ContextBuilder。
  - `agent/memory/persistent.py`、skill runtime、planning state 暴露 ContextSource adapter。
- 影响测试：
  - 来源排序和预算分配单元测试。
  - AgentLoop message 构造回归测试。
  - 记忆、skill、plan 同时存在时的集成测试。
- 不影响：
  - 不改变各来源的业务语义。
  - 不在本 change 中实现向量召回或智能记忆更新。
  - 不把 ContextBuilder 设计成独立 agent loop。

## Reference Implementation Research

- status: enabled
- reason: 上下文构建是 coding agent 核心路径，应参考 Claude Code、Aider、SWE-agent 等项目对分层上下文和预算控制的取舍。
- research questions:
  - 成熟工具如何组织 system、repo rules、memory、repo map、tool results 和 conversation history？
  - token 预算不足时哪些来源优先保留？
  - 构建结果如何记录到 trace，便于调试上下文污染和缺失？
- findings:
  - `/tmp/research-to-propose.md` 已记录初步调研：Claude Code 使用分层注入，Aider 强调结构化 repo map 和摘要优先。
  - 开发前必须补实本仓库当前 `_messages_with_run_context()` 的迁移清单和参考实现发现。
- design impact:
  - 本 proposal 把 ContextBuilder 定位为多个后续 change 的基础设施，要求清晰的来源接口和可观测性。
