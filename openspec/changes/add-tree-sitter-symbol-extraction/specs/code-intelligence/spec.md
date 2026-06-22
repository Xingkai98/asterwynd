## ADDED Requirements

### Requirement: 使用 tree-sitter 提取多语言符号

系统 SHALL 在 repo map 基础设施上接入 tree-sitter extractor，为已注册语言提取结构化符号摘要。

#### Scenario: 提取 TypeScript 文件符号

- **GIVEN** workspace 中包含已注册语言的 TypeScript 文件
- **WHEN** code intelligence 扫描该文件
- **THEN** 系统 SHALL 返回该文件中的 class、function 或 export 符号摘要
- **AND** SHALL 标识符号所属语言或 extractor 来源

### Requirement: 未注册语言降级为文件级条目

系统 SHALL 对未注册 tree-sitter grammar 或 query 的语言保留 repo map 文件条目，但不得伪造结构化符号。

#### Scenario: 扫描未注册语言文件

- **GIVEN** workspace 中包含当前未注册语言文件
- **WHEN** 生成 repo map
- **THEN** 系统 SHALL 返回该文件的路径和文件类型
- **AND** SHALL NOT 返回伪造 class、function 或 method 符号

### Requirement: tree-sitter 解析失败可降级

系统 SHALL 在单个文件 tree-sitter 解析失败时降级该文件的结构化摘要，而不是让整个 repo map 失败。

#### Scenario: 单文件解析失败

- **GIVEN** 一个已注册语言文件无法被 tree-sitter 正常解析
- **WHEN** 生成 repo map
- **THEN** 系统 SHALL 保留该文件的文件级条目
- **AND** SHALL 在摘要中标识解析不可用
