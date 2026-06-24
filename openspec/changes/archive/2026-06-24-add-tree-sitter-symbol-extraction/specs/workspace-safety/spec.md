## ADDED Requirements

### Requirement: tree-sitter 解析不得绕过 workspace read policy

Tree-sitter 符号提取 SHALL 只处理已经由 repo map scanner 和 WorkspacePolicy 允许读取的文件。Tree-sitter extractor SHALL NOT 自行遍历 workspace、读取 denied path 或扩大读取边界。

#### Scenario: denied path 中存在已注册语言文件

- **GIVEN** workspace 中 denied path 下存在 TypeScript 文件
- **WHEN** 生成 repo map 或执行符号查询
- **THEN** 系统 SHALL 跳过该文件
- **AND** SHALL NOT 通过 tree-sitter 读取或返回该文件中的符号
