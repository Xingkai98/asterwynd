# code-intelligence 规格

## Purpose

定义 repo map、符号搜索、LSP、诊断、引用、代码索引和 RAG 式代码检索的能力边界。当前仓库已经具备轻量 RepoMap 和 SymbolSearch 工具；LSP、诊断、引用分析、多语言语法级索引和语义检索仍是后续能力。

## Requirements

### Requirement: 提供轻量 repo map 和符号搜索

系统 SHALL 提供只读的 RepoMap 和 SymbolSearch 工具，用于仓库结构概览和 Python 符号名称搜索。系统 SHALL NOT 声称已经实现 LSP 诊断、引用分析、多语言语法级索引或语义代码检索。

#### Scenario: 当前代码定位

- **GIVEN** agent 需要查找代码
- **WHEN** 使用当前工具集
- **THEN** 系统 MAY 使用 Grep、Find、ListFiles、Read、RepoMap 和 SymbolSearch 等工具
- **AND** SHALL NOT 提供 LSP、引用关系或语义检索保证

#### Scenario: 生成 repo map

- **GIVEN** 仓库包含 Python 文件
- **WHEN** 调用 RepoMap
- **THEN** 系统 SHALL 返回目录摘要和 Python 顶层符号摘要
- **AND** SHALL 遵守 WorkspacePolicy 和忽略规则

#### Scenario: 搜索符号

- **GIVEN** 仓库包含 Python 函数或类
- **WHEN** 调用 SymbolSearch 并提供查询字符串
- **THEN** 系统 SHALL 返回匹配符号的名称、类型、文件和行号
- **AND** SHALL 在无匹配时返回可读提示

### Requirement: 未来实现必须服务 Coding Agent 主线

新增 code intelligence 能力 SHALL 服务代码仓库理解、上下文召回和任务相关文件定位，不得把项目转成通用知识库问答。

#### Scenario: 准备实现 repo indexing

- **GIVEN** 需求提出代码索引
- **WHEN** 创建 OpenSpec change
- **THEN** change SHALL 说明对 AgentLoop、工具系统、memory context 和 benchmark 的影响
