## Context

默认 prompt 目前分散在 CLI、Web session、AgentLoop 和 role registry 附近，且内容过于通用。Asterwynd 需要把 coding-agent 身份、工具协议、编辑约束和验证责任变成统一、可测试、可演进的提示词资产。

## Goals / Non-Goals

**Goals:**

- 提供统一 system prompt builder。
- 明确 coding agent 身份、能力边界、工具使用、工作区安全、编辑规则和验证责任。
- CLI、Web 和角色 agent 使用同一基础 prompt。
- 支持将技术栈版本和运行模式作为结构化变量注入。
- 保留角色 prompt 的增量扩展能力。

**Non-Goals:**

- 不在 prompt 中复制所有项目文档。
- 不改变 LLM provider 协议。
- 不用 prompt 取代工具权限和 workspace safety 代码约束。
- 不在本 change 中实现 AGENTS.md 加载。

## Decisions

### Decision 1: Prompt builder 输出结构化段落

Prompt builder 以命名段落组织硬性规则、身份、工具协议、编辑约束、验证清单和动态变量，而不是拼接散乱字符串。

理由：便于测试关键段落是否存在，也便于 ContextBuilder 后续作为最高优先级来源处理。

### Decision 2: 基础 prompt 与角色 prompt 合成

角色注册只提供角色差异，基础 coding-agent 约束始终由统一 builder 注入。

理由：保证 subagent 或 role agent 不会绕开核心约束。

### Decision 3: Prompt 只描述行为边界，不承载动态事实库

技术栈版本可以作为短变量注入，但长期项目知识、AGENTS.md、memory、skills 由对应 ContextSource 注入。

理由：避免 system prompt 膨胀和事实过期。

## Pre-Implementation Review

- Questions resolved:
  - propose 阶段确认首要目标是统一 prompt 构造路径，而非单点文案优化。
  - 约束、示例和结束清单都属于目标范围。
- Options considered:
  - 只替换现有两句中文 prompt。
  - 为 CLI/Web 分别维护 prompt。
  - 引入统一 prompt builder。
- Rejected alternatives:
  - 单点替换无法解决入口漂移。
  - 分入口维护会重复制造不一致。
- Final confirmations:
  - 开发前必须确认 prompt 段落顺序、动态变量来源、角色合成方式和测试断言粒度。
- Remaining risks:
  - Prompt 过长会挤占任务上下文；开发时应保持基础 prompt 精炼，并把动态内容交给 ContextBuilder。

## Risks / Trade-offs

- [Risk] 约束写进 prompt 后被误认为替代代码安全检查。Mitigation: 文档明确 prompt 是行为引导，权限仍由 runtime enforce。
- [Risk] 多入口迁移遗漏。Mitigation: 测试覆盖 CLI、Web 和 role registry。
- [Risk] 动态版本信息过期。Mitigation: 从配置或单一常量来源生成。

## Testing Strategy

- 单元测试覆盖 prompt builder 段落顺序和关键约束存在性。
- 集成测试覆盖 CLI/Web 构造 AgentLoop 时使用同一基础 prompt。
- 角色 prompt 测试覆盖基础约束 + 角色差异的合成。
- 快照或黄金文本测试只覆盖稳定片段，避免脆弱全文断言。
