## MODIFIED Requirements

### Requirement: Read 按传入路径读取文件内容

Read SHALL 使用 WorkspacePolicy 校验传入 path，读取允许路径下的文本内容，并按可选 limit 截断返回行数。Read SHALL 拒绝 workspace 外路径和当前 read policy 拒绝的路径。

#### Scenario: 读取允许文件

- **GIVEN** 传入 path 指向 workspace 内且 read policy 允许的本地文件
- **WHEN** 调用 Read
- **THEN** 工具 SHALL 返回文件文本内容

#### Scenario: 读取不存在的文件

- **GIVEN** 传入 path 通过 policy 校验但文件不存在
- **WHEN** 调用 Read
- **THEN** 工具 SHALL 返回文件不存在错误

#### Scenario: 拒绝 workspace 外文件

- **GIVEN** 传入 path 指向 workspace 外文件
- **WHEN** 调用 Read
- **THEN** 工具 SHALL 拒绝读取
- **AND** 返回权限错误

#### Scenario: 拒绝 denied pattern 文件

- **GIVEN** 传入 path 指向 `.env` 或其他 read policy 拒绝的路径
- **WHEN** 调用 Read
- **THEN** 工具 SHALL 拒绝读取
- **AND** SHALL NOT 返回文件内容

### Requirement: 搜索和列表工具只读

Grep、ListFiles、Find 和 InspectGitDiff SHALL 声明为 read-only 工具。Read-only 工具 SHALL NOT 修改工作区文件；其中 Grep、ListFiles、Find 和 InspectGitDiff SHALL 使用 WorkspacePolicy 校验 agent-facing 读取边界。

#### Scenario: 调用声明为只读的工具

- **GIVEN** 用户请求搜索、列目录、查找文件或查看 diff
- **WHEN** 对应工具执行
- **THEN** 工具 SHALL NOT 修改工作区文件

#### Scenario: Grep 搜索允许路径

- **GIVEN** 用户调用 Grep 搜索 workspace 内且 read policy 允许的文件或目录
- **WHEN** Grep 读取匹配文件
- **THEN** Grep SHALL 返回匹配行

#### Scenario: Grep 拒绝 workspace 外路径

- **GIVEN** 用户调用 Grep 搜索 workspace 外路径
- **WHEN** Grep 校验搜索起点
- **THEN** Grep SHALL 拒绝搜索
- **AND** 返回权限错误

#### Scenario: Grep 递归跳过 denied paths

- **GIVEN** 用户调用 Grep 递归搜索 workspace 根目录
- **WHEN** 子树中包含 `.env`、`.git` 或其他 read policy 拒绝的路径
- **THEN** Grep SHALL 跳过这些路径
- **AND** SHALL NOT 返回 denied path 中的内容
