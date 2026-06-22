## MODIFIED Requirements

### Requirement: code intelligence 当前为预留能力域

系统 SHALL 在本 change 实现后提供 workspace-aware repo map 基础设施和 Python AST symbol 能力；不得声称具备 tree-sitter 多语言符号提取、完整 LSP、引用分析、诊断或语义索引。

#### Scenario: 当前代码定位

- **GIVEN** agent 需要查找代码
- **WHEN** 使用当前工具集
- **THEN** 系统 MAY 使用 Grep、Find、ListFiles、Read 等文本级工具
- **AND** 只有在本 change 实现后才 SHALL 提供 repo map 或 Python symbol 查询能力

## ADDED Requirements

### Requirement: 生成轻量 repo map

系统 SHALL 能在 workspace 内生成轻量 repo map，包含文件路径、文件类型、源码/测试/配置/文档分类、大小摘要和可提取的顶层代码结构摘要。

#### Scenario: 生成 repo map

- **GIVEN** workspace 包含多个源码文件
- **WHEN** 调用 repo map 能力
- **THEN** 系统 SHALL 返回按路径组织的代码结构摘要
- **AND** SHALL 跳过 WorkspacePolicy 拒绝的路径

#### Scenario: 生成多语言文件级 repo map

- **GIVEN** workspace 同时包含 Python、TypeScript、Markdown 和 YAML 文件
- **WHEN** 调用 repo map 能力
- **THEN** 系统 SHALL 返回这些允许读取文件的文件级条目和文件类型
- **AND** 只有已支持 extractor 的语言 SHALL 返回结构化符号摘要

### Requirement: 提取 Python 符号

系统 SHALL 使用结构化解析提取 Python 文件中的 class、function、method 和 import 摘要。

#### Scenario: 提取 Python 文件符号

- **GIVEN** Python 文件包含类、函数和导入
- **WHEN** code intelligence 扫描该文件
- **THEN** 系统 SHALL 返回对应符号名称、类型和所在行号

### Requirement: extractor 接口为后续多语言能力保留扩展点

系统 SHALL 将 repo scanner、repo map 输出和具体语言 extractor 解耦，使后续 tree-sitter 或 LSP 能以新 provider 接入。

#### Scenario: 非 Python 文件没有结构化 extractor

- **GIVEN** workspace 包含当前 extractor 不支持的语言文件
- **WHEN** code intelligence 扫描该文件
- **THEN** 系统 SHALL 保留该文件的 repo map 条目
- **AND** SHALL NOT 伪造不可靠的函数或类符号
