## ADDED Requirements

### Requirement: 提供只读 repo map 和 Python 符号工具

系统 SHALL 提供只读工具用于查询 repo map 和 Python 代码符号。这些工具 SHALL NOT 修改工作区文件。

#### Scenario: 查询 repo map

- **GIVEN** 用户请求理解仓库结构
- **WHEN** 调用 repo map 工具
- **THEN** 工具 SHALL 返回受限长度的仓库结构摘要
- **AND** 摘要 SHALL 包含文件类型和源码/测试/配置/文档分类

#### Scenario: 查询代码符号

- **GIVEN** 用户请求查找某个符号
- **WHEN** 调用 symbol 查询工具
- **THEN** 工具 SHALL 返回匹配符号及其文件位置

#### Scenario: 查询非 Python 文件

- **GIVEN** workspace 包含非 Python 源码文件
- **WHEN** 调用 repo map 工具
- **THEN** 工具 SHALL 返回该文件的文件级条目
- **AND** SHALL NOT 返回未支持语言的伪造符号
