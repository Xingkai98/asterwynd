# coding-tools 规格

## Purpose

定义当前内置 coding tools 的行为边界。工具位于 `agent/tools/builtin/`，包括 Read、Write、Edit、Bash、Grep、InspectGitDiff、ListFiles、Find、RepoMap 和 SymbolSearch。

## Requirements

### Requirement: Read 按 WorkspacePolicy 读取文件内容

Read SHALL 使用 WorkspacePolicy 校验传入 path，读取允许路径下的内容。对于图片文件（`.png`、`.jpg`、`.jpeg`、`.gif`、`.webp`），Read SHALL 返回 `[TextBlock, ImageBlock]`（多模态返回值）。对于非图片文件，Read SHALL 保持现有 `str` 返回行为。

#### Scenario: 读取允许的文本文件

- **GIVEN** 传入 path 指向 workspace 内且 read policy 允许的本地文本文件
- **WHEN** 调用 Read
- **THEN** 工具 SHALL 返回文件文本内容（`str` 类型）

#### Scenario: 读取 PNG 图片

- **GIVEN** path 指向一个有效的 PNG 文件
- **WHEN** 调用 Read
- **THEN** `execute()` SHALL 返回 `[TextBlock(描述文本), ImageBlock(base64 data URL, file_path=原始路径)]`
- **AND** TextBlock 包含文件名和尺寸
- **AND** ImageBlock 包含 base64 data URL 和原始文件路径

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

#### Scenario: 超大图片

- **GIVEN** 图片文件超过 20MB
- **WHEN** 调用 Read
- **THEN** `execute()` SHALL 返回错误 TextBlock 提示图片过大

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

### Requirement: Bash 支持后台执行

`Bash` 工具 SHALL 新增 `run_in_background` 参数（默认 `False`）。当 `run_in_background=True` 时，Bash SHALL 异步启动子进程并立即返回 task_id。后台命令 SHALL 仍然经过 workspace safety 的 allowlist/denylist 检查。

#### Scenario: 后台命令通过安全检查

- **GIVEN** agent 调用 Bash 且 run_in_background=True
- **WHEN** 命令为 `pytest -q tests/`
- **AND** 命令通过 allowlist 检查
- **THEN** 命令 SHALL 在后台启动
- **AND** SHALL 返回 task_id

#### Scenario: 后台命令被拒绝

- **GIVEN** agent 调用 Bash 且 run_in_background=True
- **WHEN** 命令为 `rm -rf /`（被 denylist 拒绝）
- **THEN** 系统 SHALL 返回权限错误
- **AND** SHALL NOT 启动任何进程

#### Scenario: 前台执行保持不变

- **GIVEN** agent 调用 Bash 且 run_in_background=False（默认）
- **WHEN** 命令执行
- **THEN** 行为 SHALL 与改动前完全一致（同步阻塞等待结果）

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

### Requirement: 代码理解工具返回多语言符号

RepoMap 和 SymbolSearch SHALL 声明为 read-only 工具，并在 extractor 可用时返回 Python AST 与 tree-sitter 多语言结构化符号。新增 tree-sitter 符号 SHALL 复用既有 repo map / symbol search 输出形状，新增来源标识 SHALL 是向后兼容扩展。

#### Scenario: 查询多语言符号

- **GIVEN** workspace 包含 Python 和 TypeScript 符号
- **WHEN** 调用 SymbolSearch
- **THEN** 工具 SHALL 返回匹配的多语言符号及其文件位置
- **AND** SHALL 保持只读，不修改工作区文件
