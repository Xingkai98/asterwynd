## ADDED Requirements

### Requirement: 语义代码搜索

系统 SHALL 支持基于 embedding 向量的语义代码搜索。`SearchSimilar` 工具 SHALL 接受自然语言查询或代码片段，返回语义最相似的文件位置和代码片段，按相似度降序排列。

#### Scenario: 自然语言查询

- **GIVEN** 代码索引已构建且包含多个函数
- **WHEN** agent 调用 SearchSimilar(query="查找所有处理超时错误的代码")
- **THEN** 系统 SHALL 返回 Top-N 个语义最相关的函数
- **AND** 每个返回值 SHALL 包含 file_path、行号范围、函数名和相似度分数

#### Scenario: 代码片段查询

- **GIVEN** 代码索引包含相似模式的代码
- **WHEN** agent 调用 SearchSimilar 传入一段错误处理代码片段
- **THEN** 系统 SHALL 返回代码库中语义相似的错误处理代码

#### Scenario: 索引不存在时懒构建

- **GIVEN** 当前仓库尚未构建 embedding 索引
- **WHEN** agent 首次调用 SearchSimilar
- **THEN** 系统 SHALL 自动触发索引构建
- **AND** 构建完成后 SHALL 返回搜索结果

#### Scenario: embedding 模型不可用

- **GIVEN** sentence-transformers 库不可用或模型下载失败
- **WHEN** agent 调用 SearchSimilar
- **THEN** 系统 SHALL 返回明确错误："embedding 模型不可用"

#### Scenario: 空仓库

- **GIVEN** 仓库中无 Python/TS/JS/Go/Rust/Java 函数可提取
- **WHEN** agent 调用 SearchSimilar
- **THEN** 系统 SHALL 返回"无可用索引"提示

### Requirement: 代码片段索引

系统 SHALL 使用 tree-sitter 将代码按函数/方法级粒度切分为独立的 chunk 进行索引。每个 chunk SHALL 包含文件路径、函数名、行号范围和代码文本。索引存储 SHALL 基于 sqlite-vec。

#### Scenario: 索引构建

- **GIVEN** 仓库包含 50 个 Python 文件、每个文件有 5 个函数
- **WHEN** 触发索引构建
- **THEN** 系统 SHALL 提取约 250 个函数 chunk
- **AND** 每个 chunk SHALL 生成 embedding 向量
- **AND** SHALL 存入 sqlite-vec 索引

#### Scenario: 增量更新

- **GIVEN** 索引已构建
- **AND** 其中一个文件自上次索引后被修改
- **WHEN** 再次调用 SearchSimilar
- **THEN** 修改的文件对应的旧条目 SHALL 被失效
- **AND** 修改文件的当前版本 SHALL 被重新索引
