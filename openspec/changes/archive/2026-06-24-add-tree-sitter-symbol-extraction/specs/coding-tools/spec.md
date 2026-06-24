## ADDED Requirements

### Requirement: 代码理解工具返回多语言符号

repo map 和 symbol 查询工具 SHALL 在 tree-sitter extractor 可用时返回多语言结构化符号。

#### Scenario: 查询多语言符号

- **GIVEN** workspace 包含 Python 和 TypeScript 符号
- **WHEN** 调用 symbol 查询工具
- **THEN** 工具 SHALL 返回匹配的多语言符号及其文件位置
- **AND** SHALL 保持只读，不修改工作区文件

### Requirement: 工具输出保持第一阶段兼容

新增 tree-sitter 符号 SHALL 复用既有 repo map / symbol search 输出形状，避免破坏 AgentLoop、trace 和 benchmark 消费方。

#### Scenario: 消费 repo map 输出

- **GIVEN** 调用方已经消费第一阶段 repo map 输出
- **WHEN** tree-sitter extractor 增加新语言符号
- **THEN** 输出 SHALL 保持原有字段可用
- **AND** 新增字段 SHALL 是向后兼容扩展
