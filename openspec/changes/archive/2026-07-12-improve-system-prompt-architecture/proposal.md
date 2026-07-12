## Why

当前默认 system prompt 只有非常弱的通用助手描述，无法表达 Asterwynd 的 coding-agent 身份、工具协议、代码修改边界、验证责任和项目技术栈。CLI、Web、角色注册各自拼接 prompt，也容易产生行为漂移。

本 change 将 system prompt 升级为可维护的结构化提示词架构，作为运行时上下文的最高优先级层。

## Change Type

- primary: feature
- secondary: [refactor]

## What Changes

- 定义统一的 coding-agent system prompt 模板，覆盖身份、能力边界、工具调用协议、工作区安全、编辑约束和验证责任。
- 将负面约束和硬性规则前置，降低模型忽略关键约束的概率。
- 将项目技术栈、版本和入口约束以可维护方式注入，避免硬编码散落在 CLI/Web/role registry。
- 对关键行为提供短示例和执行前/结束前自查清单。
- CLI、Web session 和 AgentLoop SHALL 复用同一 prompt 构造路径。

## Capabilities

### Modified Capabilities

- `agent-runtime`: 统一 system prompt 构造和注入语义。
- `cli`: CLI 运行使用统一 system prompt。
- `web-ui`: Web session 使用统一 system prompt。

## Dependencies

- 与 `add-agents-runtime-instruction-injection` 共享高优先级上下文边界。
- 建议在 `add-context-builder-architecture` 之前或同批落地，后者负责把 system prompt 纳入统一排序和预算。

## Impact Analysis

- 影响代码：
  - `agent/main.py` 和 `web/session.py` 不再各自硬编码默认 prompt。
  - `agent/loop.py` 的 system message 构造改为调用统一 prompt builder。
  - `agent/workflow/role_registry.py` 的角色 prompt 与统一基础 prompt 合成。
- 影响测试：
  - CLI/Web 构造 AgentLoop 时的 system prompt 一致性测试。
  - 角色 prompt 合成测试。
  - 关键约束存在性和重复注入回归测试。
- 不影响：
  - 不改变模型 provider API。
  - 不在本 change 中实现 AGENTS.md 解析。
  - 不在 prompt 中硬编码所有长期项目知识。

## Reference Implementation Research

- status: enabled
- reason: system prompt 是 coding agent 行为边界的关键资产，应参考 Cursor、Aider、Claude Code 对约束、示例和编辑协议的组织方式。
- research questions:
  - 成熟 coding agent 如何分离基础身份 prompt、项目规则和角色 prompt？
  - 编辑协议、工具协议和安全约束应放在 prompt 的哪个位置？
  - 哪些内容适合静态模板，哪些应由 ContextBuilder 动态注入？
- findings:
  - `/tmp/research-to-propose.md` 已记录初步调研：Cursor rules 强调约束和示例，Aider 对 edit format 使用示例驱动。
  - 开发前必须补充当前代码基线下的 prompt 拼接路径调研，避免 CLI/Web/role registry 行为不一致。
- design impact:
  - 本 proposal 将 prompt 构造作为独立架构面，而不是简单改写两句硬编码字符串。
