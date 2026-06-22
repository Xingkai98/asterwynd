## MODIFIED Requirements

### Requirement: code intelligence 当前为预留能力域

系统 SHALL 在本 change 实现后提供轻量 repo map 和 Python symbol 能力；在实现前不得声称具备完整 LSP、引用分析或语义索引。

#### Scenario: 当前代码定位

- **GIVEN** agent 需要查找代码
- **WHEN** 使用当前工具集
- **THEN** 系统 MAY 使用 Grep、Find、ListFiles、Read 等文本级工具
- **AND** 只有在本 change 实现后才 SHALL 提供 repo map 或 symbol 查询能力

## ADDED Requirements

### Requirement: 生成轻量 repo map

系统 SHALL 能在 workspace 内生成轻量 repo map，包含文件路径、文件类型和可提取的顶层代码结构摘要。

#### Scenario: 生成 repo map

- **GIVEN** workspace 包含多个源码文件
- **WHEN** 调用 repo map 能力
- **THEN** 系统 SHALL 返回按路径组织的代码结构摘要
- **AND** SHALL 跳过 WorkspacePolicy 拒绝的路径

### Requirement: 提取 Python 符号

系统 SHALL 使用结构化解析提取 Python 文件中的 class、function、method 和 import 摘要。

#### Scenario: 提取 Python 文件符号

- **GIVEN** Python 文件包含类、函数和导入
- **WHEN** code intelligence 扫描该文件
- **THEN** 系统 SHALL 返回对应符号名称、类型和所在行号
