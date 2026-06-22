## ADDED Requirements

### Requirement: 提供只读代码理解工具

系统 SHALL 提供只读工具用于查询 repo map 和代码符号。这些工具 SHALL NOT 修改工作区文件。

#### Scenario: 查询 repo map

- **GIVEN** 用户请求理解仓库结构
- **WHEN** 调用 repo map 工具
- **THEN** 工具 SHALL 返回受限长度的仓库结构摘要

#### Scenario: 查询代码符号

- **GIVEN** 用户请求查找某个符号
- **WHEN** 调用 symbol 查询工具
- **THEN** 工具 SHALL 返回匹配符号及其文件位置
