# code-intelligence 规格

## Purpose

定义 LSP、符号、诊断、引用、代码索引和 RAG 式代码检索的未来能力边界。当前仓库只有基础文件搜索工具，没有独立 code intelligence 子系统。

## Requirements

### Requirement: code intelligence 当前为预留能力域

系统 SHALL NOT 声称已经实现 LSP 诊断、符号索引、引用分析、语义代码检索或 repo indexing。

#### Scenario: 当前代码定位

- **GIVEN** agent 需要查找代码
- **WHEN** 使用当前工具集
- **THEN** 系统 MAY 使用 Grep、Find、ListFiles、Read 等文本级工具
- **AND** SHALL NOT 提供 LSP 或索引级保证

### Requirement: 未来实现必须服务 Coding Agent 主线

新增 code intelligence 能力 SHALL 服务代码仓库理解、上下文召回和任务相关文件定位，不得把项目转成通用知识库问答。

#### Scenario: 准备实现 repo indexing

- **GIVEN** 需求提出代码索引
- **WHEN** 创建 OpenSpec change
- **THEN** change SHALL 说明对 AgentLoop、工具系统、memory context 和 benchmark 的影响

