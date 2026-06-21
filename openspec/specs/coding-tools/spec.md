# coding-tools 规格

## Purpose

定义当前内置 coding tools 的行为边界。工具位于 `agent/tools/builtin/`，包括 Read、Write、Edit、Bash、Grep、InspectGitDiff、ListFiles 和 Find。

## Requirements

### Requirement: Read 按传入路径读取文件内容

Read SHALL 使用传入 path 构造本地文件路径，读取文本内容，并按可选 limit 截断返回行数。当前 ReadTool 不接收 WorkspacePolicy，也不执行 workspace root 校验。

#### Scenario: 读取存在的文件

- **GIVEN** 传入 path 指向存在的本地文件
- **WHEN** 调用 Read
- **THEN** 工具 SHALL 返回文件文本内容

#### Scenario: 读取不存在的文件

- **GIVEN** 传入 path 不存在
- **WHEN** 调用 Read
- **THEN** 工具 SHALL 返回文件不存在错误

### Requirement: Write 只创建新文件

Write SHALL 通过 WorkspacePolicy 校验写入路径，创建新文件，并禁止覆盖已有文件。

#### Scenario: 目标文件已存在

- **GIVEN** 写入目标路径已经存在
- **WHEN** 调用 Write
- **THEN** 工具 SHALL 拒绝覆盖
- **AND** 返回可读错误

### Requirement: Edit 使用精确文本替换

Edit SHALL 使用 old string 和 new string 对文件执行精确替换。

#### Scenario: old string 不存在或不唯一

- **GIVEN** old string 无法唯一匹配目标文件
- **WHEN** 调用 Edit
- **THEN** 工具 SHALL 拒绝修改
- **AND** 返回说明性错误

### Requirement: Bash 返回结构化 JSON

Bash SHALL 执行允许的 shell 命令，并返回包含 `exit_code`、`stdout`、`stderr`、`duration_ms` 和 `timed_out` 的 JSON 字符串。

#### Scenario: 命令超时或失败

- **GIVEN** Bash 命令执行失败或超时
- **WHEN** 工具返回结果
- **THEN** JSON SHALL 保留退出状态、输出和超时信息

### Requirement: 搜索和列表工具只读

Grep、ListFiles、Find 和 InspectGitDiff SHALL 声明为 read-only 工具。

#### Scenario: 调用声明为只读的工具

- **GIVEN** 用户请求搜索、列目录、查找文件或查看 diff
- **WHEN** 对应工具执行
- **THEN** 工具 SHALL NOT 修改工作区文件

#### Scenario: Grep 搜索路径

- **GIVEN** 用户调用 Grep
- **WHEN** Grep 读取文件或目录
- **THEN** Grep SHALL 使用传入 path 直接构造 Path
- **AND** 当前 GrepTool SHALL NOT 执行 WorkspacePolicy 校验

### Requirement: InspectGitDiff 展示当前 diff

InspectGitDiff SHALL 在 WorkspacePolicy 的 workspace root 下运行 git diff；未传 path 时返回 tracked files 的 diff stat，传入 path 时先做 workspace read 校验并返回该路径的 diff。

#### Scenario: 无工作区变更

- **GIVEN** git diff 为空
- **WHEN** 调用 InspectGitDiff
- **THEN** 工具 SHALL 返回 tracked files 无变更提示

#### Scenario: 包含未跟踪文件

- **GIVEN** include_untracked 为 true
- **WHEN** 调用 InspectGitDiff
- **THEN** 工具 SHALL 追加 `git ls-files --others --exclude-standard` 的截断输出
